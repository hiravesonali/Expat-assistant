"""The demo pipeline must speak exactly the event contract the real pipeline will speak."""

from datetime import date

import pytest
from demo_pipeline import DemoRetriever, demo_analyze, demo_run, demo_tenancy_notice
from pydantic import TypeAdapter

from expat.schemas import (
    AnswerMetaEvent,
    CitationsEvent,
    DoneEvent,
    ErrorEvent,
    PipelineEvent,
    RetrievalConfig,
    RetrievalPlan,
    StepEvent,
    SubQuestionResult,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserProfile,
)

TENANCY_Q = "I rent a flat in Munich since 2021. If I give notice today, when does my tenancy end?"
ANMELDUNG_Q = "I just moved to Munich. What do I need for the Anmeldung, and by when?"
GENERIC_Q = "What is the capital of France?"

EVENT_ADAPTER = TypeAdapter(PipelineEvent)


def _run(question: str) -> list:
    return list(demo_run(question, [], UserProfile(), delay=0, today=date(2026, 11, 17)))


@pytest.mark.parametrize("question", [TENANCY_Q, ANMELDUNG_Q, GENERIC_Q])
def test_events_round_trip_through_the_schema(question):
    for ev in _run(question):
        # Serialise + parse via the discriminated union, as a future SSE layer would.
        parsed = EVENT_ADAPTER.validate_json(ev.model_dump_json())
        assert parsed == ev


def _kinds(events) -> list[str]:
    out = []
    for ev in events:
        kind = f"{ev.type}:{ev.name}:{ev.status}" if isinstance(ev, StepEvent) else ev.type
        if not out or out[-1] != kind:  # collapse token runs
            out.append(kind)
    return out


def test_tenancy_event_order():
    assert _kinds(_run(TENANCY_Q)) == [
        "step:query_analysis:started",
        "step:query_analysis:completed",
        "step:retrieval:started",
        "step:retrieval:completed",
        "step:tool_call:started",
        "tool_call",
        "tool_result",
        "step:tool_call:completed",
        "step:generation:started",
        "token",
        "step:generation:completed",
        "citations",
        "answer_meta",
        "done",
    ]


def test_tenancy_tool_call_and_citations():
    events = _run(TENANCY_Q)
    call = next(e for e in events if isinstance(e, ToolCallEvent))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert call.name == "calculate_tenancy_notice" == result.name
    assert call.call_id == result.call_id
    assert result.result["notice_period_months"] == 3

    citations = next(e for e in events if isinstance(e, CitationsEvent)).citations
    assert citations[0].legal_reference.startswith("§ 573c")
    assert {c.id for c in citations} == {"S1", "S2", "T1"}

    answer = "".join(e.text for e in events if isinstance(e, TokenEvent))
    for c in citations:
        assert f"[{c.id}]" in answer  # every citation is referenced in the text
    assert next(e for e in events if isinstance(e, AnswerMetaEvent)).confidence == "grounded"


def test_step_details_match_the_retrieval_contracts():
    events = _run(TENANCY_Q)
    qa = next(e for e in events if isinstance(e, StepEvent) and e.name == "query_analysis" and e.detail)
    plan = RetrievalPlan.model_validate({k: v for k, v in qa.detail.items() if k in RetrievalPlan.model_fields})
    assert plan.sub_queries[0].queries_de

    ret = next(e for e in events if isinstance(e, StepEvent) and e.name == "retrieval" and e.detail)
    subs = [SubQuestionResult.model_validate(s) for s in ret.detail["sub_results"]]
    assert subs[0].hits[0].metadata.doc_key == "bgb#573c"


def test_generic_fallback_is_insufficient_and_uncited():
    events = _run(GENERIC_Q)
    assert next(e for e in events if isinstance(e, AnswerMetaEvent)).confidence == "insufficient"
    assert next(e for e in events if isinstance(e, CitationsEvent)).citations == []
    assert isinstance(events[-1], DoneEvent)


def test_anmeldung_is_grounded_and_fresh():
    meta = next(e for e in _run(ANMELDUNG_Q) if isinstance(e, AnswerMetaEvent))
    assert meta.confidence == "grounded"
    assert meta.stale_sources == []  # both Anmeldung sources are fresh


def test_simulated_error_is_last_and_retryable():
    events = _run("simulate error please")
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].retryable
    assert not any(isinstance(e, TokenEvent) for e in events)


def test_retriever_honours_baseline_flags():
    plan = demo_analyze(TENANCY_Q)
    full = DemoRetriever().retrieve(plan, UserProfile(), RetrievalConfig())
    r0 = DemoRetriever().retrieve(plan, UserProfile(), RetrievalConfig.baseline())

    assert len(full.sub_results) == 2 and len(r0.sub_results) == 1
    assert r0.sub_results[0].where is None and full.sub_results[0].where is not None
    r0_lists = {name for hit in r0.sub_results[0].hits for name in hit.ranks}
    assert all(name.startswith("dense:en") for name in r0_lists)
    full_lists = {name for hit in full.sub_results[0].hits for name in hit.ranks}
    assert any(name.startswith("bm25:de") for name in full_lists)
    assert [p.source_id for p in full.parents] == [f"S{i}" for i in range(1, len(full.parents) + 1)]


@pytest.mark.parametrize(
    ("notice", "in_time", "end"),
    [
        (date(2026, 11, 4), True, "2027-01-31"),  # Wed 4 Nov = 3rd working day -> in time
        (date(2026, 11, 17), False, "2027-02-28"),
    ],
)
def test_tenancy_notice_third_working_day(notice, in_time, end):
    res = demo_tenancy_notice(notice, date(2021, 3, 1))
    assert res["received_in_time_for_this_month"] is in_time
    assert res["tenancy_end_date"] == end
