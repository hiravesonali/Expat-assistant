"""Spend guard: cost estimate and the budget check (no network)."""

import httpx

from expat.evals.budget import (
    ANSWER_CALLS,
    CORRECTNESS_CALL,
    GROUNDEDNESS_CALL,
    REFUSAL_CALL,
    check_budget,
    estimate_answer_eval,
    key_remaining_usd,
    model_price,
)
from expat.evals.dataset import DEFAULT_GOLDEN_PATH, load_golden

EXAMPLES = {e.id: e for e in load_golden(DEFAULT_GOLDEN_PATH)}
ANSWER, JUDGE = (0.40, 1.60), (0.10, 0.40)


def test_estimate_counts_judges_per_question_type() -> None:
    answerable, refusal, clarify = (
        EXAMPLES["ten-001"],
        EXAMPLES["oos-001"],
        next(e for e in EXAMPLES.values() if e.expect_clarification),
    )
    est = estimate_answer_eval([answerable, refusal, clarify], ["R5"], answer_price=ANSWER, judge_price=JUDGE)
    # answerable: refusal + correctness + groundedness; refusal question: refusal only; clarification: none
    assert (est.pipeline_runs, est.judge_calls) == (3, 4)
    expected_judges = 2 * REFUSAL_CALL.cost(JUDGE) + CORRECTNESS_CALL.cost(JUDGE) + GROUNDEDNESS_CALL.cost(JUDGE)
    assert abs(est.judges_usd - expected_judges) < 1e-12
    assert abs(est.answers_usd - 3 * ANSWER_CALLS.cost(ANSWER)) < 1e-12


def test_groundedness_only_for_chosen_variants_and_no_judge_mode() -> None:
    example = [EXAMPLES["ten-001"]]
    both = estimate_answer_eval(example, ["R0", "R5"], answer_price=ANSWER, judge_price=JUDGE)
    r5_only = estimate_answer_eval(
        example, ["R0", "R5"], answer_price=ANSWER, judge_price=JUDGE, groundedness_variants={"R5"}
    )
    free = estimate_answer_eval(example, ["R0", "R5"], answer_price=ANSWER, judge_price=None)
    assert both.judge_calls - r5_only.judge_calls == 1
    assert free.judges_usd == 0 and free.judge_calls == 0


def test_check_budget_stops_runs_that_do_not_fit() -> None:
    est = estimate_answer_eval([EXAMPLES["ten-001"]] * 100, ["R5"], answer_price=ANSWER, judge_price=JUDGE)
    assert check_budget(est, remaining=None) is None  # key without a limit
    assert check_budget(est, remaining=est.total_usd * 2) is None
    message = check_budget(est, remaining=est.total_usd)  # no headroom left
    assert message is not None and "--force" in message


def _client(payload: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))


def test_price_and_remaining_credit_parsing() -> None:
    models = {
        "data": [{"id": "google/gemini-2.5-flash-lite", "pricing": {"prompt": "0.0000001", "completion": "0.0000004"}}]
    }
    price = model_price("google/gemini-2.5-flash-lite", client=_client(models))
    assert price is not None and abs(price[0] - 0.10) < 1e-9 and abs(price[1] - 0.40) < 1e-9
    assert model_price("unknown/model", client=_client(models)) is None
    assert key_remaining_usd("k", client=_client({"data": {"limit_remaining": 3.5}})) == 3.5
    assert key_remaining_usd("k", client=_client({"data": {"limit_remaining": None}})) is None
