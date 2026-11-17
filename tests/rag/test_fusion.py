import pytest

from expat.rag.fusion import reciprocal_rank_fusion


def test_rrf_math_matches_formula() -> None:
    fused = reciprocal_rank_fusion({"dense": ["a", "b", "c"], "bm25": ["c", "a"]}, c=60)
    scores = {doc_id: score for doc_id, score, _ in fused}
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores["b"] == pytest.approx(1 / 62)
    assert scores["c"] == pytest.approx(1 / 63 + 1 / 61)
    assert [doc_id for doc_id, _, _ in fused] == ["a", "c", "b"]


def test_rrf_reports_per_list_ranks() -> None:
    fused = dict((d, r) for d, _, r in reciprocal_rank_fusion({"dense": ["a", "b"], "bm25": ["b"]}))
    assert fused["a"] == {"dense": 1}
    assert fused["b"] == {"dense": 2, "bm25": 1}


def test_rrf_agreement_beats_single_top_rank() -> None:
    # Ranked 2nd in two lists beats ranked 1st in one list: the core intuition of RRF.
    fused = reciprocal_rank_fusion({"l1": ["x", "y"], "l2": ["z", "y"]})
    assert fused[0][0] == "y"


def test_rrf_duplicates_within_a_list_count_once() -> None:
    fused = reciprocal_rank_fusion({"l1": ["a", "a", "b"]}, c=0)
    assert dict((d, s) for d, s, _ in fused) == {"a": 1.0, "b": pytest.approx(1 / 3)}


def test_rrf_empty_and_tie_break_deterministic() -> None:
    assert reciprocal_rank_fusion({}) == []
    assert reciprocal_rank_fusion({"l1": [], "l2": []}) == []
    fused = reciprocal_rank_fusion({"l1": ["b"], "l2": ["a"]})
    assert [d for d, _, _ in fused] == ["a", "b"]
