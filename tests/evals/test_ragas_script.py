"""scripts/ragas_eval.py: the pure helpers (filtering, cost estimate, comparison). No Ragas install, no API."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ragas_eval.py"
_spec = importlib.util.spec_from_file_location("ragas_eval", SCRIPT)
assert _spec and _spec.loader
ragas_eval = importlib.util.module_from_spec(_spec)
sys.modules["ragas_eval"] = ragas_eval  # dataclasses need the module registered
_spec.loader.exec_module(ragas_eval)

OVERHEAD = {"statements": 400, "nli": 800, "precision": 1000, "recall": 1400}


def _record(id_: str = "ten-001", **kw) -> dict:
    base = {
        "id": id_,
        "question": "How long is the notice period?",
        "answer": "Three months [S1].",
        "reference": "Three months for tenants (§ 573c BGB).",
        "profile": {"city": "munich"},
        "retrieved_contexts": ["[S1] BGB § 573c\n" + "x" * 350, "[S2] other\n" + "y" * 700],
        "tool_contexts": ["[T1] tool notice\n{}"],
        "should_refuse": False,
        "expect_clarification": False,
        "asked_clarification": False,
        "error": None,
        "ours": {"groundedness": 1.0, "correctness": 1.0},
    }
    return base | kw


def test_importing_the_script_does_not_need_ragas() -> None:
    # Ragas is not installed in the project env; the module import above must not have needed it.
    assert "ragas" not in sys.modules
    assert ragas_eval.METRICS == ("faithfulness", "context_precision", "context_recall")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({}, None),
        ({"error": "Boom"}, "pipeline error"),
        ({"should_refuse": True}, "refusal question"),
        ({"asked_clarification": True}, "clarification"),
        ({"answer": "  "}, "empty answer"),
        ({"retrieved_contexts": []}, "no retrieved sources"),
    ],
)
def test_skip_reason(changes: dict, reason: str | None) -> None:
    assert ragas_eval.skip_reason(_record(**changes)) == reason


def test_faithfulness_sees_question_profile_sources_and_tools_like_our_judge() -> None:
    evidence = ragas_eval.faithfulness_evidence(_record())
    assert evidence[0].startswith("[USER QUESTION]\nHow long is the notice period?")
    assert "[USER PROFILE]" in evidence[0] and '"munich"' in evidence[0]
    assert evidence[1].startswith("[S1]") and evidence[-1].startswith("[T1]")


def test_estimate_counts_one_precision_call_per_source() -> None:
    record = _record()
    only_precision = ragas_eval.estimate([record], OVERHEAD, ("context_precision",))
    assert only_precision.calls == 2  # two retrieved sources
    full = ragas_eval.estimate([record, record], OVERHEAD)
    assert full.calls == 2 * (2 + 2 + 1)  # faithfulness 2, precision 1 per source, recall 1
    # The fixed prompt sizes dominate short samples: at least overheads x calls.
    assert full.input_tokens > 2 * (400 + 800 + 2 * 1000 + 1400)
    assert full.usd((0.10, 0.40)) == pytest.approx((full.input_tokens * 0.10 + full.output_tokens * 0.40) / 1_000_000)


def test_compare_agreement_and_disagreements() -> None:
    rows = [
        {"id": "a", "faithfulness": 1.0, "ours_groundedness": 1.0, "context_recall": 1.0, "ours_correctness": 1.0},
        {"id": "b", "faithfulness": 0.5, "ours_groundedness": 0.0, "context_recall": 0.2, "ours_correctness": 0.0},
        {"id": "c", "faithfulness": 0.6, "ours_groundedness": 1.0, "context_recall": 0.8, "ours_correctness": 1.0},
        {"id": "d", "faithfulness": None, "ours_groundedness": 1.0, "context_recall": None, "ours_correctness": None},
    ]
    cmp = ragas_eval.compare(rows)
    assert cmp["groundedness_pairs"] == 3  # d has no Ragas score
    assert cmp["groundedness_agreement"] == pytest.approx(2 / 3)
    assert [d["id"] for d in cmp["groundedness_disagreements"]] == ["c"]
    assert cmp["faithfulness_when_ours_grounded"] == pytest.approx(0.8)
    assert cmp["context_recall_when_ours_incorrect"] == pytest.approx(0.2)


def test_render_markdown_lists_every_answer() -> None:
    rows = [{"id": "ten-001", "faithfulness": 0.9, "ours_groundedness": 1.0, "ours_correctness": 1.0}]
    result = {
        "config": {"samples": "s.jsonl", "model": "m", "ragas_version": "0.4.4", "metrics": ["faithfulness"]},
        "n_scored": 1,
        "n_skipped": 2,
        "means": {"faithfulness": 0.9},
        "comparison": ragas_eval.compare(rows),
        "usage": {"cost_usd": 0.0012, "calls": 2},
        "per_example": rows,
    }
    md = ragas_eval.render_markdown(result)
    assert "| faithfulness | 0.90 |" in md and "| ten-001 | 0.90 | – | – | 1.00 | 1.00 |" in md


def test_cache_folder_is_per_model() -> None:
    a = ragas_eval.cache_dir_for("google/gemini-2.5-flash-lite")
    b = ragas_eval.cache_dir_for("anthropic/claude-haiku-4.5")
    assert a != b and a.parent == b.parent and "/" not in a.name


def test_newest_samples(tmp_path: Path) -> None:
    for stamp in ("20261123T100000Z", "20261124T090000Z"):
        (tmp_path / f"answers-R5-holdout-{stamp}.jsonl").write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    newest = ragas_eval.newest_samples(tmp_path)
    assert newest.name.endswith("20261124T090000Z.jsonl")
    assert ragas_eval.load_samples(newest)[0]["id"] == "ten-001"
    with pytest.raises(SystemExit, match="--samples"):
        ragas_eval.newest_samples(tmp_path / "empty")
