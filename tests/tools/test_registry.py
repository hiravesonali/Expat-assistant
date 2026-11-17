"""The tool registry the answer agent binds, and the cross-tool contract (citable output, errors as data)."""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.utils.function_calling import convert_to_openai_tool

from expat.schemas.profile import UserProfile
from expat.tools import get_tools, make_checklist_tool

EXPECTED = ["calculate_tenancy_notice", "calculate_deadline", "estimate_family_benefits", "schengen_days_calculator"]


def test_get_tools_returns_deterministic_tools() -> None:
    assert [t.name for t in get_tools()] == EXPECTED


def test_get_tools_includes_injected_checklist_tool() -> None:
    checklist = make_checklist_tool(lambda proc, prof: [], GenericFakeChatModel(messages=iter([])), UserProfile())
    names = [t.name for t in get_tools(checklist_tool=checklist)]
    assert "generate_document_checklist" in names
    assert len(names) == 5


def test_get_tools_returns_a_fresh_list() -> None:
    get_tools().clear()
    assert len(get_tools()) == 4


def test_every_tool_has_a_when_to_use_description_and_json_schema() -> None:
    """What the model actually sees when tools are bound (OpenAI-style function schema)."""
    for tool in get_tools():
        schema = convert_to_openai_tool(tool)
        assert schema["function"]["name"] == tool.name
        assert "Use " in tool.description
        assert schema["function"]["parameters"]["properties"]
