from pathlib import Path

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from expat.config import Settings
from expat.llm import EmbeddingAdapter
from expat.store.__main__ import main
from expat.store.bm25 import BM25Index
from expat.store.docstore import ParentDocstore
from expat.store.index import index_corpus
from expat.store.synthetic import synthetic_chunks, synthetic_parents
from expat.store.vectorstore import ChunkVectorStore


def _run(tmp_path: Path, chunks=None):
    store = ChunkVectorStore(
        EmbeddingAdapter(DeterministicFakeEmbedding(size=32), "test/fake"),
        persist_dir=tmp_path / "chroma",
        collection_name="test",
    )
    return index_corpus(
        chunks=chunks if chunks is not None else synthetic_chunks(),
        parents=synthetic_parents(),
        vector_store=store,
        docstore=ParentDocstore(tmp_path / "docstore.sqlite"),
        bm25_dir=tmp_path / "bm25",
    )


def test_indexing_twice_gives_same_counts(tmp_path: Path) -> None:
    first = _run(tmp_path)
    second = _run(tmp_path)
    n = len(synthetic_chunks())
    assert (first.embedded, first.collection_count, first.bm25_docs) == (n, n, n)
    assert (second.embedded, second.unchanged, second.collection_count) == (0, n, n)
    assert second.docstore_count == first.docstore_count == len(synthetic_parents())


def test_reingesting_a_document_deletes_its_orphans(tmp_path: Path) -> None:
    _run(tmp_path)
    chunks = synthetic_chunks()
    # A new version of the BGB doc that no longer contains § 573c Abs. 2.
    without_abs2 = [c for c in chunks if c.metadata.legal_reference != "§ 573c Abs. 2 BGB"]
    summary = _run(tmp_path, chunks=without_abs2)
    assert summary.orphans_deleted == 1
    assert summary.collection_count == summary.bm25_docs == len(chunks) - 1
    assert len(BM25Index.load(tmp_path / "bm25")) == len(chunks) - 1


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    chunks = synthetic_chunks()
    with pytest.raises(ValueError, match="Duplicate"):
        _run(tmp_path, chunks=[*chunks, chunks[0]])


def test_cli_offline_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "chunks.jsonl").write_text(
        "\n".join(c.model_dump_json() for c in synthetic_chunks()), encoding="utf-8"
    )
    (processed / "parents.jsonl").write_text(
        "\n".join(p.model_dump_json() for p in synthetic_parents()), encoding="utf-8"
    )
    settings = Settings(_env_file=None, data_dir=tmp_path)
    monkeypatch.setattr("expat.store.__main__.get_settings", lambda: settings)
    assert main(["--fake-embeddings"]) == 0
    assert main(["--fake-embeddings", "--rebuild"]) == 0
    out = capsys.readouterr().out
    assert "expat__deterministic-embedding__s1" in out
    assert (tmp_path / "bm25" / "records.jsonl").exists()
