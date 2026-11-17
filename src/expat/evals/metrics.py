"""Deterministic eval metrics: pure functions, no I/O, no LLM. Hand-checked in tests/evals/test_metrics.py.

All retrieval metrics compare doc_keys with `expat.schemas.doc_key_matches` (exact match, or the golden key is a
prefix at a '#' boundary), never chunk ids: chunk ids change with every chunking experiment, doc_keys don't.
"""

import re
import statistics
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from expat.schemas import ToolCallEvent, doc_key_matches

# --- retrieval -------------------------------------------------------------------------------------------------


def _matches_any(retrieved_key: str, expected: Sequence[str]) -> bool:
    return any(doc_key_matches(retrieved_key, e) for e in expected)


def _require_expected(expected: Sequence[str]) -> None:
    # An empty expectation would make hit@k trivially 0 (or 1) and skew the mean silently. Callers skip refusal
    # examples explicitly instead.
    if not expected:
        raise ValueError("expected doc_keys must not be empty")


def hit_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int = 5) -> float:
    """1.0 if at least one expected doc_key is matched in the top-k retrieved doc_keys, else 0.0."""
    _require_expected(expected)
    return 1.0 if any(_matches_any(key, expected) for key in retrieved[:k]) else 0.0


def recall_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int = 10) -> float:
    """Fraction of expected doc_keys matched by at least one of the top-k retrieved doc_keys.

    Matters for multi-domain questions: hit@k is happy with one domain, recall@k wants all of them.
    """
    _require_expected(expected)
    top = retrieved[:k]
    found = sum(1 for e in expected if any(doc_key_matches(key, e) for key in top))
    return found / len(expected)


def mrr_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int = 10) -> float:
    """Reciprocal rank (1-based) of the first retrieved doc_key matching any expected key; 0.0 if none in top-k.

    Averaged over examples this is MRR. It rewards ranking quality, which is what a reranker would improve.
    """
    _require_expected(expected)
    for rank, key in enumerate(retrieved[:k], start=1):
        if _matches_any(key, expected):
            return 1.0 / rank
    return 0.0


# --- citations -------------------------------------------------------------------------------------------------

# Matches "[S1]", "[T2]" and grouped forms like "[S1, S3]" or "[S1][S2]".
_CITATION_GROUP = re.compile(r"\[\s*([ST]\d+(?:\s*[,;]\s*[ST]\d+)*)\s*\]")


def extract_citation_ids(answer: str) -> list[str]:
    """All citation ids in order of first appearance, deduplicated: "a [S2] b [S1, S2]" -> ["S2", "S1"]."""
    seen: dict[str, None] = {}
    for group in _CITATION_GROUP.findall(answer):
        for cid in re.split(r"\s*[,;]\s*", group):
            seen.setdefault(cid, None)
    return list(seen)


def citation_validity(answer: str, available_ids: Sequence[str]) -> float:
    """1.0 if the answer cites at least once and every cited id exists in the context/tool results, else 0.0.

    Binary on purpose: one invented [S7] is already a trust problem, partial credit would hide it.
    """
    cited = extract_citation_ids(answer)
    if not cited:
        return 0.0
    available = set(available_ids)
    return 1.0 if all(cid in available for cid in cited) else 0.0


def paragraph_citation_coverage(answer: str, min_chars: int = 40) -> float:
    """Share of factual paragraphs (>= min_chars, not a heading) that contain at least one citation.

    Implements "≥1 citation per factual paragraph" from the eval plan. Short lines and headings are skipped
    because "Your next steps:" is not a claim.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", answer) if p.strip()]
    factual = [p for p in paragraphs if len(p) >= min_chars and not p.startswith("#")]
    if not factual:
        return 0.0
    return sum(1 for p in factual if _CITATION_GROUP.search(p)) / len(factual)


def citation_correctness(cited_doc_keys: Sequence[str], expected_doc_keys: Sequence[str]) -> float:
    """Fraction of cited sources whose doc_key matches an expected source (required OR optional).

    Measures "did it cite the right law/page", not just "did it cite something that exists". 0.0 if nothing is cited.
    """
    if not cited_doc_keys:
        return 0.0
    return sum(1 for key in cited_doc_keys if _matches_any(key, expected_doc_keys)) / len(cited_doc_keys)


# --- string checks ---------------------------------------------------------------------------------------------


def _normalise(text: str) -> str:
    # Non-breaking / narrow spaces are common in German typography ("15 %", "€ 259").
    return re.sub(r"[\s  ]+", " ", text).casefold()


def contains_phrase(answer: str, phrase: str) -> bool:
    """Case-insensitive substring check where 'a|b|c' means any of the alternatives."""
    text = _normalise(answer)
    return any(_normalise(alt.strip()) in text for alt in phrase.split("|") if alt.strip())


def must_include_score(answer: str, must_include: Sequence[str]) -> float:
    """Fraction of must_include phrases present (1.0 if there are none)."""
    if not must_include:
        return 1.0
    return sum(1 for phrase in must_include if contains_phrase(answer, phrase)) / len(must_include)


def must_not_include_ok(answer: str, must_not_include: Sequence[str]) -> bool:
    return not any(contains_phrase(answer, phrase) for phrase in must_not_include)


# --- tools -----------------------------------------------------------------------------------------------------

ToolCallLike = ToolCallEvent | Mapping[str, Any]


def _call_name_args(call: ToolCallLike) -> tuple[str, Mapping[str, Any]]:
    if isinstance(call, ToolCallEvent):
        return call.name, call.args
    return str(call["name"]), call.get("args", {}) or {}


def _values_equal(expected: Any, actual: Any) -> bool:
    """Lenient equality for tool args: dates compare as ISO strings, dicts as subsets, numbers numerically."""
    if isinstance(actual, (date, datetime)):
        actual = actual.isoformat()
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        return args_subset_match(expected, actual)
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(expected) == float(actual)
    if isinstance(expected, str) and isinstance(actual, str):
        # A datetime arg ("2026-12-01T00:00:00") still matches the expected date "2026-12-01".
        return actual == expected or actual.startswith(expected + "T")
    return bool(expected == actual)


def args_subset_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    """True if every expected key is present in `actual` with an equal value. Extra actual args are fine."""
    return all(key in actual and _values_equal(value, actual[key]) for key, value in expected.items())


def tool_selection_correct(
    expected_tool: Mapping[str, Any] | None,
    actual_calls: Sequence[ToolCallLike],
) -> bool:
    """Plan definition: the expected tool was called with the expected arg subset; no tool when none was expected.

    `expected_tool` is `{"name": ..., "args_subset": {...}}` (GoldenExample.expected_tool dumped) or None.
    Any matching call counts, so a retry after a validation error ("needs: move_in_date") is not penalised.
    """
    if expected_tool is None:
        return len(actual_calls) == 0
    name = expected_tool["name"]
    subset = expected_tool.get("args_subset", {}) or {}
    for call in actual_calls:
        call_name, call_args = _call_name_args(call)
        if call_name == name and args_subset_match(subset, call_args):
            return True
    return False


# --- refusal ---------------------------------------------------------------------------------------------------

# Cheap heuristic used when no LLM judge is configured. The judge (judges.make_refusal_judge) is the real metric;
# this keeps offline runs meaningful and is easy to explain. It looks for an explicit FIRST-PERSON decline only:
# merely mentioning a lawyer or the Mieterverein is normal in good answers ("get advice from a Mieterverein"),
# and the generic "not legal advice" disclaimer appears in every answer.
_REFUSAL_PATTERNS = [
    r"\bI (?:can(?:'|no)?t|cannot|am not able to|'m not able to|am unable to) (?:help|advise|give|provide|prepare|"
    r"fill|assist)",
    r"\boutside (?:of )?(?:what I can|my scope)",
    r"\bich kann (?:ihnen |dir )?(?:dazu |hier |hierzu |dabei )?(?:nicht|keine)\b",
    r"\bkann ich (?:ihnen |dir )?(?:dazu |hier |hierzu |dabei )?(?:nicht|keine)\b",
]
_REFUSAL_RE = re.compile("|".join(_REFUSAL_PATTERNS), flags=re.IGNORECASE)


def looks_like_refusal(answer: str) -> bool:
    """Heuristic: does the answer decline and/or redirect to a professional?"""
    return bool(_REFUSAL_RE.search(answer))


def refusal_correct(should_refuse: bool, refused: bool) -> bool:
    """Refusal accuracy counts both directions: refuse the sensitive ones, answer the rest."""
    return should_refuse == refused


# --- aggregation helpers ---------------------------------------------------------------------------------------


def mean(values: Sequence[float]) -> float | None:
    """Mean, or None for an empty list (None renders as '–' in the report instead of a misleading 0)."""
    return statistics.fmean(values) if values else None


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank-with-interpolation percentile (q in 0..100). Stdlib only, matches numpy's default 'linear'."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q / 100
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)
