"""Chroma collection for child chunks (ADR-0001): factory, metadata flattening, upsert, query.

Why we talk to `chromadb` directly instead of `langchain_chroma.Chroma`:
* the indexer embeds ONLY chunks whose `content_hash` changed and refreshes metadata of the others
  without re-embedding; that needs `collection.upsert(embeddings=...)` / `collection.update(...)`;
* we store a native list (`applies_to`) in metadata, verified by tests/store/test_chroma_spike.py;
* we guard against querying an index with the wrong embedding model (see below).
The query side is a ~10-line call to `collection.query`, so the LangChain wrapper would add little.

Metadata flattening (Chroma metadata values are str/int/float/bool or a list of one of those):
* enums -> their string value;
* dates -> ISO string (for display) + `<field>_ts` int = days since 1970-01-01 (Chroma's `$gte`/`$lt`
  only work on numbers);
* missing `valid_from` / `valid_until` -> "" + a sentinel `_ts` (see `OPEN_START_TS` / `OPEN_END_TS`).
  Chroma comparisons never match a document that lacks the key, so "no expiry date" must be
  written as "expires at the end of time" for `valid_until_ts >= today` to keep it;
* `applies_to` -> native list of strings (spike result: local chromadb 1.5.9 supports `$contains`).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from expat.config import Settings, get_settings
from expat.llm import EmbeddingAdapter
from expat.schemas import ChunkMetadata, ChunkRecord

EPOCH = date(1970, 1, 1)
OPEN_START_TS = (date.min - EPOCH).days  # -719162: "valid since forever"
OPEN_END_TS = (date.max - EPOCH).days  # 2932896: "valid until 9999-12-31"
DATE_FIELDS = ("last_verified", "valid_from", "valid_until")

# Chroma's default upsert batch limit is ~5k; small batches also keep embedding API calls modest.
EMBED_BATCH = 64


class EmbeddingModelMismatchError(RuntimeError):
    """The query embedder is not the model the collection was built with (vectors are incomparable)."""


def days_since_epoch(d: date) -> int:
    return (d - EPOCH).days


def to_chroma_metadata(meta: ChunkMetadata) -> dict[str, Any]:
    """Flatten a validated ChunkMetadata into Chroma-compatible values (see module docstring)."""
    flat: dict[str, Any] = meta.model_dump(mode="json", exclude=set(DATE_FIELDS))
    flat["applies_to"] = [str(a) for a in meta.applies_to]
    flat["last_verified"] = meta.last_verified.isoformat()
    flat["last_verified_ts"] = days_since_epoch(meta.last_verified)
    flat["valid_from"] = meta.valid_from.isoformat() if meta.valid_from else ""
    flat["valid_from_ts"] = days_since_epoch(meta.valid_from) if meta.valid_from else OPEN_START_TS
    flat["valid_until"] = meta.valid_until.isoformat() if meta.valid_until else ""
    flat["valid_until_ts"] = days_since_epoch(meta.valid_until) if meta.valid_until else OPEN_END_TS
    return flat


def from_chroma_metadata(flat: dict[str, Any]) -> ChunkMetadata:
    """Inverse of `to_chroma_metadata`: drop the derived `_ts` keys, turn "" dates back into None."""
    data = {k: v for k, v in flat.items() if not k.endswith("_ts")}
    for name in ("valid_from", "valid_until"):
        if data.get(name) == "":
            data[name] = None
    return ChunkMetadata.model_validate(data)


@dataclass
class DenseHit:
    chunk_id: str
    distance: float  # cosine distance: 0 = identical direction
    text: str
    metadata: ChunkMetadata


@dataclass
class UpsertStats:
    embedded: int = 0  # new or changed content -> re-embedded
    unchanged: int = 0  # same content_hash -> metadata refreshed only
    deleted_orphans: int = 0
    embedded_ids: list[str] = field(default_factory=list)


class ChunkVectorStore:
    """One Chroma collection of child chunks, bound to one embedding model."""

    def __init__(
        self,
        embeddings: EmbeddingAdapter,
        persist_dir: Path | None = None,
        collection_name: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        s = settings or get_settings()
        self.embeddings = embeddings
        self.collection_name = collection_name or s.collection_name
        directory = persist_dir or s.chroma_dir
        directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(directory))
        self.collection: Collection = self.client.get_or_create_collection(
            self.collection_name,
            # We always pass our own vectors; None stops Chroma from loading its default ONNX model.
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"embedding_model": embeddings.model_name, "schema_version": s.schema_version},
        )
        self.assert_embedding_model()

    # ------------------------------------------------------------------------------ safety check

    @property
    def indexed_model(self) -> str:
        return str((self.collection.metadata or {}).get("embedding_model", ""))

    def assert_embedding_model(self) -> None:
        """Fail loudly if this collection was built with a different embedding model.

        `get_or_create_collection` ignores the metadata argument for an existing collection, so the
        stored value is the one written at creation time: exactly what we need to compare against.
        """
        if self.indexed_model != self.embeddings.model_name:
            raise EmbeddingModelMismatchError(
                f"Collection {self.collection_name!r} was built with {self.indexed_model!r}, "
                f"but the query embedder is {self.embeddings.model_name!r}."
            )

    # ------------------------------------------------------------------------------------- write

    def existing_hashes(self, ids: Sequence[str]) -> dict[str, str]:
        if not ids:
            return {}
        got = self.collection.get(ids=list(ids), include=["metadatas"])
        metas = got["metadatas"] or []
        return {cid: str(m.get("content_hash", "")) for cid, m in zip(got["ids"], metas, strict=True)}

    def upsert(self, records: Sequence[ChunkRecord]) -> UpsertStats:
        """Idempotent upsert: embed only new/changed chunks, refresh metadata for the rest."""
        stats = UpsertStats()
        stamped = [r.model_copy(update={"metadata": self._stamp(r.metadata)}) for r in records]
        known = self.existing_hashes([r.metadata.chunk_id for r in stamped])
        changed = [r for r in stamped if known.get(r.metadata.chunk_id) != r.metadata.content_hash]
        unchanged = [r for r in stamped if known.get(r.metadata.chunk_id) == r.metadata.content_hash]

        for start in range(0, len(changed), EMBED_BATCH):
            batch = changed[start : start + EMBED_BATCH]
            vectors = self.embeddings.embed_documents([r.embed_text for r in batch])
            self.collection.upsert(
                ids=[r.metadata.chunk_id for r in batch],
                embeddings=vectors,  # type: ignore[arg-type]
                documents=[r.text for r in batch],
                metadatas=[to_chroma_metadata(r.metadata) for r in batch],
            )
        if unchanged:
            # e.g. a newer `last_verified`: cheap metadata-only update, no embedding API call.
            self.collection.update(
                ids=[r.metadata.chunk_id for r in unchanged],
                metadatas=[to_chroma_metadata(r.metadata) for r in unchanged],
            )
        stats.embedded = len(changed)
        stats.unchanged = len(unchanged)
        stats.embedded_ids = [r.metadata.chunk_id for r in changed]
        return stats

    def delete_orphans(self, records: Iterable[ChunkRecord]) -> int:
        """Delete chunks of the given documents that are no longer produced by ingestion.

        For every `doc_id` in `records`, any stored chunk whose id is not in the new set goes away.
        That covers the design's `doc_version != new` rule AND re-chunking within one version.
        Documents absent from `records` are left alone (partial re-ingestion must not wipe them).
        """
        current_ids: dict[str, set[str]] = {}
        for r in records:
            current_ids.setdefault(r.metadata.doc_id, set()).add(r.metadata.chunk_id)
        if not current_ids:
            return 0
        doc_filter: dict[str, Any] = {"doc_id": {"$in": list(current_ids)}}
        stored = self.collection.get(where=doc_filter, include=["metadatas"])
        metas = stored["metadatas"] or []
        orphans = [
            cid
            for cid, m in zip(stored["ids"], metas, strict=True)
            if cid not in current_ids.get(str(m["doc_id"]), set())
        ]
        if orphans:
            self.collection.delete(ids=orphans)
        return len(orphans)

    def _stamp(self, meta: ChunkMetadata) -> ChunkMetadata:
        return meta.model_copy(update={"embedding_model": self.embeddings.model_name})

    # -------------------------------------------------------------------------------------- read

    def count(self) -> int:
        return self.collection.count()

    def all_records(self) -> list[tuple[str, str, ChunkMetadata]]:
        """(chunk_id, text, metadata) for every stored chunk; used by tests and admin views."""
        got = self.collection.get(include=["documents", "metadatas"])
        docs = got["documents"] or []
        metas = got["metadatas"] or []
        return [(cid, doc, from_chroma_metadata(dict(m))) for cid, doc, m in zip(got["ids"], docs, metas, strict=True)]

    def query(self, text: str, k: int, where: dict[str, Any] | None = None) -> list[DenseHit]:
        """Dense search for one query variant. The model guard runs on EVERY query, not just at startup."""
        self.assert_embedding_model()
        n = min(k, self.count())
        if n == 0:
            return []
        res = self.collection.query(
            query_embeddings=[self.embeddings.embed_query(text)],  # type: ignore[arg-type]
            n_results=n,
            where=where or None,  # Chroma rejects an empty dict
            include=["documents", "metadatas", "distances"],
        )
        ids = res["ids"][0]
        docs = (res["documents"] or [[]])[0]
        metas = (res["metadatas"] or [[]])[0]
        dists = (res["distances"] or [[]])[0]
        return [
            DenseHit(chunk_id=cid, distance=float(d), text=doc, metadata=from_chroma_metadata(dict(m)))
            for cid, doc, m, d in zip(ids, docs, metas, dists, strict=True)
        ]
