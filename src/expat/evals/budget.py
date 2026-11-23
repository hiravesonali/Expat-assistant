"""Spend guard for paid eval runs: estimate the cost up front and stop if the key's remaining credit can't cover it.

Why: on 2026-11-23 a full answer eval hit the OpenRouter key limit mid-run, which wasted the calls already made
and left a broken result. Token profiles below are the measured averages of that day (LangSmith traces), with
the judge output lowered for the short-reasoning prompts (judges-v2).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

import httpx

from expat.evals.dataset import GoldenExample

OPENROUTER = "https://openrouter.ai/api/v1"
SAFETY_FACTOR = 1.25  # estimates are averages; leave headroom for long answers and retries


@dataclass(frozen=True)
class CallProfile:
    """Average tokens of one call."""

    input_tokens: int
    output_tokens: int

    def cost(self, price: tuple[float, float]) -> float:
        """price = (USD per 1M input tokens, USD per 1M output tokens)."""
        return (self.input_tokens * price[0] + self.output_tokens * price[1]) / 1_000_000


# Measured 2026-11-23: answer pipeline (query analysis + answer agent) ~10.3k in / 555 out per question;
# groundedness judge 6.65k in, correctness 1.42k, refusal 1.39k. Outputs: short-reasoning targets.
ANSWER_CALLS = CallProfile(10_300, 560)
GROUNDEDNESS_CALL = CallProfile(6_700, 150)
CORRECTNESS_CALL = CallProfile(1_450, 120)
REFUSAL_CALL = CallProfile(1_400, 100)


@dataclass(frozen=True)
class CostEstimate:
    answers_usd: float
    judges_usd: float
    pipeline_runs: int
    judge_calls: int

    @property
    def total_usd(self) -> float:
        return self.answers_usd + self.judges_usd


def estimate_answer_eval(
    examples: Sequence[GoldenExample],
    variants: Collection[str],
    *,
    answer_price: tuple[float, float],
    judge_price: tuple[float, float] | None,
    groundedness_variants: Collection[str] | None = None,
) -> CostEstimate:
    """Cost of `run_answer_eval` for these examples and variants. judge_price=None means --no-judge."""
    answers = judges = 0.0
    runs = calls = 0
    for variant in variants:
        grounded = groundedness_variants is None or variant in groundedness_variants
        for example in examples:
            runs += 1
            answers += ANSWER_CALLS.cost(answer_price)
            if judge_price is None or example.expect_clarification:
                continue  # clarification items stop before any judge (see score_answer)
            calls += 1
            judges += REFUSAL_CALL.cost(judge_price)
            if not example.should_refuse:
                calls += 1
                judges += CORRECTNESS_CALL.cost(judge_price)
                if grounded:
                    calls += 1
                    judges += GROUNDEDNESS_CALL.cost(judge_price)
    return CostEstimate(answers_usd=answers, judges_usd=judges, pipeline_runs=runs, judge_calls=calls)


def model_price(model: str, client: httpx.Client | None = None) -> tuple[float, float] | None:
    """(USD per 1M input, per 1M output) from OpenRouter's public model list; None if the model is unknown."""
    http = client or httpx.Client(timeout=30)
    for row in http.get(f"{OPENROUTER}/models").json().get("data", []):
        if row.get("id") == model:
            pricing = row.get("pricing", {})
            return float(pricing.get("prompt", 0)) * 1e6, float(pricing.get("completion", 0)) * 1e6
    return None


def key_remaining_usd(api_key: str, client: httpx.Client | None = None) -> float | None:
    """Remaining credit on the key's own limit, or None if the key has no limit (or the check failed)."""
    http = client or httpx.Client(timeout=30)
    try:
        data = http.get(f"{OPENROUTER}/key", headers={"Authorization": f"Bearer {api_key}"}).json().get("data", {})
    except (httpx.HTTPError, ValueError):
        return None
    remaining = data.get("limit_remaining")
    return None if remaining is None else float(remaining)


def check_budget(estimate: CostEstimate, remaining: float | None) -> str | None:
    """An error message if the run would not fit into the remaining credit (with headroom), else None."""
    if remaining is None:
        return None
    needed = estimate.total_usd * SAFETY_FACTOR
    if needed > remaining:
        return (
            f"estimated cost ${estimate.total_usd:.2f} (x{SAFETY_FACTOR} headroom = ${needed:.2f}) exceeds the key's "
            f"remaining credit ${remaining:.2f}. Run fewer questions (--ids, --split) or variants, top up the key, "
            "or pass --force."
        )
    return None
