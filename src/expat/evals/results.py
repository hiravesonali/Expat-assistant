"""The local result file format shared by the retrieval and answer runners (and read by report.py).

Why local JSON at all when LangSmith stores experiments? The LangSmith free tier keeps data for 14 days; the review
is later than that. `evals/results/<experiment>.json` is the durable record, committed to git if you want.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from expat.config import REPO_ROOT
from expat.evals.dataset import GoldenExample
from expat.evals.metrics import mean, percentile

DEFAULT_RESULTS_DIR = REPO_ROOT / "evals" / "results"

MetricValue = float | None


class ExampleScore(BaseModel):
    """Per-example metrics, kept in the JSON so you can inspect failures without LangSmith."""

    id: str
    metrics: dict[str, MetricValue]
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)  # e.g. retrieved doc_keys, judge reasoning


class ExperimentResult(BaseModel):
    """One experiment = one variant on one split. Required keys per the eval plan + a few extras for the report."""

    experiment: str
    kind: Literal["retrieval", "answers"]
    variant: str
    split: str
    config: dict[str, Any]
    metrics: dict[str, MetricValue]
    per_slice: dict[str, dict[str, MetricValue]]
    n: int
    errors: int = 0
    created_at: datetime
    mode: Literal["local", "langsmith"] = "local"
    dataset: str = ""
    langsmith_experiment: str | None = None
    per_example: list[ExampleScore] = Field(default_factory=list)


def experiment_name(kind: str, variant: str, split: str, now: datetime | None = None) -> str:
    """`retrieval-R4-dev-20261117T143000Z`: sortable, unique per run, safe as a file name."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{kind}-{variant}-{split}-{stamp}"


def aggregate(
    scores: Sequence[ExampleScore],
    examples_by_id: dict[str, GoldenExample],
    metric_names: Sequence[str],
) -> tuple[dict[str, MetricValue], dict[str, dict[str, MetricValue]]]:
    """Mean of every metric overall and per slice/tag; latency as p50/p95.

    A metric that is None for an example (e.g. groundedness for a refusal case) is left out of that mean rather
    than counted as 0, so each metric is averaged only over the examples it applies to.
    """

    def summarise(subset: Sequence[ExampleScore]) -> dict[str, MetricValue]:
        out: dict[str, MetricValue] = {}
        for name in metric_names:
            out[name] = mean([v for s in subset if (v := s.metrics.get(name)) is not None])
        latencies = [s.latency_ms for s in subset if s.latency_ms is not None]
        out["latency_p50_ms"] = percentile(latencies, 50)
        out["latency_p95_ms"] = percentile(latencies, 95)
        out["n"] = float(len(subset))
        return out

    overall = summarise(scores)
    overall.pop("n")
    tags: dict[str, list[ExampleScore]] = {}
    for score in scores:
        for tag in examples_by_id[score.id].tags():
            tags.setdefault(tag, []).append(score)
    per_slice = {tag: summarise(subset) for tag, subset in sorted(tags.items())}
    return overall, per_slice


def write_result(result: ExperimentResult, results_dir: Path = DEFAULT_RESULTS_DIR) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{result.experiment}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_results(results_dir: Path = DEFAULT_RESULTS_DIR) -> list[ExperimentResult]:
    """All experiment files in the directory, oldest first (file names sort by timestamp)."""
    if not results_dir.exists():
        return []
    return [
        ExperimentResult.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(results_dir.glob("*.json"))
    ]
