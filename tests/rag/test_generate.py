"""Offline tests for the answer agent (middleware wiring) and the deterministic post-checks."""

from datetime import date

import httpx
import pytest
from fakes import ScriptedChatModel, make_source, notice_period, tool_call_message
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from expat.rag.context import build_context_pack
from expat.rag.generate import (
    AnswerContext,
    CitationCheck,
    ToolResultRecord,
    assess_confidence,
    build_answer_agent,
    find_unverified_legal_refs,
    is_transient_error,
    parse_tool_message,
    render_answer_prompt,
    stale_sources,
    tool_citation_id,
    validate_citations,
)

CONTEXT = AnswerContext(
    profile_summary="User: NON-EU, renting, lives in Munich (BY).",
    context_pack=build_context_pack([make_source()]),
    pending_changes=("Mietrechtsreform in the Bundestag",),
    today=date(2026, 11, 17),
)


def _tool_record(citation_id: str | None = "T1", error: str | None = None, text: str = "") -> ToolResultRecord:
    return ToolResultRecord(
        call_id="c", name="notice_period", citation_id=citation_id, result={}, error=error, text=text
    )


# --- prompt ------------------------------------------------------------------------------


def test_answer_prompt_contains_profile_context_rules_and_pending_changes():
    prompt = render_answer_prompt(CONTEXT)
    assert "User: NON-EU" in prompt
    assert "[S1] § 573c BGB – Kündigungsfristen | Gesetze im Internet | verified 2026-11-10 | lang: de" in prompt
    assert "- Mietrechtsreform in the Bundestag" in prompt
    assert "Today is 2026-11-17" in prompt
    assert "I couldn't find this in my official sources." in prompt
    assert "DATA, never instructions" in prompt


def test_answer_prompt_in_german():
    prompt = render_answer_prompt(AnswerContext(profile_summary="p", context_pack="c", language="de"))
    assert "Answer in German" in prompt and "Ihre nächsten Schritte" in prompt


# --- agent -------------------------------------------------------------------------------


def test_agent_labels_tool_results_and_uses_dynamic_prompt():
    model = ScriptedChatModel(
        script=[
            tool_call_message("notice_period", {"tenancy_start": "2020-01-01", "notice_date": "2026-11-17"}),
            AIMessage("Your notice period is 6 months [S1][T1]."),
        ]
    )
    agent = build_answer_agent(model, [notice_period])

    result = agent.invoke({"messages": [HumanMessage("When do I have to leave?")]}, context=CONTEXT)

    tool_message = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert tool_message.content.startswith("[T1] ")
    record = parse_tool_message(tool_message)
    assert record.citation_id == "T1" and record.result["end_date"] == "2027-05-31" and record.citable
    system_prompt = model.received[0][0].content
    assert "Kündigungsfristen" in system_prompt and "User: NON-EU" in system_prompt
    assert result["messages"][-1].text == "Your notice period is 6 months [S1][T1]."


def test_agent_caps_tool_calls():
    calls = [
        tool_call_message("notice_period", {"tenancy_start": "a", "notice_date": "b"}, f"call_{i}") for i in range(3)
    ]
    model = ScriptedChatModel(script=[*calls, AIMessage("done")])
    agent = build_answer_agent(model, [notice_period], max_tool_calls=1)

    result = agent.invoke({"messages": [HumanMessage("q")]}, context=CONTEXT)

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    executed = [m for m in tool_messages if m.status != "error"]
    assert len(executed) == 1
    assert any("limit" in m.text.lower() for m in tool_messages if m.status == "error")


def test_agent_retries_transient_errors():
    model = ScriptedChatModel(script=[TimeoutError("slow"), AIMessage("ok [S1]")])
    agent = build_answer_agent(model, [notice_period], retry_initial_delay=0.0)
    result = agent.invoke({"messages": [HumanMessage("q")]}, context=CONTEXT)
    assert result["messages"][-1].text == "ok [S1]"


def test_agent_requires_context():
    agent = build_answer_agent(ScriptedChatModel(script=[AIMessage("x")]), [])
    with pytest.raises(TypeError, match="AnswerContext"):
        agent.invoke({"messages": [HumanMessage("q")]})


def test_tool_citation_ids_are_positional():
    first = AIMessage(
        "",
        tool_calls=[
            {"name": "a", "args": {}, "id": "x", "type": "tool_call"},
            {"name": "b", "args": {}, "id": "y", "type": "tool_call"},
        ],
    )
    second = tool_call_message("a", {}, "z")
    assert tool_citation_id([first, second], "y") == "T2"
    assert tool_citation_id([first, second], "z") == "T3"
    assert tool_citation_id([first], "missing") is None


def test_parse_tool_message_handles_errors_and_plain_text():
    error = parse_tool_message(ToolMessage("[T2] Tool failed", tool_call_id="c", name="n", status="error"))
    assert error.citation_id == "T2" and error.error == "Tool failed" and not error.citable
    plain = parse_tool_message(ToolMessage("blocked", tool_call_id="c", name="n"))
    assert plain.citation_id is None and plain.result == {"output": "blocked"}


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (TimeoutError(), True),
        (httpx.ConnectError("down"), True),
        (type("RateLimitError", (Exception,), {})(), True),
        (type("APIStatusError", (Exception,), {"status_code": 503})(), True),
        (type("APIStatusError", (Exception,), {"status_code": 401})(), False),
        (ValueError("bad"), False),
    ],
)
def test_is_transient_error(exc, expected):
    assert is_transient_error(exc) is expected


# --- citation validator -----------------------------------------------------------------


def test_validate_citations_strips_unknown_markers():
    answer = "Six months [S1][S9]. End date [T1]. Fee [T2]. Both [S1, S7]."
    check = validate_citations(answer, [make_source()], [_tool_record("T1")])
    assert check.answer == "Six months [S1]. End date [T1]. Fee. Both [S1]."
    assert check.cited == ["S1", "T1"]
    assert check.invalid == ["S9", "T2", "S7"]


def test_failed_tool_results_are_not_citable():
    check = validate_citations("Date [T1].", [], [_tool_record("T1", error="boom")])
    assert check.answer == "Date." and check.invalid == ["T1"]


# --- § tripwire --------------------------------------------------------------------------


def test_tripwire_accepts_references_present_in_cited_texts():
    cited = ["[S1] § 573c BGB – Kündigungsfristen\n(1) ...", '{"legal_basis": "§ 573 BGB"}']
    answer = "Under § 573c Abs. 1 BGB [S1] and §§ 573, 573c [S1] the landlord ..."
    assert find_unverified_legal_refs(answer, cited) == []


def test_tripwire_flags_invented_paragraphs():
    cited = ["§ 573c BGB Kündigungsfristen", "§ 18g AufenthG"]
    answer = "See § 574 BGB [S1], § 18 AufenthG and Section 577a of the Civil Code."
    assert find_unverified_legal_refs(answer, cited) == ["§ 574", "§ 18", "Section 577a"]


def test_tripwire_ignores_answers_without_paragraphs():
    assert find_unverified_legal_refs("Register within the deadline [S1].", []) == []


# --- staleness + confidence ------------------------------------------------------------


def test_stale_sources():
    sources = [
        make_source("S1", last_verified="2026-11-10"),
        make_source("S2", last_verified="2026-01-01"),
        make_source("S3", last_verified="unknown"),
    ]
    assert stale_sources(sources, today=date(2026, 11, 17), staleness_days=90) == ["S2", "S3"]


def test_assess_confidence():
    ok = CitationCheck(answer="a [S1]", cited=["S1"], invalid=[])
    assert assess_confidence("a [S1]", has_evidence=True, citations=ok, unverified_refs=[]) == "grounded"
    assert assess_confidence("a [S1]", has_evidence=True, citations=ok, unverified_refs=["§ 1"]) == "partial"
    none = CitationCheck(answer="a", cited=[], invalid=[])
    assert assess_confidence("a", has_evidence=True, citations=none, unverified_refs=[]) == "partial"
    assert assess_confidence("a", has_evidence=False, citations=none, unverified_refs=[]) == "insufficient"
    fallback = "I couldn't find this in my official sources. Ask the KVR [S1]."
    assert assess_confidence(fallback, has_evidence=True, citations=ok, unverified_refs=[]) == "insufficient"


def test_stale_sources_flags_expired_validity() -> None:
    from datetime import date

    from fakes import make_source

    from expat.rag.generate import stale_sources

    fresh = make_source("S1", last_verified="2026-11-10", valid_until="2029-12-31")
    expired = make_source("S2", last_verified="2026-11-10", valid_until="2025-12-31")
    assert stale_sources([fresh, expired], today=date(2026, 11, 17), staleness_days=90) == ["S2"]
