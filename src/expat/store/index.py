"""Indexer: data/processed/{chunks,parents}.jsonl -> Chroma + SQLite docstore + BM25.

Every step is idempotent, so running the indexer twice yields identical counts and ids
(the Day-2 "done" criterion in docs/milestones.md):
1. validate + load the JSONL files (Pydantic: a malformed line fails here, not inside Chroma);
2. upsert chunks into Chroma, embedding only new/changed `content_hash`es;
3. delete orphan chunks of re-ingested documents;
4. upsert parents into SQLite;
5. rebuild the BM25 index from the same chunks (seconds at this scale, so no incremental logic).

Assumption: chunks.jsonl is the FULL processed corpus (ingestion writes it that way). BM25 is
rebuilt from it, so a partial file would shrink the BM25 index while Chroma keeps old documents.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from expat.schemas import ChunkRecord, ParentRecord
from expat.store.bm25 import BM25Index
from expat.store.docstore import ParentDocstore
from expat.store.vectorstore import ChunkVectorStore


def read_jsonl[M: BaseModel](path: Path, model: type[M]) -> list[M]:
    """Read a JSONL file, validating every line (PEP 695 generic: returns list of the given model)."""
    with path.open(encoding="utf-8") as f:
        return [model.model_validate_json(line) for line in f if line.strip()]


@dataclass
class IndexSummary:
    collection: str
    embedding_model: str
    chunks_in: int
    embedded: int
    unchanged: int
    orphans_deleted: int
    collection_count: int
    parents_upserted: int
    docstore_count: int
    bm25_docs: int

    def render(self) -> str:
        return "\n".join(f"{name:>17}: {value}" for name, value in vars(self).items())


def _assert_unique_ids(chunks: list[ChunkRecord]) -> None:
    """Duplicate chunk_ids would make Chroma's upsert fail mid-batch; fail early with a clear message."""
    dupes = [cid for cid, n in Counter(c.metadata.chunk_id for c in chunks).items() if n > 1]
    if dupes:
        raise ValueError(f"Duplicate chunk_id(s) in input: {dupes[:5]}")


def index_corpus(
    chunks: list[ChunkRecord],
    parents: list[ParentRecord],
    vector_store: ChunkVectorStore,
    docstore: ParentDocstore,
    bm25_dir: Path,
) -> IndexSummary:
    _assert_unique_ids(chunks)
    stats = vector_store.upsert(chunks)
    orphans = vector_store.delete_orphans(chunks)
    docstore.put_many(parents)
    bm25 = BM25Index.build(chunks)
    bm25.save(bm25_dir)
    return IndexSummary(
        collection=vector_store.collection_name,
        embedding_model=vector_store.embeddings.model_name,
        chunks_in=len(chunks),
        embedded=stats.embedded,
        unchanged=stats.unchanged,
        orphans_deleted=orphans,
        collection_count=vector_store.count(),
        parents_upserted=len(parents),
        docstore_count=docstore.count(),
        bm25_docs=len(bm25),
    )
