"""CLI parsing and the offline `report` command."""

from pathlib import Path

import pytest

from expat.evals.__main__ import _select, build_parser, main
from expat.evals.retrieval_eval import ablation_variants


def test_parser_defaults() -> None:
    args = build_parser().parse_args(["retrieval"])
    assert (args.split, args.mode, args.stretch) == ("dev", "local", False)
    assert build_parser().parse_args(["answers", "--split", "all"]).split is None


def test_parser_rejects_bad_split() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["retrieval", "--split", "test"])


def test_select_variants() -> None:
    assert list(_select(ablation_variants(), "R0,R4")) == ["R0", "R4"]
    with pytest.raises(SystemExit):
        _select(ablation_variants(), "R9")


def test_report_command_writes_markdown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["report", "--results-dir", str(tmp_path)]) == 0
    assert (tmp_path / "REPORT.md").exists()
    assert "Evaluation report" in capsys.readouterr().out
