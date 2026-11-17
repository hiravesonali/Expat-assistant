"""Answer generation: a `create_agent` tool-calling loop plus deterministic post-checks.

Design (ADR-0008, rag-pipeline.md §7–8):
- Retrieval has ALREADY happened; its result arrives as a context pack in the system prompt.
  The agent's only autonomy is deciding whether/which tools to call (dates, amounts, checklists).
- The system prompt is built per request by `@dynamic_prompt` from a typed runtime context
  (`AnswerContext`). That keeps ONE compiled agent reusable across requests (cacheable with
  `st.cache_resource`), while the profile/context/pending changes change on every call.
- Middleware gives bounded cost and resilience without hand-written loops:
  `ModelRetryMiddleware` (transient provider errors), `ModelCallLimitMiddleware` and
  `ToolCallLimitMiddleware` (max 4 tool calls), `ToolErrorMiddleware` (a failing tool becomes an
  error message the model can explain, instead of crashing the turn), and our own
  `ToolCitationMiddleware`, which labels every tool result "[T1]", "[T2]", … so the model can cite it.
- After generation, cheap regex checks catch the most harmful failure modes: invented citation ids,
  § references not backed by any cited text (the "hallucination tripwire"), and stale sources.
"""

import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelRequest,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
    dynamic_prompt,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from expat.config import get_settings
from expat.rag.prompts import (
    ANSWER_SYSTEM_TEMPLATE,
    INSUFFICIENT_CONTEXT_PHRASES,
    LANGUAGE_NAMES,
    NEXT_STEPS_HEADINGS,
    NO_PENDING_CHANGES,
)
from expat.schemas.retrieval import ContextSource

Confidence = Literal["grounded", "partial", "insufficient"]

DEFAULT_MAX_TOOL_CALLS = 4

# --------------------------------------------------------------------------------------
# Runtime context + dynamic system prompt
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AnswerContext:
    """Per-request data for the system prompt, passed as `agent.stream(..., context=...)`."""

    profile_summary: str
    context_pack: str
    language: str = "en"
    pending_changes: tuple[str, ...] = ()
    clarification: str | None = None
    today: date = field(default_factory=date.today)


AnswerAgent = CompiledStateGraph[Any, AnswerContext, Any, Any]
"""The compiled agent graph returned by `build_answer_agent` (state, context, input, output)."""


def render_answer_prompt(ctx: AnswerContext) -> str:
    """Fill the versioned answer template (prompts.ANSWER_SYSTEM_TEMPLATE) from the context."""
    lang = ctx.language if ctx.language in LANGUAGE_NAMES else "en"
    pending = "\n".join(f"- {change}" for change in ctx.pending_changes) or NO_PENDING_CHANGES
    clarification = (
        f"Possibly missing information (ask only if it changes the answer): {ctx.clarification}\n"
        if ctx.clarification
        else ""
    )
    return ANSWER_SYSTEM_TEMPLATE.format(
        today=ctx.today.isoformat(),
        profile=ctx.profile_summary,
        clarification=clarification,
        language_name=LANGUAGE_NAMES[lang],
        insufficient_phrase=INSUFFICIENT_CONTEXT_PHRASES[lang],
        next_steps_heading=NEXT_STEPS_HEADINGS[lang],
        pending_changes=pending,
        context=ctx.context_pack,
    )


@dynamic_prompt
def answer_prompt(request: ModelRequest) -> str:
    """Build the system prompt for every model call from the typed runtime context."""
    ctx = request.runtime.context
    if not isinstance(ctx, AnswerContext):
        raise TypeError("The answer agent needs `context=AnswerContext(...)` when it is invoked or streamed.")
    return render_answer_prompt(ctx)


# --------------------------------------------------------------------------------------
# Tool results become citable: [T1], [T2], ...
# --------------------------------------------------------------------------------------

TOOL_LABEL_RE = re.compile(r"^\[(T\d+)\]\s?")


def tool_citation_id(messages: Sequence[AnyMessage], call_id: str) -> str | None:
    """Number tool calls by their position across all AI messages of this run: T1, T2, ...

    Position-based numbering (instead of a counter) is deterministic even when the model makes
    several tool calls in parallel and they finish in any order.
    """
    position = 0
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                position += 1
                if call["id"] == call_id:
                    return f"T{position}"
    return None


class ToolCitationMiddleware(AgentMiddleware[Any, Any, Any]):
    """Prefix every tool result with its citation id, so the model sees "[T1] {...}".

    The pipeline reads the id back from the same prefix (`parse_tool_message`), so the label the
    model cites and the label the UI shows always come from one place.
    """

    def _label(self, request: ToolCallRequest, result: ToolMessage | Command[Any]) -> ToolMessage | Command[Any]:
        if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
            return result
        citation_id = tool_citation_id(request.state.get("messages", []), request.tool_call["id"] or "")
        if citation_id is None or TOOL_LABEL_RE.match(result.content):
            return result
        return result.model_copy(update={"content": f"[{citation_id}] {result.content}"})

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        return self._label(request, handler(request))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        return self._label(request, await handler(request))


@dataclass(frozen=True)
class ToolResultRecord:
    """A tool result as the pipeline and the post-checks see it."""

    call_id: str
    name: str
    citation_id: str | None  # None if the call was blocked (e.g. the tool-call limit)
    result: dict[str, Any]
    error: str | None = None
    text: str = ""  # the raw text the model saw, used by the § tripwire

    @property
    def citable(self) -> bool:
        return self.citation_id is not None and self.error is None


def parse_tool_message(message: ToolMessage) -> ToolResultRecord:
    """Turn a (labelled) ToolMessage back into structured data for events and citations."""
    content = message.content if isinstance(message.content, str) else json.dumps(message.content, default=str)
    match = TOOL_LABEL_RE.match(content)
    citation_id = match.group(1) if match else None
    body = content[match.end() :] if match else content

    result: dict[str, Any]
    if isinstance(message.artifact, dict):  # tools using response_format="content_and_artifact"
        result = message.artifact
    else:
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            parsed = body
        result = parsed if isinstance(parsed, dict) else {"output": parsed}

    error = body if message.status == "error" else None
    return ToolResultRecord(
        call_id=message.tool_call_id,
        name=message.name or "",
        citation_id=citation_id,
        result=result,
        error=error,
        text=body,
    )


def _tool_error_message(exc: Exception, request: ToolCallRequest) -> str:
    """Surface tool failures to the model; input errors keep their message, others only the type."""
    name = request.tool_call["name"]
    if isinstance(exc, ValueError | TypeError):
        return f"Tool `{name}` failed: {exc}. Ask the user for correct input; do not compute the result yourself."
    return f"Tool `{name}` failed ({type(exc).__name__}). Tell the user the calculation is unavailable right now."


# --------------------------------------------------------------------------------------
# Agent factory
# --------------------------------------------------------------------------------------

_TRANSIENT_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_TRANSIENT_NAMES = frozenset({"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"})


def is_transient_error(exc: Exception) -> bool:
    """Retry only what can succeed on a second try: timeouts, connection drops, 429 and 5xx.

    Duck-typed (status_code / class name) so we don't depend on the OpenAI or OpenRouter SDK's
    exception classes. A 400/401 (bad request, wrong key) is NOT retried: it would fail again.
    """
    if isinstance(exc, TimeoutError | ConnectionError | httpx.TransportError):
        return True
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status in _TRANSIENT_STATUS
    return type(exc).__name__ in _TRANSIENT_NAMES


def build_answer_agent(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    *,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    max_retries: int = 2,
    retry_initial_delay: float = 1.0,
) -> AnswerAgent:
    """Compile the answer agent once; invoke/stream it with `context=AnswerContext(...)`.

    Middleware order matters: the first entry is the outermost wrapper. The model call limit
    is `max_tool_calls + 2` (one call per tool round plus the final answer, plus one spare), so
    the loop always terminates even if the model keeps asking for blocked tools.
    """
    middleware: list[AgentMiddleware[Any, Any, Any]] = [
        answer_prompt,
        ModelRetryMiddleware(
            max_retries=max_retries,
            retry_on=is_transient_error,
            on_failure="error",  # let the pipeline emit an ErrorEvent(retryable=True)
            initial_delay=retry_initial_delay,
        ),
        ModelCallLimitMiddleware(run_limit=max_tool_calls + 2, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=max_tool_calls, exit_behavior="continue"),
        ToolCitationMiddleware(),
        ToolErrorMiddleware(on_error=_tool_error_message),
    ]
    return create_agent(
        model,
        tools=list(tools),
        middleware=middleware,
        context_schema=AnswerContext,
        name="answer_agent",
    )


# --------------------------------------------------------------------------------------
# Post-generation checks (deterministic, cheap)
# --------------------------------------------------------------------------------------

# "[S1]", "[T2]", and grouped forms like "[S1, S3]" or "[S1; T1]".
CITATION_RE = re.compile(r"(?P<space>[ \t]*)\[(?P<ids>[ST]\d+(?:\s*[,;]\s*[ST]\d+)*)\]")


@dataclass(frozen=True)
class CitationCheck:
    answer: str  # the answer with unknown markers stripped
    cited: list[str]  # valid ids in order of first use
    invalid: list[str]  # markers that were stripped


def validate_citations(
    answer: str, sources: Sequence[ContextSource], tool_results: Sequence[ToolResultRecord]
) -> CitationCheck:
    """Keep only citation markers that point at a real source or a successful tool result."""
    valid = {s.source_id for s in sources} | {t.citation_id for t in tool_results if t.citable and t.citation_id}
    cited: dict[str, None] = {}
    invalid: dict[str, None] = {}

    def _replace(match: re.Match[str]) -> str:
        ids = [part.strip() for part in re.split(r"[,;]", match.group("ids"))]
        keep = [i for i in ids if i in valid]
        for i in ids:
            (cited if i in valid else invalid).setdefault(i, None)
        if not keep:
            return ""  # drop the marker and the whitespace before it
        return f"{match.group('space')}[{', '.join(keep)}]"

    cleaned = CITATION_RE.sub(_replace, answer)
    return CitationCheck(answer=cleaned, cited=list(cited), invalid=list(invalid))


# § 573c, §§ 573, 573c, § 18g Abs. 2, "Section 17" (English answers), "Paragraf 66".
LEGAL_REF_RE = re.compile(
    r"(?P<prefix>§§?|\bSections?\b|\bParagra(?:ph|f)(?:en|s)?\b)\s*"
    r"(?P<nums>\d+[a-z]?\b(?:\s*(?:,|und|and|bis|to|or|oder|-|–)\s*\d+[a-z]?\b)*)"
    r"(?P<abs>\s*(?:Abs\.|Absatz|para\.|subsection)\s*\d+)?",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d+[a-z]?", re.IGNORECASE)


def _legal_refs(text: str) -> list[tuple[str, set[str]]]:
    """(mention, {paragraph numbers}) for every § mention in a text."""
    return [
        (match.group(0).strip(), {n.lower() for n in _NUMBER_RE.findall(match.group("nums"))})
        for match in LEGAL_REF_RE.finditer(text)
    ]


def find_unverified_legal_refs(answer: str, cited_texts: Sequence[str]) -> list[str]:
    """The § tripwire: § mentions in the answer whose paragraph number no cited text contains.

    Compares paragraph numbers ("573c"), not the law name: a § from the wrong law that happens to
    share the number slips through, but an invented paragraph (the common hallucination) is caught.
    "Abs." is kept in the reported mention but not verified, because a § text rarely repeats its
    own Absatz numbers in a matchable form.
    """
    verified: set[str] = set()
    for text in cited_texts:
        for _, numbers in _legal_refs(text):
            verified |= numbers
    unverified: dict[str, None] = {}
    for mention, numbers in _legal_refs(answer):
        if not numbers <= verified:
            unverified.setdefault(mention, None)
    return list(unverified)


def stale_sources(
    sources: Sequence[ContextSource], *, today: date | None = None, staleness_days: int | None = None
) -> list[str]:
    """Source ids that are stale: `last_verified` older than `settings.staleness_days` (or unparsable),
    or past their `valid_until` date (e.g. a regulation that expired).
    """
    today = today or date.today()
    max_age = timedelta(days=staleness_days if staleness_days is not None else get_settings().staleness_days)
    stale: list[str] = []
    for source in sources:
        try:
            verified = date.fromisoformat(source.last_verified[:10])
        except ValueError:
            stale.append(source.source_id)
            continue
        expired = bool(source.valid_until) and source.valid_until[:10] < today.isoformat()
        if today - verified > max_age or expired:
            stale.append(source.source_id)
    return stale


def assess_confidence(
    answer: str,
    *,
    has_evidence: bool,
    citations: CitationCheck,
    unverified_refs: Sequence[str],
) -> Confidence:
    """Deterministic confidence label for AnswerMetaEvent.

    insufficient: no evidence at all, or the model used the prescribed fallback sentence.
    partial: something is off (no citations, stripped citations, unverified §).
    grounded: every check passed.
    """
    if not has_evidence or any(phrase in answer for phrase in INSUFFICIENT_CONTEXT_PHRASES.values()):
        return "insufficient"
    if not citations.cited or citations.invalid or unverified_refs:
        return "partial"
    return "grounded"
