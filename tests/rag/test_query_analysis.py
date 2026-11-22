"""Offline tests for query analysis: schema strictness, few-shot validity, to_plan(), fallback."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.utils.function_calling import convert_to_json_schema

from expat.rag.prompts import FEW_SHOT_EXAMPLES, QUERY_ANALYSIS_SYSTEM_PROMPT
from expat.rag.query_analysis import QueryAnalysis, analyze, format_history
from expat.schemas import RetrievalPlan, UserProfile


class FakeStructuredModel:
    """Minimal stand-in for a chat model's `with_structured_output(..., include_raw=True)`.

    `analyze()` only calls `with_structured_output(...).invoke(messages)`, so duck typing is
    enough; LangChain's fake chat models don't implement structured output.
    """

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []
        self.seen_messages: list[Any] = []

    def with_structured_output(self, schema: type, **kwargs: Any) -> RunnableLambda:
        self.calls.append({"schema": schema, **kwargs})

        def _invoke(messages: Any) -> dict[str, Any]:
            self.seen_messages = messages
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

        return RunnableLambda(_invoke)


def _example_analysis(index: int) -> QueryAnalysis:
    return QueryAnalysis.model_validate(FEW_SHOT_EXAMPLES[index].output)


def _walk_objects(schema: dict[str, Any]):
    if isinstance(schema, dict):
        if schema.get("type") == "object" or "properties" in schema:
            yield schema
        for value in schema.values():
            if isinstance(value, dict):
                yield from _walk_objects(value)
            elif isinstance(value, list):
                for item in value:
                    yield from _walk_objects(item)


def test_schema_is_strict_mode_compatible():
    schema = convert_to_json_schema(QueryAnalysis)
    objects = list(_walk_objects(schema))
    assert len(objects) >= 3  # QueryAnalysis, DomainScore, SubQuestion
    for obj in objects:
        assert obj.get("additionalProperties") is False
        assert set(obj["required"]) == set(obj["properties"])
        for prop in obj["properties"].values():
            assert "default" not in prop
    assert "_fallback_reason" not in str(schema)


@pytest.mark.parametrize("index", range(len(FEW_SHOT_EXAMPLES)))
def test_few_shot_examples_match_the_schema(index):
    analysis = _example_analysis(index)
    assert FEW_SHOT_EXAMPLES[index].question in QUERY_ANALYSIS_SYSTEM_PROMPT
    if analysis.intent in {"out_of_scope", "sensitive", "chitchat"}:
        assert analysis.sub_questions == []
    else:
        assert all(sub.queries_de for sub in analysis.sub_questions)


def test_few_shots_cover_the_required_cases():
    intents = {ex.output["intent"] for ex in FEW_SHOT_EXAMPLES}
    assert {"info", "checklist", "mixed", "sensitive", "out_of_scope"} <= intents
    assert any(ex.output["language"] == "de" for ex in FEW_SHOT_EXAMPLES)
    assert any(len(ex.output["sub_questions"]) >= 3 for ex in FEW_SHOT_EXAMPLES)
    assert any(sub["step_back"] for ex in FEW_SHOT_EXAMPLES for sub in ex.output["sub_questions"])


def test_to_plan_maps_sub_questions_and_domain_confidence():
    plan = _example_analysis(2).to_plan()  # multi-domain Blue Card family example
    assert len(plan.sub_queries) == 4
    first = plan.sub_queries[0]
    assert first.domain == "bureaucracy" and first.domain_confidence == pytest.approx(0.9)
    assert plan.sub_queries[2].domain == "family" and plan.sub_queries[2].domain_confidence == pytest.approx(0.85)
    assert first.queries_de == ["Wohnsitzanmeldung Familie München", "Anmeldung Familie Unterlagen"]


def test_to_plan_sanitises_llm_output():
    data = FEW_SHOT_EXAMPLES[1].output | {"domains": [{"domain": "tenancy", "confidence": 7.0}]}
    sub = data["sub_questions"][0] | {
        "queries_en": ["a", " a ", "", "b", "c", "d"],
        "queries_de": ["x", "y", "z"],
        "step_back": "   ",
        "section_kinds": ["deadlines", "deadlines"],
    }
    analysis = QueryAnalysis.model_validate(data | {"sub_questions": [sub] * 6})
    plan = analysis.to_plan()
    assert len(plan.sub_queries) == 4
    q = plan.sub_queries[0]
    assert q.queries_en == ["a", "b", "c"]
    assert q.queries_de == ["x", "y"]
    assert q.step_back is None
    assert q.section_kinds == ["deadlines"]
    assert q.domain_confidence == 1.0


def test_to_plan_without_sub_questions_uses_raw_plan():
    analysis = _example_analysis(6)  # out of scope
    assert analysis.to_plan() == RetrievalPlan.from_raw(analysis.standalone_question)


def test_analyze_returns_parsed_result_with_usage():
    parsed = _example_analysis(0)
    raw = AIMessage("{}", usage_metadata={"input_tokens": 120, "output_tokens": 40, "total_tokens": 160})
    llm = FakeStructuredModel({"raw": raw, "parsed": parsed, "parsing_error": None})
    history = [HumanMessage("I just signed a lease."), AIMessage("Great!")]

    result = analyze("How long do I have to register it?", history, UserProfile(city="munich"), llm)  # type: ignore[arg-type]

    assert result.intent == "info" and not result.is_fallback
    assert result.usage == (120, 40)
    assert llm.calls[0] == {"schema": QueryAnalysis, "method": "json_schema", "strict": True, "include_raw": True}
    user_prompt = llm.seen_messages[-1].content
    assert "user: I just signed a lease." in user_prompt and "Munich" in user_prompt


def test_analyze_falls_back_on_exception():
    llm = FakeStructuredModel(TimeoutError("provider timed out"))
    result = analyze("Wie melde ich mich an?", [], None, llm)  # type: ignore[arg-type]
    assert result.is_fallback and "TimeoutError" in (result.fallback_reason or "")
    assert result.to_plan() == RetrievalPlan.from_raw("Wie melde ich mich an?")


def test_analyze_falls_back_on_parsing_error():
    llm = FakeStructuredModel({"raw": AIMessage("not json"), "parsed": None, "parsing_error": ValueError("bad")})
    result = analyze("Kindergeld?", [], None, llm)  # type: ignore[arg-type]
    assert result.is_fallback and result.intent == "info"


def test_format_history_keeps_only_the_last_messages():
    history = [HumanMessage(f"q{i}") for i in range(10)]
    assert format_history(history, 2) == "user: q8\nuser: q9"
    assert format_history([], 6) == "(none)"
