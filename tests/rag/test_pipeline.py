"""Offline end-to-end tests of the event-streaming pipeline with fake models, retriever and tool."""

from datetime import date
from typing import Any

import pytest
from fakes import FakeRetriever, ScriptedChatModel, make_source, notice_period, tool_call_message
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from expat.rag import pipeline
from expat.rag.prompts import FEW_SHOT_EXAMPLES
from expat.rag.query_analysis import QueryAnalysis
from expat.schemas import (
    AnswerMetaEvent,
    CitationsEvent,
    DoneEvent,
    ErrorEvent,
    PipelineEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserProfile,
)

PROFILE = UserProfile(citizenship="non_eu", residence_status="blue_card", housing="renting")


class FakeAnalysisModel:
    """Duck-typed analysis model: `with_structured_output(...).invoke()` returns a canned result."""

    def __init__(self, analysis: QueryAnalysis | Exception) -> None:
        self.analysis = analysis
        self.calls = 0

    def with_structured_output(self, schema: type, **kwargs: Any) -> RunnableLambda:
        def _invoke(_: Any) -> dict[str, Any]:
            self.calls += 1
            if isinstance(self.analysis, Exception):
                raise self.analysis
            return {"raw": AIMessage("{}"), "parsed": self.analysis, "parsing_error": None}

        return RunnableLambda(_invoke)


def _analysis(example: int) -> QueryAnalysis:
    return QueryAnalysis.model_validate(FEW_SHOT_EXAMPLES[example].output)


def _run(question: str, analysis_llm: Any, answer_llm: Any, retriever: FakeRetriever | None = None, **kwargs: Any):
    events = list(
        pipeline.run(
            question,
            [("user", "Hi"), ("assistant", "Hello! How can I help?")],
            PROFILE,
            retriever=retriever or FakeRetriever(),
            analysis_llm=analysis_llm,
            answer_llm=answer_llm,
            tools=[notice_period],
            today=date(2026, 11, 17),
            **kwargs,
        )
    )
    return events


def _shape(events: list[PipelineEvent]) -> list[str]:
    """Event types (steps with name/status), with consecutive tokens collapsed into one entry."""
    shape: list[str] = []
    for event in events:
        label = f"step:{event.name}:{event.status}" if isinstance(event, StepEvent) else event.type
        if not (label == "token" and shape and shape[-1] == "token"):
            shape.append(label)
    return shape


def _text(events: list[PipelineEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, TokenEvent))


def test_normal_question_event_order():
    answer_llm = ScriptedChatModel(script=[AIMessage("You have to give notice in writing [S1].")])
    events = _run("How early do I tell my landlord I'm moving out?", FakeAnalysisModel(_analysis(1)), answer_llm)

    assert _shape(events) == [
        "step:query_analysis:started",
        "step:query_analysis:completed",
        "step:retrieval:started",
        "step:retrieval:completed",
        "step:generation:started",
        "token",
        "step:generation:completed",
        "citations",
        "answer_meta",
        "done",
    ]
    assert _text(events) == "You have to give notice in writing [S1]."
    analysis_step = events[1]
    assert analysis_step.detail["sub_questions"][0]["queries_de"] == [
        "Kündigungsfrist Mieter",
        "ordentliche Kündigung Mietvertrag durch Mieter",
    ]
    retrieval_step = events[3]
    assert retrieval_step.detail["sub_questions"][0]["top_hits"][0]["doc_key"] == "bgb#573c"
    citations = next(e for e in events if isinstance(e, CitationsEvent)).citations
    assert [c.id for c in citations] == ["S1"] and citations[0].legal_reference == "§ 573c BGB"
    meta = next(e for e in events if isinstance(e, AnswerMetaEvent))
    assert meta.confidence == "grounded" and meta.stale_sources == [] and meta.unverified_refs == []
    assert isinstance(events[-1], DoneEvent) and events[-1].latency_ms >= 0


def test_history_and_profile_reach_the_answer_model():
    answer_llm = ScriptedChatModel(script=[AIMessage("ok [S1]")])
    retriever = FakeRetriever()
    _run("Question?", FakeAnalysisModel(_analysis(1)), answer_llm, retriever)

    prompt = answer_llm.received[0]
    assert "residence: blue card" in prompt[0].content
    assert [m.type for m in prompt[1:]] == ["human", "ai", "human"]
    plan, profile, _ = retriever.calls[0]
    assert plan.sub_queries[0].queries_de[0] == "Kündigungsfrist Mieter" and profile == PROFILE


def test_tool_call_flow_emits_tool_events_and_t_citations():
    answer_llm = ScriptedChatModel(
        script=[
            tool_call_message("notice_period", {"tenancy_start": "2020-11-01", "notice_date": "2026-11-17"}),
            AIMessage("Your tenancy would end on 31 May 2027 [T1] under § 573c BGB [S1]. See also [S4]."),
        ]
    )
    events = _run("If my landlord gives notice today, when do I leave?", FakeAnalysisModel(_analysis(3)), answer_llm)

    shape = _shape(events)
    assert shape.index("tool_call") < shape.index("tool_result") < shape.index("token")
    call = next(e for e in events if isinstance(e, ToolCallEvent))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert call.name == "notice_period" and call.call_id == result.call_id
    assert result.result["end_date"] == "2027-05-31" and result.error is None

    citations = next(e for e in events if isinstance(e, CitationsEvent)).citations
    assert [(c.id, c.kind) for c in citations] == [("T1", "tool"), ("S1", "source")]
    generation = next(
        e for e in events if isinstance(e, StepEvent) and e.name == "generation" and e.status == "completed"
    )
    assert generation.detail["stripped_citations"] == ["S4"]
    assert "[S4]" not in generation.detail["answer"]
    meta = next(e for e in events if isinstance(e, AnswerMetaEvent))
    assert meta.confidence == "partial"  # a stripped citation lowers the confidence


def test_unverified_paragraph_is_flagged():
    answer_llm = ScriptedChatModel(script=[AIMessage("Under § 574 BGB you can object [S1].")])
    events = _run("Can I object?", FakeAnalysisModel(_analysis(1)), answer_llm)
    meta = next(e for e in events if isinstance(e, AnswerMetaEvent))
    assert meta.unverified_refs == ["§ 574"] and meta.confidence == "partial"


def test_stale_cited_source_is_reported():
    retriever = FakeRetriever([make_source(last_verified="2025-01-01")])
    answer_llm = ScriptedChatModel(script=[AIMessage("Yes [S1].")])
    events = _run("Question?", FakeAnalysisModel(_analysis(1)), answer_llm, retriever)
    assert next(e for e in events if isinstance(e, AnswerMetaEvent)).stale_sources == ["S1"]


def test_keyword_precheck_short_circuits_before_any_llm_call():
    analysis_llm = FakeAnalysisModel(_analysis(1))
    answer_llm = ScriptedChatModel(script=[])
    retriever = FakeRetriever()
    events = _run("My landlord filed a Räumungsklage against me", analysis_llm, answer_llm, retriever)

    assert _shape(events) == ["step:safety:completed", "token", "citations", "answer_meta", "done"]
    assert events[0].detail == {"category": "legal_dispute", "trigger": "keyword"}
    assert "mieterverein-muenchen.de" in _text(events)
    assert analysis_llm.calls == 0 and retriever.calls == [] and answer_llm.received == []


def test_sensitive_intent_short_circuits_after_analysis():
    retriever = FakeRetriever()
    events = _run(
        "What happens to my papers now?", FakeAnalysisModel(_analysis(5)), ScriptedChatModel(script=[]), retriever
    )
    assert _shape(events)[:3] == [
        "step:query_analysis:started",
        "step:query_analysis:completed",
        "step:safety:completed",
    ]
    assert events[2].detail["trigger"] == "analysis" and retriever.calls == []
    assert next(e for e in events if isinstance(e, AnswerMetaEvent)).confidence == "insufficient"


@pytest.mark.parametrize(("example", "expected_start"), [(6, "Sorry"), (0, None)])
def test_out_of_scope_short_circuits(example, expected_start):
    answer_llm = ScriptedChatModel(script=[AIMessage("Register at the KVR [S1].")])
    events = _run("Question?", FakeAnalysisModel(_analysis(example)), answer_llm)
    if expected_start:
        assert _text(events).startswith(expected_start)
    else:
        assert "step:retrieval:completed" in _shape(events)


def test_analysis_failure_falls_back_to_raw_question():
    retriever = FakeRetriever()
    answer_llm = ScriptedChatModel(script=[AIMessage("Answer [S1].")])
    events = _run("Wie melde ich mich an?", FakeAnalysisModel(RuntimeError("model down")), answer_llm, retriever)

    analysis_step = events[1]
    assert analysis_step.detail["fallback"] is True and "RuntimeError" in analysis_step.detail["fallback_reason"]
    plan = retriever.calls[0][0]
    assert plan.standalone_question == "Wie melde ich mich an?" and plan.sub_queries[0].queries_de == []
    assert isinstance(events[-1], DoneEvent)


def test_retrieval_error_becomes_error_event():
    retriever = FakeRetriever(error=ConnectionError("chroma unreachable"))
    events = _run("Question?", FakeAnalysisModel(_analysis(1)), ScriptedChatModel(script=[]), retriever)

    assert _shape(events)[-2:] == ["step:retrieval:failed", "error"]
    error = events[-1]
    assert isinstance(error, ErrorEvent)
    assert error.code == "retrieval_failed" and error.retryable is True and "chroma" in error.message


def test_no_sources_gives_insufficient_confidence():
    answer_llm = ScriptedChatModel(script=[AIMessage("I couldn't find this in my official sources.")])
    events = _run("Question?", FakeAnalysisModel(_analysis(1)), answer_llm, FakeRetriever(sources=[]))
    assert next(e for e in events if isinstance(e, AnswerMetaEvent)).confidence == "insufficient"


def test_profile_metadata_contains_only_enums():
    metadata = pipeline.profile_metadata(PROFILE)
    assert metadata["profile_residence_status"] == "blue_card" and metadata["profile_city"] == "munich"
    assert pipeline.profile_metadata(None) == {"profile": "none"}


def test_load_pending_changes(tmp_path):
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        "pending_changes:\n  - Plain note\n  - {title: Elterngeld reform, note: births from 2027-11}\n",
        encoding="utf-8",
    )
    assert pipeline.load_pending_changes(rules) == ("Plain note", "Elterngeld reform – births from 2027-11")
    assert pipeline.load_pending_changes(tmp_path / "missing.yaml") == ()


def test_build_default_pipeline_is_importable():
    assert callable(pipeline.build_default_pipeline)
