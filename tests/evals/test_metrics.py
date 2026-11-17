"""Hand-computed cases for the deterministic metrics (the numbers in the comments are worked out by hand)."""

from datetime import date

import pytest

from expat.evals.metrics import (
    args_subset_match,
    citation_correctness,
    citation_validity,
    contains_phrase,
    extract_citation_ids,
    hit_at_k,
    looks_like_refusal,
    mean,
    mrr_at_k,
    must_include_score,
    must_not_include_ok,
    paragraph_citation_coverage,
    percentile,
    recall_at_k,
    refusal_correct,
    tool_selection_correct,
)
from expat.schemas import ToolCallEvent

RETRIEVED = ["bgb#573", "muc-anmeldung#documents", "bgb#573c", "fp-kindergeld#faq", "bmg#17"]


# --- hit@k -----------------------------------------------------------------------------------------------------


def test_hit_at_k_exact_key() -> None:
    assert hit_at_k(RETRIEVED, ["bgb#573c"], k=5) == 1.0
    assert hit_at_k(RETRIEVED, ["bgb#573c"], k=2) == 0.0  # it is at rank 3


def test_hit_at_k_prefix_rule() -> None:
    # bare source_id matches any section of that page ...
    assert hit_at_k(RETRIEVED, ["muc-anmeldung"], k=2) == 1.0
    # ... but a law key never matches a "longer" paragraph: bgb#573 must not match bgb#573c and vice versa
    assert hit_at_k(["bgb#573c"], ["bgb#573"], k=5) == 0.0
    assert hit_at_k(["bgb#573"], ["bgb#573c"], k=5) == 0.0
    # and "muc-anmeldung" must not match the different source "muc-anmeldung-familie"
    assert hit_at_k(["muc-anmeldung-familie#documents"], ["muc-anmeldung"], k=5) == 0.0


def test_metrics_reject_empty_expectation() -> None:
    with pytest.raises(ValueError):
        hit_at_k(RETRIEVED, [])


# --- recall@k --------------------------------------------------------------------------------------------------


def test_recall_at_k() -> None:
    # expected 4 keys; in top-10: bgb#573c yes, fp-kindergeld yes (prefix), muc-kita no, bmg#17 yes -> 3/4
    assert recall_at_k(RETRIEVED, ["bgb#573c", "fp-kindergeld", "muc-kita", "bmg#17"], k=10) == 0.75
    # top-3 only contains bgb#573c of those -> 1/4
    assert recall_at_k(RETRIEVED, ["bgb#573c", "fp-kindergeld", "muc-kita", "bmg#17"], k=3) == 0.25


def test_recall_counts_each_expected_key_once() -> None:
    # two retrieved sections of the same page still satisfy only ONE expected key
    retrieved = ["muc-anmeldung#documents", "muc-anmeldung#fees"]
    assert recall_at_k(retrieved, ["muc-anmeldung", "bmg#17"], k=10) == 0.5


# --- MRR -------------------------------------------------------------------------------------------------------


def test_mrr_at_k() -> None:
    assert mrr_at_k(RETRIEVED, ["bgb#573"]) == 1.0  # rank 1
    assert mrr_at_k(RETRIEVED, ["muc-anmeldung"]) == 0.5  # rank 2 via prefix
    assert mrr_at_k(RETRIEVED, ["bgb#573c", "bmg#17"]) == pytest.approx(1 / 3)  # first relevant at rank 3
    assert mrr_at_k(RETRIEVED, ["bmg#17"], k=4) == 0.0  # rank 5 is outside k=4
    assert mrr_at_k(RETRIEVED, ["muc-kita"]) == 0.0


def test_mean_mrr_over_examples() -> None:
    # MRR = mean of reciprocal ranks: (1 + 1/2 + 0) / 3 = 0.5
    rr = [mrr_at_k(RETRIEVED, ["bgb#573"]), mrr_at_k(RETRIEVED, ["muc-anmeldung"]), mrr_at_k(RETRIEVED, ["x"])]
    assert mean(rr) == pytest.approx(0.5)


# --- citations -------------------------------------------------------------------------------------------------


def test_extract_citation_ids_handles_groups_and_dedupes() -> None:
    answer = "Six months [S2]. Landlord needs a reason [S1, S2]. End date [T1][S3]."
    assert extract_citation_ids(answer) == ["S2", "S1", "T1", "S3"]


def test_citation_validity() -> None:
    assert citation_validity("A [S1]. B [T1].", ["S1", "S2", "T1"]) == 1.0
    assert citation_validity("A [S1]. B [S7].", ["S1", "S2"]) == 0.0  # invented source
    assert citation_validity("No citations at all.", ["S1"]) == 0.0


def test_paragraph_citation_coverage_skips_headings_and_short_lines() -> None:
    answer = (
        "## Short answer\n\n"
        "The notice period is six months because you rented for six years [S1].\n\n"
        "The landlord also needs a legitimate interest such as personal need.\n\n"
        "Next steps:"
    )
    # 2 factual paragraphs, 1 cited -> 0.5
    assert paragraph_citation_coverage(answer) == 0.5


def test_citation_correctness() -> None:
    # cited: bgb#573c (expected), bgb#573 (optional expected), muc-kita#overview (wrong) -> 2/3
    expected = ["bgb#573c", "bgb#573"]
    assert citation_correctness(["bgb#573c", "bgb#573", "muc-kita#overview"], expected) == pytest.approx(2 / 3)
    assert citation_correctness([], expected) == 0.0


# --- must_include ----------------------------------------------------------------------------------------------


def test_must_include_alternatives_and_case() -> None:
    answer = "You must register within Two Weeks (§ 17 BMG)."
    assert contains_phrase(answer, "2 weeks|two weeks|14 days")
    assert must_include_score(answer, ["2 weeks|two weeks", "17", "€259"]) == pytest.approx(2 / 3)
    assert must_include_score(answer, []) == 1.0


def test_must_include_normalises_non_breaking_spaces() -> None:
    assert contains_phrase("Kappungsgrenze 15 %", "15 %")


def test_must_not_include() -> None:
    assert must_not_include_ok("Kindergeld is €259.", ["€250"])
    assert not must_not_include_ok("Kindergeld is €250.", ["€250|250 euro"])


# --- tool selection --------------------------------------------------------------------------------------------


def test_tool_selection_expected_tool_with_args_subset() -> None:
    expected = {"name": "calculate_deadline", "args_subset": {"procedure": "anmeldung", "event_date": "2026-12-01"}}
    good = ToolCallEvent(
        call_id="1", name="calculate_deadline", args={"procedure": "anmeldung", "event_date": "2026-12-01"}
    )
    wrong_args = {"name": "calculate_deadline", "args": {"procedure": "abmeldung", "event_date": "2026-12-01"}}
    assert tool_selection_correct(expected, [good])
    assert tool_selection_correct(expected, [wrong_args, good])  # a corrected retry counts
    assert not tool_selection_correct(expected, [wrong_args])
    assert not tool_selection_correct(expected, [])


def test_tool_selection_no_tool_expected() -> None:
    assert tool_selection_correct(None, [])
    assert not tool_selection_correct(None, [{"name": "calculate_deadline", "args": {}}])


def test_args_subset_match_types() -> None:
    assert args_subset_match({"event_date": "2026-12-01"}, {"event_date": date(2026, 12, 1), "extra": 1})
    assert args_subset_match({"children_count": 2}, {"children_count": 2.0})
    assert args_subset_match({"include_elterngeld": True}, {"include_elterngeld": True})
    assert not args_subset_match({"include_elterngeld": True}, {"include_elterngeld": 1})
    assert not args_subset_match({"party": "landlord"}, {})


# --- refusal ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("I can't give advice on asylum cases. Please contact a lawyer.", True),
        ("Ich kann Ihnen dazu keine Rechtsberatung geben.", True),
        ("That is outside what I can advise on.", True),
        ("The rent is reduced by law [S1]. Get advice from a Mieterverein.", False),
        ("Der Vermieter kann nicht kündigen [S1]. This is not legal advice.", False),
    ],
)
def test_looks_like_refusal(answer: str, expected: bool) -> None:
    assert looks_like_refusal(answer) is expected


def test_refusal_correct_both_directions() -> None:
    assert refusal_correct(True, True)
    assert refusal_correct(False, False)
    assert not refusal_correct(False, True)  # over-refusal is an error too


# --- aggregation -----------------------------------------------------------------------------------------------


def test_percentile_and_mean() -> None:
    assert percentile([10, 20, 30, 40], 50) == 25
    assert percentile([5], 95) == 5
    assert percentile([], 50) is None
    assert mean([]) is None
