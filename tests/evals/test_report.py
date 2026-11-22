"""Report rendering from hand-made result files."""

from datetime import UTC, datetime
from pathlib import Path

from expat.evals.report import latest_runs, render_report, write_report
from expat.evals.results import ExperimentResult, write_result


def _result(
    variant: str, hit: float, *, kind: str = "retrieval", minute: int = 0, **metrics: float
) -> ExperimentResult:
    created = datetime(2026, 11, 17, 12, minute, tzinfo=UTC)
    base = {"hit@5": hit, "recall@10": hit, "mrr@10": hit / 2, "latency_p50_ms": 120.4, "latency_p95_ms": 300.0}
    return ExperimentResult(
        experiment=f"{kind}-{variant}-dev-{minute}",
        kind=kind,  # type: ignore[arg-type]
        variant=variant,
        split="dev",
        config={},
        metrics={**base, **metrics},
        per_slice={
            "tenancy": {"hit@5": hit, "n": 8.0},
            "category:legal_lookup": {"hit@5": hit / 2, "n": 9.0},
            "bureaucracy": {"hit@5": 1.0, "n": 8.0},
        },
        n=25,
        created_at=created,
    )


def test_latest_runs_keeps_newest_per_variant_and_sorts_naturally() -> None:
    runs = latest_runs([_result("R10", 0.9), _result("R1", 0.5), _result("R1", 0.6, minute=5), _result("R0", 0.4)])
    assert [(r.variant, r.metrics["hit@5"]) for r in runs] == [("R0", 0.4), ("R1", 0.6), ("R10", 0.9)]


def test_render_report_tables() -> None:
    text = render_report([_result("R0", 0.5), _result("R4", 0.86)], now=datetime(2026, 11, 17, tzinfo=UTC))
    assert "## Split: dev" in text
    # leak@10 is "–": fake runs carry no metadata
    r0_row = (
        "| R0 | Vector only, raw query, no filters (baseline) | 25 | 0.50 | +0.00 | 0.50 | 0.25 | – | 120 | 300 | 0 |"
    )
    assert r0_row in text
    assert "| R4 | R3 + BM25 hybrid | 25 | 0.86 | +0.36 |" in text
    # per-slice: primary slices first in fixed order, then cross-cutting tags
    lines = text.splitlines()
    i_bur = lines.index("| bureaucracy | 8 | 1.00 | 1.00 |")
    i_ten = lines.index("| tenancy | 8 | 0.50 | 0.86 |")
    i_legal = lines.index("| category:legal_lookup | 9 | 0.25 | 0.43 |")
    assert i_bur < i_ten < i_legal


def test_render_answer_section_and_missing_values() -> None:
    answers = _result("R5", 0.0, kind="answers", groundedness=0.93, refusal_accuracy=1.0, cost_usd=0.0021)
    text = render_report([answers])
    assert "### Answer quality" in text
    assert "| R5 | 25 | 0.93 | – |" in text  # correctness missing -> dash, not 0
    assert "$0.0021" in text


def test_write_report_reads_json_and_writes_markdown(tmp_path: Path) -> None:
    write_result(_result("R0", 0.5), tmp_path)
    write_result(_result("R5", 0.9), tmp_path)
    path, text = write_report(tmp_path)
    assert path == tmp_path / "REPORT.md"
    assert path.read_text(encoding="utf-8") == text
    assert "| R5 |" in text


def test_empty_results_dir(tmp_path: Path) -> None:
    _, text = write_report(tmp_path / "missing")
    assert "No results yet" in text
