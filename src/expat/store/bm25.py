"""Sparse retrieval: a `bm25s` index over `ChunkRecord.embed_text` with German Snowball stemming.

Why BM25 at all (ADR-0004): embeddings blur exact identifiers such as "§ 573c", "18g" or
"Anlage N"; BM25 matches them literally. Why stemming: German inflects heavily, and without it
"Kündigungsfristen" (plural) would not match "Kündigungsfrist". The Snowball German stemmer also
folds umlauts (ü -> u), so "Kundigungsfrist" typed on an English keyboard still matches.

Known limitation: no decompounding ("Mietpreisbremse" does not match "Miete"). Stretch goal.

Persistence layout in `settings.bm25_dir`:
    <bm25s files>         the sparse score matrix + vocabulary (bm25s.BM25.save)
    records.jsonl         one line per indexed chunk, in index order: {chunk_id, text, metadata}
The metadata sidecar is what lets us apply the Chroma-style `where` filter after scoring.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bm25s
import numpy as np
import Stemmer
from bm25s.stopwords import STOPWORDS_EN, STOPWORDS_GERMAN

from expat.schemas import ChunkMetadata, ChunkRecord
from expat.store.vectorstore import from_chroma_metadata, to_chroma_metadata
from expat.store.where import Where, matches_where

RECORDS_FILE = "records.jsonl"

# Words of 2+ characters, including digits and letter-digit mixes: "573c", "18g", "§" is dropped.
_TOKEN_RE = re.compile(r"\w\w+", re.UNICODE)
# Queries arrive in German AND English (queries_en variants), so drop stopwords of both.
_STOPWORDS = frozenset(STOPWORDS_GERMAN) | frozenset(STOPWORDS_EN)
_STEMMER = Stemmer.Stemmer("german")


def tokenize(text: str) -> list[str]:
    """Lowercase -> split -> drop stopwords -> German Snowball stem. Used for corpus AND queries."""
    words = [w for w in _TOKEN_RE.findall(text.lower()) if w not in _STOPWORDS]
    return list(_STEMMER.stemWords(words))


@dataclass
class SparseHit:
    chunk_id: str
    score: float
    text: str
    metadata: ChunkMetadata


class BM25Index:
    """bm25s index + per-document metadata, so filters can be applied after scoring."""

    def __init__(self, retriever: bm25s.BM25, records: list[dict[str, Any]]) -> None:
        self._bm25 = retriever
        self._records = records  # index position i <-> records[i]
        self._metadata = [from_chroma_metadata(r["metadata"]) for r in records]

    @classmethod
    def build(cls, chunks: list[ChunkRecord]) -> BM25Index:
        # Sort by chunk_id so a rebuild over the same chunks yields an identical index (determinism).
        ordered = sorted(chunks, key=lambda c: c.metadata.chunk_id)
        retriever = bm25s.BM25()
        if ordered:
            retriever.index([tokenize(c.embed_text) for c in ordered], show_progress=False)
        records = [
            {"chunk_id": c.metadata.chunk_id, "text": c.text, "metadata": to_chroma_metadata(c.metadata)}
            for c in ordered
        ]
        return cls(retriever, records)

    def __len__(self) -> int:
        return len(self._records)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        if self._records:
            self._bm25.save(str(directory), show_progress=False)
        with (directory / RECORDS_FILE).open("w", encoding="utf-8") as f:
            for record in self._records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, directory: Path) -> BM25Index:
        path = directory / RECORDS_FILE
        if not path.exists():
            raise FileNotFoundError(f"No BM25 index in {directory}. Run `uv run python -m expat.store` first.")
        with path.open(encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        retriever = bm25s.BM25.load(str(directory), show_progress=False) if records else bm25s.BM25()
        return cls(retriever, records)

    def search(self, query: str, k: int, where: Where | None = None) -> list[SparseHit]:
        """Score ALL documents, filter by `where`, return the top-k with score > 0.

        Scoring everything is O(corpus) but trivial at our size (~3k chunks), and it makes the
        filtered top-k exact: "retrieve top-k, then filter" could return fewer than k results.
        """
        if not self._records:
            return []
        token_ids = self._bm25.get_tokens_ids(tokenize(query))
        if not token_ids:
            return []  # no query term occurs in the corpus
        scores = np.asarray(self._bm25.get_scores_from_ids(token_ids))
        hits: list[SparseHit] = []
        for i in np.argsort(-scores, kind="stable"):
            if scores[i] <= 0 or len(hits) >= k:
                break
            record = self._records[int(i)]
            if matches_where(record["metadata"], where):
                hits.append(SparseHit(record["chunk_id"], float(scores[i]), record["text"], self._metadata[int(i)]))
        return hits
