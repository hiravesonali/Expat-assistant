from pathlib import Path

from expat.store.bm25 import BM25Index, tokenize
from expat.store.synthetic import synthetic_chunks
from expat.store.where import matches_where


def _chunk_id(doc_key: str, contains: str) -> str:
    return next(c.metadata.chunk_id for c in synthetic_chunks() if c.metadata.doc_key == doc_key and contains in c.text)


def test_tokenize_stems_plural_and_folds_umlauts() -> None:
    assert tokenize("Kündigungsfristen") == tokenize("Kündigungsfrist") == tokenize("Kundigungsfrist")
    assert "573c" in tokenize("§ 573c BGB")


def test_german_stemming_match() -> None:
    index = BM25Index.build(synthetic_chunks())
    hits = index.search("Kündigungsfristen", k=5)
    # Abs. 2 (text AND header) contains only the singular "Kündigungsfrist", yet it is found.
    abs2 = next(c for c in synthetic_chunks() if c.metadata.legal_reference == "§ 573c Abs. 2 BGB")
    assert "Kündigungsfristen" not in abs2.embed_text
    assert _chunk_id("bgb#573c", "(2)") in {h.chunk_id for h in hits}


def test_exact_paragraph_lookup() -> None:
    index = BM25Index.build(synthetic_chunks())
    hits = index.search("§ 573c", k=5)
    assert {h.metadata.doc_key for h in hits} == {"bgb#573c"}
    assert all(h.metadata.doc_key != "bgb#573" for h in hits)  # "573" is a different token


def test_post_hoc_filter_and_no_match() -> None:
    index = BM25Index.build(synthetic_chunks())
    hits = index.search("Anmeldung Reisepass", k=5, where={"city": {"$in": ["munich", ""]}})
    assert [h.metadata.doc_key for h in hits] == ["muc-anmeldung#documents"]
    assert index.search("Steuerklasse", k=5) == []


def test_save_load_roundtrip(tmp_path: Path) -> None:
    index = BM25Index.build(synthetic_chunks())
    index.save(tmp_path)
    loaded = BM25Index.load(tmp_path)
    assert len(loaded) == len(index)
    before = [h.chunk_id for h in index.search("Kindergeld", k=3)]
    assert before
    assert [h.chunk_id for h in loaded.search("Kindergeld", k=3)] == before


def test_matches_where_semantics() -> None:
    meta = {"city": "", "applies_to": ["all"], "valid_until_ts": 100}
    assert matches_where(meta, None)
    assert matches_where(meta, {"$and": [{"city": {"$in": ["munich", ""]}}, {"valid_until_ts": {"$gte": 50}}]})
    assert matches_where(meta, {"$or": [{"applies_to": {"$contains": "non_eu"}}, {"applies_to": {"$contains": "all"}}]})
    assert not matches_where(meta, {"domain": "tenancy"})  # missing key never matches (like Chroma)
    assert not matches_where(meta, {"valid_until_ts": {"$lt": 100}})
