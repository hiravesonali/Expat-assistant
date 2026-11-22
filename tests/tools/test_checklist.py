"""Structured-output checklist, tested offline with a fake chat model (no network, no API key)."""

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from expat.schemas.profile import FamilyStatus, UserProfile
from expat.schemas.retrieval import ContextSource
from expat.tools.checklist import (
    Checklist,
    ChecklistItem,
    build_checklist,
    make_checklist_tool,
)


class FakeToolCallingModel(GenericFakeChatModel):
    """GenericFakeChatModel replays canned AIMessages; we only add `bind_tools`, which `with_structured_output`
    needs. The real LangChain parsing path (tool call -> PydanticToolsParser -> ChecklistDraft) still runs."""

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable:
        return self


def _fake_llm(draft_args: dict[str, Any] | None) -> BaseChatModel:
    if draft_args is None:
        return FakeToolCallingModel(messages=iter([AIMessage(content="Sorry, I can't.")]))
    call = {"name": "ChecklistDraft", "args": draft_args, "id": "call_1", "type": "tool_call"}
    return FakeToolCallingModel(messages=iter([AIMessage(content="", tool_calls=[call])]))


def _source(source_id: str, text: str) -> ContextSource:
    return ContextSource(
        source_id=source_id,
        parent_id=f"muc-anmeldung-familie#{source_id}",
        chunk_ids=[f"c-{source_id}"],
        doc_key="muc-anmeldung-familie#documents",
        title="Wohnsitzanmeldung Familie",
        heading_path="Documents",
        source_name="Stadt München",
        source_url="https://stadt.muenchen.de/service/info/wohnsitzanmeldung/1063475/n0/",
        legal_reference="§ 17 BMG" if source_id == "S1" else "",
        language="de",
        last_verified="2026-11-17",
        text=text,
    )


SOURCES = [
    _source("S1", "Mitzubringen: Personalausweis oder Reisepass, Wohnungsgeberbestätigung."),
    _source("S2", "Für Kinder: Geburtsurkunde. Die Anmeldung ist gebührenfrei."),
]
PROFILE = UserProfile(city="munich", family_status=FamilyStatus.MARRIED, children_count=2)


DRAFT = {
    "items": [
        {"name_en": "Passport", "name_de": "Reisepass", "required": True, "source_id": "S1"},
        {
            "name_en": "Landlord confirmation",
            "name_de": "Wohnungsgeberbestätigung",
            "required": True,
            "source_id": "S1",
        },
        {
            "name_en": "Birth certificates",
            "name_de": "Geburtsurkunde",
            "required": True,
            "applies_because": "you have children",
            "source_id": "S2",
        },
        {"name_en": "Marriage certificate", "required": True, "source_id": "S9"},  # hallucinated source
        {"name_en": "Rental contract", "required": False, "source_id": ""},  # no source at all
    ],
    "fees": [{"label": "Registration", "amount_eur": 0, "source_id": "S2"}, {"label": "Express", "source_id": "S7"}],
    "steps": [{"order": 1, "description": "Book an appointment", "source_id": "S3"}],
    "missing_info": [],
}


def test_validator_drops_items_with_unknown_or_missing_source_id() -> None:
    result = build_checklist("anmeldung", PROFILE, SOURCES, _fake_llm(DRAFT))
    assert [i.name_en for i in result.items] == ["Passport", "Landlord confirmation", "Birth certificates"]
    assert [f.label for f in result.fees] == ["Registration"]
    assert result.steps == []
    assert len(result.dropped_ungrounded) == 4
    assert any("Marriage certificate" in d for d in result.dropped_ungrounded)
    assert any("removed because no source" in c for c in result.caveats)


def test_grounded_checklist_is_citable() -> None:
    result = build_checklist("anmeldung", PROFILE, SOURCES, _fake_llm(DRAFT))
    assert result.procedure == "anmeldung"
    assert result.city == "munich"
    assert [s.source_id for s in result.cited_sources] == ["S1", "S2"]
    assert result.source_urls == [SOURCES[0].source_url]  # deduplicated
    assert result.legal_basis == ["§ 17 BMG"]
    assert result.rules_version


def test_validator_is_a_no_op_without_context() -> None:
    """Re-validating an already grounded checklist (e.g. from JSON) must not drop anything."""
    data = {
        "procedure": "anmeldung",
        "city": "munich",
        "items": [ChecklistItem(name_en="X", required=True, source_id="S42").model_dump()],
        "legal_basis": [],
        "source_urls": [],
        "rules_version": "v",
    }
    assert len(Checklist.model_validate(data).items) == 1
    assert Checklist.model_validate(data, context={"allowed_source_ids": {"S1"}}).items == []


def test_no_sources_returns_missing_info_without_calling_the_model() -> None:
    llm = _fake_llm(None)
    result = build_checklist("kita_registration", PROFILE, [], llm)
    assert result.items == []
    assert "kita_registration" in result.missing_info[0]


def test_model_without_structured_answer_degrades_gracefully() -> None:
    result = build_checklist("anmeldung", PROFILE, SOURCES, _fake_llm(None))
    assert result.items == []
    assert result.missing_info


def test_all_items_ungrounded_reports_missing_info() -> None:
    draft = {"items": [{"name_en": "Ghost document", "required": True, "source_id": "S99"}]}
    result = build_checklist("anmeldung", PROFILE, SOURCES, _fake_llm(draft))
    assert result.items == []
    assert any("usable document list" in m for m in result.missing_info)


def test_tool_factory_injects_profile_and_sources() -> None:
    seen: dict[str, Any] = {}

    def fetch(procedure: str, profile: UserProfile) -> list[ContextSource]:
        seen["procedure"], seen["profile"] = procedure, profile
        return SOURCES

    tool = make_checklist_tool(fetch, _fake_llm(DRAFT), PROFILE)
    assert tool.name == "generate_document_checklist"
    assert set(tool.args) == {"procedure"}  # the model can't choose the profile
    payload = json.loads(tool.invoke({"procedure": "anmeldung"}))
    assert seen == {"procedure": "anmeldung", "profile": PROFILE}
    assert len(payload["items"]) == 3


def test_tool_rejects_unknown_procedure_as_data() -> None:
    tool = make_checklist_tool(lambda proc, prof: SOURCES, _fake_llm(DRAFT), PROFILE)
    payload = json.loads(tool.invoke({"procedure": "buy_a_car"}))
    assert payload["needs"] == ["procedure"]
