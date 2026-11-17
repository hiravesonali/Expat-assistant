from datetime import date
from pathlib import Path

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from expat.llm import EmbeddingAdapter
from expat.store.synthetic import synthetic_chunks
from expat.store.vectorstore import (
    OPEN_END_TS,
    ChunkVectorStore,
    EmbeddingModelMismatchError,
    days_since_epoch,
    from_chroma_metadata,
    to_chroma_metadata,
)


def _store(tmp_path: Path, model: str = "test/fake-embedding") -> ChunkVectorStore:
    return ChunkVectorStore(
        EmbeddingAdapter(DeterministicFakeEmbedding(size=32), model),
        persist_dir=tmp_path,
        collection_name="test",
    )


def test_metadata_flattening_roundtrip() -> None:
    expired = next(c for c in synthetic_chunks() if c.metadata.valid_until)
    flat = to_chroma_metadata(expired.metadata)
    assert flat["valid_until"] == "2025-12-31"
    assert flat["valid_until_ts"] == days_since_epoch(date(2025, 12, 31))
    assert flat["applies_to"] == ["all"]
    assert from_chroma_metadata(flat) == expired.metadata


def test_open_ended_validity_gets_sentinel() -> None:
    flat = to_chroma_metadata(synthetic_chunks()[0].metadata)
    assert flat["valid_until"] == ""
    assert flat["valid_until_ts"] == OPEN_END_TS
    assert from_chroma_metadata(flat).valid_until is None


def test_upsert_is_idempotent_and_skips_unchanged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    chunks = synthetic_chunks()
    first = store.upsert(chunks)
    second = store.upsert(chunks)
    assert first.embedded == len(chunks)
    assert (second.embedded, second.unchanged) == (0, len(chunks))
    assert store.count() == len(chunks)


def test_changed_content_is_reembedded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    chunks = synthetic_chunks()
    store.upsert(chunks)
    edited = chunks[0].model_copy(
        update={"text": "neu", "metadata": chunks[0].metadata.model_copy(update={"content_hash": "changed"})}
    )
    stats = store.upsert([edited, *chunks[1:]])
    assert stats.embedded_ids == [edited.metadata.chunk_id]


def test_orphans_of_a_reingested_doc_are_deleted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    chunks = synthetic_chunks()
    store.upsert(chunks)
    # New version of the BGB doc keeps only Abs. 1 of § 573c; other docs are not re-ingested.
    bgb_doc = chunks[0].metadata.doc_id
    new_bgb = [chunks[0]]
    assert store.delete_orphans(new_bgb) == sum(1 for c in chunks if c.metadata.doc_id == bgb_doc) - 1
    remaining = {cid for cid, _, _ in store.all_records()}
    assert chunks[0].metadata.chunk_id in remaining
    assert chunks[1].metadata.chunk_id not in remaining
    assert chunks[3].metadata.chunk_id in remaining  # other doc untouched


def test_query_returns_exact_match_first_and_applies_where(tmp_path: Path) -> None:
    store = _store(tmp_path)
    chunks = synthetic_chunks()
    store.upsert(chunks)
    target = chunks[3]
    hits = store.query(target.embed_text, k=3)
    assert hits[0].chunk_id == target.metadata.chunk_id
    assert hits[0].metadata == target.metadata.model_copy(update={"embedding_model": "test/fake-embedding"})
    berlin_only = store.query(target.embed_text, k=10, where={"city": "berlin"})
    assert [h.metadata.city for h in berlin_only] == ["berlin"]


def test_embedding_model_mismatch_is_rejected(tmp_path: Path) -> None:
    _store(tmp_path, model="qwen/qwen3-embedding-8b")
    with pytest.raises(EmbeddingModelMismatchError):
        _store(tmp_path, model="baai/bge-m3")
