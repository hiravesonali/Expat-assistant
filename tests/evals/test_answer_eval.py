"""Answer eval with a fake pipeline and fake judges (no LLM)."""

import json
from pathlib import Path

from expat.evals.answer_eval import AnswerOutput, fold_events, run_answer_eval, score_answer
from expat.evals.dataset import DEFAULT_GOLDEN_PATH, by_id, load_golden
from expat.evals.judges import JudgeSet, JudgeVerdict
from expat.schemas import (
    AnswerMetaEvent,
    CitationsEvent,
    ContextSource,
    DoneEvent,
    RetrievalConfig,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserProfile,
)

EXAMPLES = by_id(load_golden(DEFAULT_GOLDEN_PATH))


def _ctx(source_id: str, doc_key: str) -> ContextSource:
    return ContextSource(
        source_id=source_id,
        parent_id=doc_key,
        chunk_ids=[f"{doc_key}:0"],
        doc_key=doc_key,
        title=doc_key,
        heading_path="",
        source_name="Gesetze im Internet",
        source_url="https://example.org",
        language="de",
        last_verified="2026-11-17",
        text="Die Kündigungsfrist verlängert sich nach fünf Jahren um drei Monate.",
    )


def _fake_judges(score: bool = True) -> JudgeSet:
    def verdict(key: str):
        return lambda **kwargs: JudgeVerdict(key=key, score=score, reasoning=f"{key} reasoning")

    return JudgeSet(groundedness=verdict("g"), correctness=verdict("c"), refusal=verdict("r"))


def test_fold_events_builds_answer_output() -> None:
    events = [
        StepEvent(name="retrieval", status="completed", detail={"sources": [_ctx("S1", "bgb#573c").model_dump()]}),
        ToolCallEvent(call_id="c1", name="calculate_tenancy_notice", args={"party": "landlord"}),
        ToolResultEvent(call_id="c1", name="calculate_tenancy_notice", result={"notice_period_months": 6}),
        TokenEvent(text="Six months "),
        TokenEvent(text="[S1][T1]."),
        CitationsEvent(citations=[]),
        AnswerMetaEvent(confidence="grounded"),
        DoneEvent(latency_ms=1200, input_tokens=1000, output_tokens=200),
    ]
    out = fold_events(events)
    assert out.answer == "Six months [S1][T1]."
    assert out.available_citation_ids() == ["S1", "T1"]
    assert out.cited_doc_keys() == ["bgb#573c"]
    assert out.latency_ms == 1200 and out.confidence == "grounded"
    assert "[T1] tool calculate_tenancy_notice" in out.context_text()


def test_score_answer_good_tenancy_answer() -> None:
    example = EXAMPLES["ten-001"]  # expects calculate_tenancy_notice(party=landlord), must_include 6 months + 573c
    output = AnswerOutput(
        answer="Your landlord must give 6 months' notice (§ 573c BGB) [S1][T1].",
        contexts=[_ctx("S1", "bgb#573c")],
        tool_calls=[ToolCallEvent(call_id="1", name="calculate_tenancy_notice", args={"party": "landlord"})],
        tool_results=[ToolResultEvent(call_id="1", name="calculate_tenancy_notice", result={"months": 6})],
        input_tokens=1000,
        output_tokens=100,
    )
    score = score_answer(example, output, _fake_judges(), price_per_mtok=(1.0, 4.0))
    m = score.metrics
    assert m["citation_validity"] == 1.0
    assert m["citation_correctness"] == 1.0
    assert m["must_include"] == 1.0
    assert m["tool_selection"] == 1.0
    assert m["groundedness"] == m["correctness"] == m["refusal_accuracy"] == 1.0
    assert m["total_tokens"] == 1100
    assert m["cost_usd"] == (1000 * 1.0 + 100 * 4.0) / 1_000_000


def test_score_answer_refusal_example_without_judges() -> None:
    example = EXAMPLES["oos-001"]
    refused = score_answer(example, AnswerOutput(answer="I can't give advice on asylum cases. Please see a lawyer."))
    assert refused.metrics["refusal_accuracy"] == 1.0
    assert refused.metrics["tool_selection"] == 1.0
    assert refused.metrics["citation_validity"] is None  # not applicable to refusals
    answered = score_answer(example, AnswerOutput(answer="File the appeal within two weeks at the court [S1]."))
    assert answered.metrics["refusal_accuracy"] == 0.0


def test_score_answer_error_counts_as_failure() -> None:
    score = score_answer(EXAMPLES["fam-001"], AnswerOutput(error="Timeout: openrouter"))
    assert score.error and score.metrics["must_include"] == 0.0 and score.metrics["refusal_accuracy"] == 0.0


def test_run_answer_eval_local_writes_json(tmp_path: Path) -> None:
    def factory(config: RetrievalConfig):
        def target(question: str, profile: UserProfile) -> AnswerOutput:
            example = next(e for e in EXAMPLES.values() if e.question == question)
            # A pipeline that just returns the reference answer, cited, without tools.
            return AnswerOutput(answer=example.reference_answer + " [S1]", contexts=[_ctx("S1", "bgb#573c")])

        return target

    variants = {"R0": RetrievalConfig.baseline()}
    [result] = run_answer_eval(factory, variants, split="holdout", judges=_fake_judges(), results_dir=tmp_path)
    data = json.loads(next(tmp_path.glob("answers-R0-holdout-*.json")).read_text(encoding="utf-8"))
    assert data["n"] == 12 and data["kind"] == "answers"
    assert data["metrics"]["must_include"] == 1.0
    assert data["metrics"]["groundedness"] == 1.0
    assert 0.0 < data["metrics"]["tool_selection"] < 1.0  # tool examples fail because the fake never calls tools
    assert data["per_slice"]["out_of_scope"]["refusal_accuracy"] == 1.0  # fake judge says correct
    assert data["per_slice"]["out_of_scope"]["groundedness"] is None
    assert result.config["judges"] is True


def test_fold_events_scores_the_citation_validated_answer_the_ui_shows() -> None:
    events = [
        TokenEvent(text="Three months [S1][S9]."),
        AnswerMetaEvent(confidence="grounded", final_answer="Three months [S1]."),
    ]
    assert fold_events(events).answer == "Three months [S1]."
    assert fold_events([TokenEvent(text="raw")]).answer == "raw"  # no meta event: fall back to the tokens


def test_failing_judge_keeps_the_free_metrics_and_records_the_error() -> None:
    """Regression: a judge blocked by the OpenRouter guardrail used to wipe the whole example's score."""

    def blocked(**kwargs):
        raise RuntimeError("Model blocked by guardrail")

    ok = _fake_judges()
    judges = JudgeSet(groundedness=blocked, correctness=ok.correctness, refusal=ok.refusal)
    output = AnswerOutput(
        answer="Your landlord must give 6 months' notice (§ 573c BGB) [S1].", contexts=[_ctx("S1", "bgb#573c")]
    )
    score = score_answer(EXAMPLES["ten-001"], output, judges)
    assert score.metrics["groundedness"] is None  # only the failing judge's metric is missing
    assert score.metrics["correctness"] == 1.0 and score.metrics["citation_validity"] == 1.0
    assert score.details["judge_errors"] == ["groundedness: RuntimeError: Model blocked by guardrail"]


def test_groundedness_judge_sees_question_and_profile() -> None:
    seen: dict[str, str] = {}

    def grounded(**kwargs):
        seen.update(kwargs)
        return JudgeVerdict(key="g", score=True)

    ok = _fake_judges()
    judges = JudgeSet(groundedness=grounded, correctness=ok.correctness, refusal=ok.refusal)
    output = AnswerOutput(answer="As a tenant in Munich: 6 months [S1].", contexts=[_ctx("S1", "bgb#573c")])
    score_answer(EXAMPLES["ten-001"], output, judges)
    assert seen["context"].startswith("[USER QUESTION]\n" + EXAMPLES["ten-001"].question)
    assert "[USER PROFILE]" in seen["context"] and "[S1]" in seen["context"]
