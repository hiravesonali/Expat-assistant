"""`generate_document_checklist`: a personalised document checklist, grounded in retrieved sources.

Unlike the other tools this one IS an LLM call: a structured-output chain (`llm.with_structured_output`) over
the retrieved `ContextSource` blocks. Grounding is enforced in code, not trusted to the prompt: every item
must reference a provided `source_id`, and a Pydantic validator drops items that don't. That prevents
hallucinated documents ("bring your birth certificate") from reaching the user.
"""

import logging
from collections.abc import Callable
from typing import Literal, Self

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, ValidationInfo, model_validator

from expat.places import city_label
from expat.schemas.profile import UserProfile
from expat.schemas.retrieval import ContextSource
from expat.tools._common import ToolOutput, make_tool

logger = logging.getLogger(__name__)

ChecklistProcedure = Literal[
    "anmeldung",
    "blue_card_first_permit",
    "blue_card_extension",
    "settlement_permit_blue_card",
    "kindergeld_application",
    "elterngeld_application",
    "kita_registration",
]

# How the pipeline supplies context: given the procedure and the profile, return retrieved source blocks
# (typically checklist/document sections). Kept as a plain callable so this module doesn't depend on rag/.
SourceFetcher = Callable[[ChecklistProcedure, UserProfile], list[ContextSource]]

NOT_GROUNDED_RULES_VERSION = "n/a (grounded in retrieved sources)"


# --- LLM-facing schema (what the model fills in) ---------------------------------------------------


class ChecklistItem(BaseModel):
    name_en: str = Field(description="Document name in English.")
    name_de: str | None = Field(default=None, description="Official German name, as written in the source.")
    required: bool = Field(description="True if the source says it is mandatory for this person.")
    applies_because: str | None = Field(
        default=None, description="Why it applies to this user's profile, e.g. 'you have children'."
    )
    notes: str | None = Field(default=None, description="Short practical note from the source (original, copies).")
    source_id: str = Field(description="Id of the source block this item comes from, e.g. 'S2'. Mandatory.")


class FeeItem(BaseModel):
    label: str
    amount_eur: float | None = Field(default=None, description="Amount exactly as stated in the source.")
    source_id: str = Field(description="Id of the source block stating this fee. Mandatory.")


class StepItem(BaseModel):
    order: int = Field(ge=1)
    description: str
    source_id: str = Field(description="Id of the source block describing this step. Mandatory.")


class ChecklistDraft(BaseModel):
    """Structured output requested from the model. It never sets provenance fields itself."""

    items: list[ChecklistItem] = Field(default_factory=list)
    fees: list[FeeItem] = Field(default_factory=list)
    steps: list[StepItem] = Field(default_factory=list)
    missing_info: list[str] = Field(
        default_factory=list, description="Facts about the user you would need to finalise the list."
    )


# --- Tool output (grounded) ------------------------------------------------------------------------


class CitedSource(BaseModel):
    source_id: str
    doc_key: str
    title: str
    source_url: str


class Checklist(ToolOutput):
    """The grounded checklist.

    Validate with `Checklist.model_validate(data, context={"allowed_source_ids": {...}})`: the after-validator
    then drops every item, fee and step whose `source_id` isn't in that set and records what it dropped.
    Pydantic's validation *context* is the idiomatic way to give a validator run-time data (the ids of this
    request's sources) without putting that data into the model itself. Without a context nothing is dropped
    (e.g. when re-loading an already grounded checklist).
    """

    procedure: ChecklistProcedure
    city: str | None = None  # None when the user has not said where they live
    items: list[ChecklistItem] = Field(default_factory=list)
    fees: list[FeeItem] = Field(default_factory=list)
    steps: list[StepItem] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    cited_sources: list[CitedSource] = Field(default_factory=list)
    dropped_ungrounded: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _drop_ungrounded(self, info: ValidationInfo) -> Self:
        allowed: set[str] | None = (info.context or {}).get("allowed_source_ids")
        if allowed is None:
            return self
        dropped = [
            f"item: {i.name_en} ({i.source_id or 'no source'})" for i in self.items if i.source_id not in allowed
        ]
        dropped += [f"fee: {f.label} ({f.source_id or 'no source'})" for f in self.fees if f.source_id not in allowed]
        dropped += [
            f"step: {s.description} ({s.source_id or 'no source'})" for s in self.steps if s.source_id not in allowed
        ]
        self.items = [i for i in self.items if i.source_id in allowed]
        self.fees = [f for f in self.fees if f.source_id in allowed]
        self.steps = [s for s in self.steps if s.source_id in allowed]
        self.dropped_ungrounded = [*self.dropped_ungrounded, *dropped]
        return self


SYSTEM_PROMPT = """You build a document checklist for a German administrative procedure.
Rules:
- Use ONLY the numbered source blocks below. Every item, fee and step MUST carry the source_id of the block that
  states it (e.g. "S2"). Never add documents, fees or steps that are not in the sources.
- Personalise with the user profile: mark items that apply because of the profile (e.g. children, marital status)
  in applies_because. Skip items that clearly don't apply.
- Copy fee amounts exactly as written; leave amount_eur empty if no amount is stated.
- Put facts you would need from the user (e.g. "Are you married?") into missing_info.
- name_de must be the German term used in the source, if any."""


def _format_sources(sources: list[ContextSource]) -> str:
    return "\n\n".join(f"[{s.source_id}] {s.title} - {s.heading_path} ({s.source_url})\n{s.text}" for s in sources)


def _empty_checklist(procedure: ChecklistProcedure, profile: UserProfile, reason: str) -> Checklist:
    return Checklist(
        procedure=procedure,
        city=profile.city,
        missing_info=[reason],
        legal_basis=[],
        source_urls=[],
        rules_version=NOT_GROUNDED_RULES_VERSION,
        caveats=["No grounded checklist available; refer the user to the official procedure page of the office."],
    )


def build_checklist(
    procedure: ChecklistProcedure,
    profile: UserProfile,
    sources: list[ContextSource],
    llm: BaseChatModel,
) -> Checklist:
    """Run the structured-output chain and ground the result in `sources`.

    Never raises for model problems: an empty retrieval or an unparsable answer becomes a Checklist with
    `missing_info`, so the answer agent can still respond (error-as-data, docs/tools.md principle 5).
    """
    if not sources:
        return _empty_checklist(procedure, profile, f"No official checklist was retrieved for '{procedure}'.")

    chain = llm.with_structured_output(ChecklistDraft)
    messages = [
        SystemMessage(SYSTEM_PROMPT),
        HumanMessage(
            f"Procedure: {procedure} in {city_label(profile.city) or 'Germany'}\n{profile.summary()}\n\nSources:\n"
            f"{_format_sources(sources)}"
        ),
    ]
    try:
        draft = chain.invoke(messages)
    except Exception:  # provider/parse errors must not crash the answer turn
        logger.exception("checklist structured output failed for %s", procedure)
        draft = None
    if not isinstance(draft, ChecklistDraft):
        return _empty_checklist(procedure, profile, "The checklist could not be generated from the sources.")

    by_id = {s.source_id: s for s in sources}
    checklist = Checklist.model_validate(
        {
            **draft.model_dump(),
            "procedure": procedure,
            "city": profile.city,
            "legal_basis": [],
            "source_urls": [],
            "rules_version": NOT_GROUNDED_RULES_VERSION,
        },
        context={"allowed_source_ids": set(by_id)},
    )

    entries: list[ChecklistItem | FeeItem | StepItem] = [*checklist.items, *checklist.fees, *checklist.steps]
    cited_ids = sorted({entry.source_id for entry in entries})
    cited = [by_id[i] for i in cited_ids]
    checklist.cited_sources = [
        CitedSource(source_id=s.source_id, doc_key=s.doc_key, title=s.title, source_url=s.source_url) for s in cited
    ]
    checklist.source_urls = list(dict.fromkeys(s.source_url for s in cited))  # dedupe, keep order
    checklist.legal_basis = list(dict.fromkeys(s.legal_reference for s in cited if s.legal_reference))
    checklist.caveats = [
        "Generated from the official pages listed; offices can ask for extra documents in individual cases.",
        "Bring originals plus copies unless the source says otherwise.",
    ]
    if checklist.dropped_ungrounded:
        checklist.caveats.append(
            f"{len(checklist.dropped_ungrounded)} suggestion(s) were removed because no source supported them."
        )
    if not checklist.items:
        checklist.missing_info.append("The retrieved sources did not contain a usable document list.")
    return checklist


class ChecklistInput(BaseModel):
    """Only the procedure is chosen by the model; the profile is injected server-side (never by the LLM)."""

    procedure: ChecklistProcedure = Field(description="The procedure to build a document checklist for.")


def make_checklist_tool(fetch_sources: SourceFetcher, llm: BaseChatModel, profile: UserProfile) -> BaseTool:
    """Build the `generate_document_checklist` tool for one request.

    Why a factory: the tool needs per-request dependencies (the user's profile, a retrieval function and a
    chat model) that the LLM must not choose. The pipeline creates it per turn, e.g.

        tool = make_checklist_tool(lambda proc, prof: retriever.retrieve(plan_for(proc), prof).parents, llm, profile)
        tools = get_tools(checklist_tool=tool)
    """

    def _generate(inp: ChecklistInput) -> Checklist:
        return build_checklist(inp.procedure, profile, fetch_sources(inp.procedure, profile), llm)

    return make_tool(
        name="generate_document_checklist",
        description=(
            "Build a personalised list of documents, fees and steps for a Munich procedure (Anmeldung, Blue Card "
            "first permit/extension, settlement permit, Kindergeld, Elterngeld, Kita registration), grounded in "
            "official sources. Use whenever the user asks what documents to bring or prepare."
        ),
        args_schema=ChecklistInput,
        fn=_generate,
    )
