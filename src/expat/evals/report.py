"""Turn evals/results/*.json into markdown tables (printed and written to evals/results/REPORT.md).

Only the LATEST run per (kind, split, variant) is shown, so re-running a variant replaces its row while the old JSON
stays on disk as history. The tables are meant to be pasted into the README / review slides as they are.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from expat.evals.results import DEFAULT_RESULTS_DIR, ExperimentResult, MetricValue, load_results
from expat.evals.retrieval_eval import VARIANT_DESCRIPTIONS

PRIMARY_SLICES = ("bureaucracy", "tenancy", "family", "multi_domain", "out_of_scope")
REPORT_NAME = "REPORT.md"


def latest_runs(results: Sequence[ExperimentResult]) -> list[ExperimentResult]:
    """Keep the newest result per (kind, split, variant)."""
    latest: dict[tuple[str, str, str], ExperimentResult] = {}
    for result in results:
        key = (result.kind, result.split, result.variant)
        if key not in latest or result.created_at > latest[key].created_at:
            latest[key] = result
    return sorted(latest.values(), key=lambda r: (r.kind, r.split, _variant_order(r.variant)))


def _variant_order(variant: str) -> tuple[int, str]:
    """R0 < R1 < ... < R10, then anything else (e.g. "E-qwen3") alphabetically."""
    if variant[:1] == "R" and variant[1:].isdigit():
        return int(variant[1:]), ""
    return 10_000, variant


def fmt(value: MetricValue, *, digits: int = 2) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def fmt_ms(value: MetricValue) -> str:
    return "–" if value is None else f"{value:.0f}"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def render_retrieval_table(runs: Sequence[ExperimentResult]) -> str:
    """The ablation table: one row per variant, with the hit@5 delta against the R0 baseline."""
    baseline = next((r.metrics.get("hit@5") for r in runs if r.variant == "R0"), None)
    rows = []
    for r in runs:
        hit = r.metrics.get("hit@5")
        delta = "–" if baseline is None or hit is None else f"{hit - baseline:+.2f}"
        rows.append(
            [
                r.variant,
                VARIANT_DESCRIPTIONS.get(r.variant, ""),
                str(r.n),
                fmt(hit),
                delta,
                fmt(r.metrics.get("recall@10")),
                fmt(r.metrics.get("mrr@10")),
                fmt_ms(r.metrics.get("latency_p50_ms")),
                fmt_ms(r.metrics.get("latency_p95_ms")),
                str(r.errors),
            ]
        )
    header = ["Variant", "What", "n", "hit@5", "Δ hit@5 vs R0", "recall@10", "MRR@10", "p50 ms", "p95 ms", "errors"]
    return _table(header, rows)


def _slice_order(slice_name: str) -> tuple[int, str]:
    if slice_name in PRIMARY_SLICES:
        return PRIMARY_SLICES.index(slice_name), ""
    return len(PRIMARY_SLICES), slice_name


def render_per_slice_table(runs: Sequence[ExperimentResult], metric: str) -> str:
    """Slices as rows, variants as columns: shows WHERE a technique helps (e.g. BM25 on category:legal_lookup)."""
    slices = sorted({s for r in runs for s in r.per_slice}, key=_slice_order)
    rows = []
    for slice_name in slices:
        n_values = {int(v) for r in runs if (v := r.per_slice.get(slice_name, {}).get("n")) is not None}
        n = str(max(n_values)) if n_values else "–"
        rows.append([slice_name, n, *(fmt(r.per_slice.get(slice_name, {}).get(metric)) for r in runs)])
    return _table(["Slice", "n", *(r.variant for r in runs)], rows)


ANSWER_COLUMNS = (
    ("groundedness", "Faithful"),
    ("correctness", "Correct"),
    ("citation_validity", "Cit. valid"),
    ("citation_correctness", "Cit. correct"),
    ("must_include", "Must-incl."),
    ("tool_selection", "Tool sel."),
    ("refusal_accuracy", "Refusal acc."),
)


def render_answer_table(runs: Sequence[ExperimentResult]) -> str:
    rows = []
    for r in runs:
        cost = r.metrics.get("cost_usd")
        rows.append(
            [
                r.variant,
                str(r.n),
                *(fmt(r.metrics.get(key)) for key, _ in ANSWER_COLUMNS),
                fmt_ms(r.metrics.get("latency_p50_ms")),
                "–" if cost is None else f"${cost:.4f}",
            ]
        )
    return _table(["Variant", "n", *(label for _, label in ANSWER_COLUMNS), "p50 ms", "cost/answer"], rows)


def render_report(results: Sequence[ExperimentResult], now: datetime | None = None) -> str:
    """Full markdown report: per split, the retrieval ablation + per-slice hit@5, then the answer evals."""
    runs = latest_runs(results)
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    parts = [f"# Evaluation report\n\nGenerated {stamp} from `evals/results/*.json` (latest run per variant)."]
    if not runs:
        parts.append("No results yet. Run `uv run python -m expat.evals retrieval` first.")
        return "\n\n".join(parts) + "\n"

    for split in sorted({r.split for r in runs}):
        retrieval = [r for r in runs if r.kind == "retrieval" and r.split == split]
        answers = [r for r in runs if r.kind == "answers" and r.split == split]
        parts.append(f"## Split: {split}")
        if retrieval:
            parts.append("### Retrieval ablation\n\n" + render_retrieval_table(retrieval))
            parts.append("### hit@5 per slice\n\n" + render_per_slice_table(retrieval, "hit@5"))
            parts.append("### recall@10 per slice\n\n" + render_per_slice_table(retrieval, "recall@10"))
        if answers:
            parts.append("### Answer quality\n\n" + render_answer_table(answers))
            parts.append("### Correctness per slice\n\n" + render_per_slice_table(answers, "correctness"))
            parts.append("### Refusal accuracy per slice\n\n" + render_per_slice_table(answers, "refusal_accuracy"))
    return "\n\n".join(parts) + "\n"


def write_report(results_dir: Path = DEFAULT_RESULTS_DIR) -> tuple[Path, str]:
    text = render_report(load_results(results_dir))
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / REPORT_NAME
    path.write_text(text, encoding="utf-8")
    return path, text
