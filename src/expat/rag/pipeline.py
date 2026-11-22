"""The RAG pipeline as a generator of typed events (ADR-0009).

    safety pre-check -> query analysis -> [short-circuit] -> retrieval -> answer agent -> post-checks

`run()` yields `expat.schemas.events` objects as each stage completes; the Streamlit UI renders
them (timeline, streamed tokens, tool chips, citations). A future FastAPI layer would serialise
the SAME events as SSE.

Everything external is injected (retriever, models, tools), so the whole pipeline runs offline
in tests with fakes. `build_default_pipeline()` wires the real implementations, importing them
lazily so this module imports fine even before those modules exist.

Tracing: `run` is a LangSmith `@traceable` root run ("expat_pipeline") with the profile enums
as metadata; analysis, retrieval and the agent appear as named child runs.
"""

import logging
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, convert_to_messages
from langchain_core.messages.utils import MessageLikeRepresentation
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from expat.config import REPO_ROOT, get_settings
from expat.places import SUPPORTED_CITIES, city_label, find_cities
from expat.rag.context import build_context_pack, source_header
from expat.rag.filters import location_from_profile
from expat.rag.generate import (
    AnswerAgent,
    AnswerContext,
    ToolResultRecord,
    assess_confidence,
    build_answer_agent,
    find_unverified_legal_refs,
    is_transient_error,
    parse_tool_message,
    stale_sources,
    validate_citations,
)
from expat.rag.prompts import ANSWER_PROMPT_VERSION, QUERY_ANALYSIS_PROMPT_VERSION
from expat.rag.query_analysis import QueryAnalysis, analyze
from expat.safety import SafetyCategory, category_for_intent, precheck, safety_response
from expat.schemas.chunks import SectionKind
from expat.schemas.events import (
    AnswerMetaEvent,
    Citation,
    CitationsEvent,
    ClarificationEvent,
    DoneEvent,
    ErrorEvent,
    PipelineEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from expat.schemas.profile import UserProfile
from expat.schemas.retrieval import (
    ContextSource,
    Location,
    RetrievalConfig,
    RetrievalPlan,
    RetrievalResult,
    Retriever,
    SubQuery,
)

logger = logging.getLogger(__name__)

History = Sequence[MessageLikeRepresentation]
"""Anything LangChain can turn into messages: BaseMessage, ("user", "hi"), {"role": ..., "content": ...}."""

TOP_HITS_PER_SUB_QUESTION = 3
QUOTE_CHARS = 300


def profile_metadata(profile: UserProfile | None) -> dict[str, Any]:
    """Profile enums as LangSmith run metadata (coarse, non-identifying; see ADR-0007)."""
    if profile is None:
        return {"profile": "none"}
    return {f"profile_{key}": value for key, value in profile.model_dump(mode="json").items()}


def run(
    question: str,
    history: History,
    profile: UserProfile | None,
    *,
    retriever: Retriever,
    analysis_llm: BaseChatModel,
    answer_llm: BaseChatModel | None,
    tools: Sequence[BaseTool],
    config: RetrievalConfig | None = None,
    answer_agent: AnswerAgent | None = None,
    pending_changes: Sequence[str] = (),
    today: date | None = None,
) -> Iterator[PipelineEvent]:
    """Answer one chat turn, yielding events. Never raises: failures become an `ErrorEvent`.

    Pass a prebuilt `answer_agent` (from `build_answer_agent`) to avoid recompiling the agent
    graph per turn; otherwise one is built from `answer_llm` + `tools`.
    """
    yield from _run_traced(
        question,
        history,
        profile,
        retriever=retriever,
        analysis_llm=analysis_llm,
        answer_llm=answer_llm,
        tools=tools,
        retrieval_config=config,  # NOT `config`: @traceable reads that name as a RunnableConfig
        answer_agent=answer_agent,
        pending_changes=tuple(pending_changes),
        today=today or date.today(),
        langsmith_extra={
            "metadata": {
                **profile_metadata(profile),
                "query_analysis_prompt": QUERY_ANALYSIS_PROMPT_VERSION,
                "answer_prompt": ANSWER_PROMPT_VERSION,
            },
            "tags": ["expat", "pipeline"],
        },
    )


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, message: AIMessage) -> None:
        if message.usage_metadata:
            self.input_tokens += message.usage_metadata["input_tokens"]
            self.output_tokens += message.usage_metadata["output_tokens"]


@dataclass
class _AnswerState:
    """What the agent stream leaves behind for the post-checks."""

    final_text: str = ""
    final_streamed: bool = False
    tool_results: list[ToolResultRecord] = field(default_factory=list)


@traceable(name="expat_pipeline", run_type="chain")
def _run_traced(
    question: str,
    history: History,
    profile: UserProfile | None,
    *,
    retriever: Retriever,
    analysis_llm: BaseChatModel,
    answer_llm: BaseChatModel | None,
    tools: Sequence[BaseTool],
    retrieval_config: RetrievalConfig | None,
    answer_agent: AnswerAgent | None,
    pending_changes: tuple[str, ...],
    today: date,
) -> Iterator[PipelineEvent]:
    started = time.perf_counter()
    settings = get_settings()
    usage = _Usage()
    chosen_language = profile.answer_language if profile else None  # the app's language switch, if set
    language = chosen_language or "en"
    stage = "safety"

    def done() -> DoneEvent:
        run_tree = get_current_run_tree()
        return DoneEvent(
            run_id=str(run_tree.id) if run_tree else None,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

    try:
        messages: list[BaseMessage] = convert_to_messages(history)[-2 * settings.history_turns :]

        # 0. Deterministic safety pre-check: no LLM call at all for the clearest cases.
        category = precheck(question)
        if category is not None:
            yield from _short_circuit(category, language, trigger="keyword")
            yield done()
            return

        # 1. Query translation (one structured-output call; never raises, falls back instead).
        stage = "query_analysis"
        yield StepEvent(name="query_analysis", status="started")
        analysis = analyze(question, messages, profile, analysis_llm, max_history_messages=2 * settings.history_turns)
        usage.input_tokens += analysis.usage[0]
        usage.output_tokens += analysis.usage[1]
        plan = analysis.to_plan()
        yield StepEvent(name="query_analysis", status="completed", detail=_analysis_detail(analysis, plan))
        if chosen_language is None and analysis.language in ("en", "de"):
            language = analysis.language  # no explicit choice: answer in the language the user wrote in

        category = category_for_intent(analysis.intent)
        if category is not None:
            yield from _short_circuit(category, language, trigger="analysis")
            yield done()
            return

        # Where is the question about? Places named in the question (or kept from the history by the
        # standalone rewrite) win over the profile; unknown -> nationwide sources only.
        location = resolve_location(question, analysis.standalone_question, profile, analysis.mentioned_city)
        plan = plan.model_copy(update={"location": location})
        if analysis.location_dependent and not location.known:
            yield from _ask_for_location(question, language)
            yield done()
            return

        # 2. Structured hybrid retrieval (deterministic, always runs for in-scope questions).
        stage = "retrieval"
        yield StepEvent(name="retrieval", status="started")
        result = _retrieve(retriever, plan, profile, retrieval_config)
        sources = result.parents
        yield StepEvent(name="retrieval", status="completed", detail=_retrieval_detail(result))

        # 3. Answer agent, streamed.
        stage = "generation"
        yield StepEvent(name="generation", status="started")
        if answer_agent is None:
            if answer_llm is None:
                raise ValueError("run() needs either `answer_agent` or `answer_llm`.")
            answer_agent = build_answer_agent(answer_llm, tools)
        context = AnswerContext(
            profile_summary=profile.summary() if profile else "User: profile unknown (ask if it matters).",
            context_pack=build_context_pack(sources),
            language=language,
            pending_changes=pending_changes,
            clarification=analysis.needs_clarification,
            today=today,
        )
        state = _AnswerState()
        yield from _stream_answer(
            answer_agent, [*messages, HumanMessage(question)], context, state, usage, profile=profile
        )
        if state.final_text and not state.final_streamed:
            yield TokenEvent(text=state.final_text)  # e.g. a message written by a limit middleware

        # 4. Deterministic post-checks.
        check = validate_citations(state.final_text, sources, state.tool_results)
        cited_sources = [s for s in sources if s.source_id in check.cited]
        cited_tools = [t for t in state.tool_results if t.citation_id in check.cited]
        cited_texts = [f"{source_header(s)}\n{s.text}" for s in cited_sources] + [t.text for t in cited_tools]
        unverified = find_unverified_legal_refs(check.answer, cited_texts)
        stale = stale_sources(cited_sources, today=today, staleness_days=settings.staleness_days)
        has_evidence = bool(sources) or any(t.citable for t in state.tool_results)
        confidence = assess_confidence(
            state.final_text, has_evidence=has_evidence, citations=check, unverified_refs=unverified
        )
        if check.invalid or unverified:
            logger.warning("Post-check flags: invalid citations=%s, unverified refs=%s", check.invalid, unverified)
            _annotate_run({"invalid_citations": check.invalid, "unverified_refs": unverified})

        yield StepEvent(
            name="generation",
            status="completed",
            detail={
                # The UI already streamed the raw tokens; `answer` is the cleaned final text it may re-render.
                "answer": check.answer,
                "stripped_citations": check.invalid,
                "tool_calls": len(state.tool_results),
            },
        )
        yield CitationsEvent(citations=_citations(check.cited, cited_sources, cited_tools))
        yield AnswerMetaEvent(
            confidence=confidence, stale_sources=stale, unverified_refs=unverified, final_answer=check.answer
        )
        yield done()
    except Exception as exc:  # the generator must end with a typed event, never a traceback in the UI
        logger.exception("Pipeline failed during %s", stage)
        yield StepEvent(name=stage, status="failed", detail={"error": type(exc).__name__})
        yield ErrorEvent(code=f"{stage}_failed", message=str(exc)[:500], retryable=is_transient_error(exc))


def resolve_location(
    question: str, standalone_question: str, profile: UserProfile | None, mentioned_city: str | None = None
) -> Location:
    """Location for this turn: supported cities named in the question > another city the analysis heard
    ("I live in Leipzig": known, but no local sources -> nationwide only) > the profile > unknown."""
    cities = find_cities(" \n".join((question, standalone_question, mentioned_city or "")))
    if cities:
        return Location(
            cities=[c.slug for c in cities], states=list(dict.fromkeys(c.state for c in cities)), source="question"
        )
    if mentioned_city and mentioned_city.strip():
        return Location(cities=[mentioned_city.strip().lower()], source="question")
    return location_from_profile(profile)


def with_question_city(profile: UserProfile | None, question: str) -> UserProfile | None:
    """The profile, moved to the city the question names (exactly one), for the profile-bound tools."""
    cities = find_cities(question)
    if profile is None or len(cities) != 1:
        return profile
    return profile.model_copy(update={"city": cities[0].slug, "state": cities[0].state})


_ASK_LOCATION = {
    "en": "Which city do you live in? Offices, appointments and local rules differ from city to city, so I want "
    "to give you the right ones. Pick your city below, or just type it.",
    "de": "In welcher Stadt wohnen Sie? Ämter, Termine und lokale Regeln sind von Stadt zu Stadt verschieden. "
    "Wählen Sie unten Ihre Stadt oder schreiben Sie sie einfach.",
}


def _ask_for_location(question: str, language: str) -> Iterator[PipelineEvent]:
    """One follow-up question instead of a possibly wrong-city answer (docs/plan-germany-wide.md)."""
    yield StepEvent(name="clarification", status="completed", detail={"kind": "location"})
    yield TokenEvent(text=_ASK_LOCATION["de" if language == "de" else "en"])
    yield ClarificationEvent(
        original_question=question,
        options=[(c.slug, c.name) for c in SUPPORTED_CITIES.values()] + [("other", "Other city")],
    )
    yield CitationsEvent(citations=[])
    yield AnswerMetaEvent(confidence="insufficient")


def _short_circuit(category: SafetyCategory, language: str, *, trigger: str) -> Iterator[PipelineEvent]:
    """A fixed policy answer instead of RAG (sensitive, out of scope, chitchat)."""
    yield StepEvent(name="safety", status="completed", detail={"category": category.value, "trigger": trigger})
    yield TokenEvent(text=safety_response(category, language))
    yield CitationsEvent(citations=[])
    # Not grounded in sources by design; the UI can tell it apart via the "safety" step above.
    yield AnswerMetaEvent(confidence="insufficient")


@traceable(name="retrieval", run_type="chain")
def _retrieve(
    retriever: Retriever, plan: RetrievalPlan, profile: UserProfile | None, retrieval_config: RetrievalConfig | None
) -> RetrievalResult:
    return retriever.retrieve(plan, profile, retrieval_config)


def _stream_answer(
    agent: AnswerAgent,
    messages: list[BaseMessage],
    context: AnswerContext,
    state: _AnswerState,
    usage: _Usage,
    *,
    profile: UserProfile | None,
) -> Iterator[PipelineEvent]:
    """Map the agent's dual-mode stream to our events.

    - "messages" mode yields token chunks as the model writes them -> TokenEvent.
    - "updates" mode yields each node's completed state update: AI messages with tool calls
      -> ToolCallEvent, ToolMessages -> ToolResultEvent, the last AI message -> final answer.
    """
    run_config: RunnableConfig = {
        "run_name": "answer_agent",
        "tags": ["expat", "answer"],
        "metadata": {**profile_metadata(profile), "answer_prompt": ANSWER_PROMPT_VERSION},
    }
    stream = agent.stream(
        {"messages": messages},
        config=run_config,
        context=context,
        stream_mode=["messages", "updates"],
    )
    # With a list of stream modes, every item is a (mode, payload) tuple.
    data: Any
    for mode, data in stream:
        if mode == "messages":
            chunk, meta = data
            if isinstance(chunk, AIMessage) and meta.get("langgraph_node") == "model" and chunk.text:
                yield TokenEvent(text=chunk.text)
            continue
        for node, update in data.items():
            node_messages = update.get("messages") if isinstance(update, dict) else None
            if not isinstance(node_messages, list):
                continue
            for message in node_messages:
                if isinstance(message, AIMessage):
                    usage.add(message)
                    for call in message.tool_calls:
                        yield ToolCallEvent(call_id=call["id"] or "", name=call["name"], args=call["args"])
                    if not message.tool_calls and message.text:
                        state.final_text = message.text
                        # Text from the model node was already streamed token by token; text written
                        # by another node (e.g. a call-limit middleware) was not.
                        state.final_streamed = node == "model"
                elif isinstance(message, ToolMessage):
                    record = parse_tool_message(message)
                    state.tool_results.append(record)
                    yield ToolResultEvent(
                        call_id=record.call_id, name=record.name, result=record.result, error=record.error
                    )


def _analysis_detail(analysis: QueryAnalysis, plan: RetrievalPlan) -> dict[str, Any]:
    return {
        "standalone_question": analysis.standalone_question,
        "intent": analysis.intent,
        "language": analysis.language,
        "domains": [d.model_dump(mode="json") for d in analysis.domains],
        # Same shape as RetrievalPlan.model_dump() (the UI contract, see app/demo_pipeline.py).
        "sub_queries": [q.model_dump(mode="json") for q in plan.sub_queries],
        "needs_clarification": analysis.needs_clarification,
        "fallback": analysis.is_fallback,
        "fallback_reason": analysis.fallback_reason,
    }


def _retrieval_detail(result: RetrievalResult) -> dict[str, Any]:
    """UI + eval contract: `sub_results` = SubQuestionResult dumps (top hits only, to keep events small);
    `sources` = full ContextSource dumps (the faithfulness judge needs the text)."""
    return {
        "sub_results": [
            sub.model_copy(update={"hits": sub.hits[:TOP_HITS_PER_SUB_QUESTION]}).model_dump(mode="json")
            for sub in result.sub_results
        ],
        "sources": [s.model_dump(mode="json") for s in result.parents],
    }


def _citations(
    cited_ids: Sequence[str], sources: Sequence[ContextSource], tools: Sequence[ToolResultRecord]
) -> list[Citation]:
    by_id: dict[str, Citation] = {}
    for s in sources:
        by_id[s.source_id] = Citation(
            id=s.source_id,
            kind="source",
            title=s.title,
            source_name=s.source_name,
            source_url=s.source_url,
            heading_path=s.heading_path,
            legal_reference=s.legal_reference,
            doc_key=s.doc_key,
            last_verified=s.last_verified,
            quote=s.text[:QUOTE_CHARS],
        )
    for t in tools:
        if t.citation_id:
            by_id[t.citation_id] = Citation(
                id=t.citation_id, kind="tool", title=t.name, source_name="calculation tool", quote=t.text[:QUOTE_CHARS]
            )
    return [by_id[i] for i in cited_ids if i in by_id]


def _annotate_run(metadata: dict[str, Any]) -> None:
    """Attach post-check results to the current LangSmith run (no-op when tracing is off)."""
    run_tree = get_current_run_tree()
    if run_tree is not None:
        run_tree.add_metadata(metadata)


# --------------------------------------------------------------------------------------
# Default wiring
# --------------------------------------------------------------------------------------

PipelineFn = Callable[[str, History, UserProfile | None], Iterator[PipelineEvent]]

PENDING_CHANGES_PATH = REPO_ROOT / "rules" / "2026.yaml"


def load_pending_changes(path: Path = PENDING_CHANGES_PATH) -> tuple[str, ...]:
    """Read `pending_changes` from the rules file as one-line notes; empty if absent or malformed.

    Entries may be plain strings or dicts; for dicts we join the human-readable fields.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ()
    entries = data.get("pending_changes", []) if isinstance(data, dict) else []
    notes: list[str] = []
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, str):
            notes.append(entry)
        elif isinstance(entry, dict):
            parts = [str(entry[k]) for k in ("title", "topic", "summary", "note", "status") if entry.get(k)]
            if parts:
                notes.append(" – ".join(parts))
    return tuple(notes)


CHECKLIST_QUERY_DE = "Erforderliche Unterlagen für {procedure} in München"


@dataclass
class Pipeline:
    """The wired pipeline: what the Streamlit chat, the debugger page and the evals all use.

    Why an object instead of a bare function: the Retrieval Debugger needs the *same* `retriever`
    and `analyze` step the chat uses ("one retrieval code path", docs/PLAN.md), and the
    checklist tool needs per-request inputs (the user's profile), so tools are assembled per turn.
    """

    retriever: Retriever
    analysis_llm: BaseChatModel
    answer_llm: BaseChatModel
    pending_changes: tuple[str, ...] = ()
    _static_tools: list[BaseTool] = field(default_factory=list)
    _static_agent: AnswerAgent | None = None

    def analyze(self, question: str, history: History = (), profile: UserProfile | None = None) -> RetrievalPlan:
        """Query analysis only (debugger / retrieval evals). Never raises; falls back to the raw question.

        Resolves the location exactly like `run()` does, so evals and the debugger filter like the chat.
        """
        analysis = analyze(question, convert_to_messages(list(history)), profile, self.analysis_llm)
        location = resolve_location(question, analysis.standalone_question, profile, analysis.mentioned_city)
        return analysis.to_plan().model_copy(update={"location": location})

    def tools_for(self, profile: UserProfile | None) -> list[BaseTool]:
        """Static calculators + the profile-bound checklist tool (when we know who is asking)."""
        if profile is None:
            return self._static_tools
        from expat.tools import get_tools
        from expat.tools.checklist import make_checklist_tool

        def fetch_sources(procedure: str, prof: UserProfile) -> list[ContextSource]:
            readable = procedure.replace("_", " ")
            where = f" in {city_label(prof.city)}" if prof.city else ""
            sub = SubQuery(
                text=f"Which documents do I need for {readable}{where}?",
                queries_de=[CHECKLIST_QUERY_DE.format(procedure=readable)],
                section_kinds=[SectionKind.DOCUMENTS],
            )
            plan = RetrievalPlan(standalone_question=sub.text, sub_queries=[sub])
            return self.retriever.retrieve(plan, prof).parents

        return get_tools(checklist_tool=make_checklist_tool(fetch_sources, self.analysis_llm, profile))

    def run(
        self,
        question: str,
        history: History = (),
        profile: UserProfile | None = None,
        config: RetrievalConfig | None = None,
    ) -> Iterator[PipelineEvent]:
        tools = self.tools_for(with_question_city(profile, question))
        # Reuse the compiled agent when the tool set is the static one; otherwise build per turn (cheap).
        agent = self._static_agent if tools is self._static_tools else None
        return run(
            question,
            history,
            profile,
            retriever=self.retriever,
            analysis_llm=self.analysis_llm,
            answer_llm=self.answer_llm,
            tools=tools,
            config=config,
            answer_agent=agent,
            pending_changes=self.pending_changes,
        )

    __call__ = run


def build_default_pipeline() -> Pipeline:
    """Wire the real models, retriever and tools; call once (e.g. under `st.cache_resource`).

    Imports are lazy so importing this module stays cheap (no Chroma/BM25 loading at import time).
    """
    from expat.llm import get_chat_model
    from expat.rag.retrieve import HybridRetriever
    from expat.tools import get_tools

    answer_llm = get_chat_model("answer")
    static_tools = list(get_tools())
    return Pipeline(
        retriever=HybridRetriever.from_settings(),
        analysis_llm=get_chat_model("analysis"),
        answer_llm=answer_llm,
        pending_changes=load_pending_changes(),
        _static_tools=static_tools,
        _static_agent=build_answer_agent(answer_llm, static_tools),
    )
