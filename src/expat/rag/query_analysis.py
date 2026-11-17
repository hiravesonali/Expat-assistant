"""Query translation as ONE structured-output call (ADR-0005, rag-pipeline.md §1).

`analyze()` asks a cheap model to fill a `QueryAnalysis` (standalone question, intent, domains,
EN/DE rewrites, sub-questions, step-back, filters) and `QueryAnalysis.to_plan()` turns it into the
`RetrievalPlan` hand-off contract that the retriever consumes.

Strict-mode compatibility (OpenAI-style `json_schema` with `strict: true`, which OpenRouter forwards):
- every object must list ALL its properties in `required` -> no field has a default here;
- every object must set `additionalProperties: false` -> `extra="forbid"` on every model;
- an optional value is expressed as "required but nullable" (`str | None` without a default);
- no open dicts (`dict[str, Any]`) and no numeric `minimum`/`maximum` (not supported by every
  provider); confidences are clamped in `to_plan()` instead.
tests/rag/test_query_analysis.py walks the generated JSON schema and asserts these rules.
"""

import logging
from collections.abc import Sequence
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langsmith import traceable
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from expat.rag.prompts import QUERY_ANALYSIS_PROMPT_VERSION, QUERY_ANALYSIS_SYSTEM_PROMPT, QUERY_ANALYSIS_USER_TEMPLATE
from expat.schemas.chunks import Domain, SectionKind
from expat.schemas.profile import UserProfile
from expat.schemas.retrieval import RetrievalPlan, SubQuery

logger = logging.getLogger(__name__)

Intent = Literal["info", "calculation", "checklist", "mixed", "out_of_scope", "sensitive", "chitchat"]

# Intents that skip retrieval entirely (see pipeline.py).
SHORT_CIRCUIT_INTENTS: frozenset[str] = frozenset({"out_of_scope", "sensitive", "chitchat"})

# Caps applied in to_plan(): the prompt asks for these limits, but we never trust an LLM to obey
# them, because every extra query variant costs a dense + a BM25 search per sub-question.
MAX_SUB_QUESTIONS = 4
MAX_QUERIES_EN = 3
MAX_QUERIES_DE = 2


class DomainScore(BaseModel):
    """A routing decision: one domain plus how sure the model is (>= 0.7 becomes a hard filter)."""

    model_config = ConfigDict(extra="forbid")

    domain: Domain
    confidence: float = Field(description="0.0 to 1.0")


class SubQuestion(BaseModel):
    """One independently retrievable part of the question (decomposition)."""

    model_config = ConfigDict(extra="forbid")

    text_en: str = Field(description="The sub-question in English.")
    queries_en: list[str] = Field(description="1-3 English paraphrases incl. German terms in parentheses.")
    queries_de: list[str] = Field(description="1-2 German keyword queries in authority language.")
    step_back: str | None = Field(description="A more general question, only for specific legal questions.")
    domain: Domain | None
    section_kinds: list[SectionKind]
    legal_references: list[str] = Field(description='e.g. ["§ 573c BGB"]; [] if unsure.')


class QueryAnalysis(BaseModel):
    """Everything the retrieval step needs, produced by a single LLM call.

    Runtime-only information (whether this is a fallback, token usage) lives in private
    attributes, so it never leaks into the JSON schema the model has to fill.
    """

    model_config = ConfigDict(extra="forbid")

    standalone_question: str = Field(description="The question rewritten to be understandable without history.")
    language: Literal["en", "de", "other"]
    intent: Intent
    domains: list[DomainScore]
    sub_questions: list[SubQuestion]
    needs_clarification: str | None = Field(description="A question to ask the user, or null.")

    _fallback_reason: str | None = PrivateAttr(default=None)
    _input_tokens: int = PrivateAttr(default=0)
    _output_tokens: int = PrivateAttr(default=0)

    @property
    def is_fallback(self) -> bool:
        """True when the LLM call failed and this object was built from the raw question."""
        return self._fallback_reason is not None

    @property
    def fallback_reason(self) -> str | None:
        return self._fallback_reason

    @property
    def usage(self) -> tuple[int, int]:
        """(input_tokens, output_tokens) of the analysis call, for the DoneEvent."""
        return self._input_tokens, self._output_tokens

    @classmethod
    def fallback(cls, question: str, reason: str) -> "QueryAnalysis":
        """Graceful degradation (ADR-0005): treat the raw question as a single `info` query.

        `to_plan()` of a fallback is exactly `RetrievalPlan.from_raw(question)`, i.e. the R0
        baseline, so a broken analysis model degrades quality but never breaks the chat.
        """
        analysis = cls(
            standalone_question=question,
            language="other",
            intent="info",
            domains=[],
            sub_questions=[],
            needs_clarification=None,
        )
        analysis._fallback_reason = reason
        return analysis

    def to_plan(self) -> RetrievalPlan:
        """Convert to the retrieval hand-off contract, sanitising the LLM output on the way.

        Why sanitise here and not in the retriever: the retriever should be able to trust its
        input (it is also called by the eval harness with hand-written plans).
        """
        if self.is_fallback or not self.sub_questions:
            return RetrievalPlan.from_raw(self.standalone_question)

        # The confidence for a sub-question comes from the top-level routing decision.
        confidence_by_domain: dict[Domain, float] = {}
        for score in self.domains:
            clamped = min(max(score.confidence, 0.0), 1.0)
            confidence_by_domain[score.domain] = max(clamped, confidence_by_domain.get(score.domain, 0.0))

        sub_queries = [
            SubQuery(
                text=sub.text_en.strip() or self.standalone_question,
                queries_en=_clean(sub.queries_en, MAX_QUERIES_EN),
                queries_de=_clean(sub.queries_de, MAX_QUERIES_DE),
                step_back=(sub.step_back or "").strip() or None,
                domain=sub.domain,
                domain_confidence=confidence_by_domain.get(sub.domain, 0.0) if sub.domain else 0.0,
                section_kinds=list(dict.fromkeys(sub.section_kinds)),
                legal_references=_clean(sub.legal_references, limit=None),
            )
            for sub in self.sub_questions[:MAX_SUB_QUESTIONS]
        ]
        return RetrievalPlan(standalone_question=self.standalone_question, sub_queries=sub_queries)


def _clean(values: Sequence[str], limit: int | None) -> list[str]:
    """Strip, drop empties and duplicates (order-preserving), then cap the length."""
    unique = list(dict.fromkeys(v.strip() for v in values if v.strip()))
    return unique if limit is None else unique[:limit]


def format_history(history: Sequence[BaseMessage], max_messages: int) -> str:
    """Render the last `max_messages` turns as "role: text" lines for the prompt."""
    lines: list[str] = []
    for message in list(history)[-max_messages:] if max_messages > 0 else []:
        role = "user" if message.type == "human" else "assistant" if message.type == "ai" else message.type
        lines.append(f"{role}: {message.text.strip()}")
    return "\n".join(lines) or "(none)"


@traceable(name="query_analysis", run_type="chain", metadata={"prompt_version": QUERY_ANALYSIS_PROMPT_VERSION})
def analyze(
    question: str,
    history: Sequence[BaseMessage],
    profile: UserProfile | None,
    llm: BaseChatModel,
    *,
    max_history_messages: int = 12,
) -> QueryAnalysis:
    """Run the single structured-output analysis call; never raises.

    `include_raw=True` makes LangChain return {"raw", "parsed", "parsing_error"} instead of
    raising on invalid JSON, which gives us both the parse error and the token usage.
    Any failure (network, invalid schema, refusal) falls back to the raw question.
    """
    profile_line = profile.summary() if profile else "User: profile unknown."
    messages = [
        SystemMessage(QUERY_ANALYSIS_SYSTEM_PROMPT),
        HumanMessage(
            QUERY_ANALYSIS_USER_TEMPLATE.format(
                history=format_history(history, max_history_messages), profile=profile_line, question=question
            )
        ),
    ]
    try:
        structured = llm.with_structured_output(QueryAnalysis, method="json_schema", strict=True, include_raw=True)
        result = structured.invoke(messages)
    except Exception as exc:  # any provider/network error: degrade, don't crash the chat
        logger.warning("Query analysis failed, falling back to the raw question: %s", exc)
        return QueryAnalysis.fallback(question, reason=f"{type(exc).__name__}: {exc}")

    parsed = result.get("parsed") if isinstance(result, dict) else result
    if not isinstance(parsed, QueryAnalysis):
        error = result.get("parsing_error") if isinstance(result, dict) else None
        logger.warning("Query analysis returned no valid QueryAnalysis (%s); using the raw question.", error)
        return QueryAnalysis.fallback(question, reason=f"invalid output: {error}")

    raw = result.get("raw") if isinstance(result, dict) else None
    usage = getattr(raw, "usage_metadata", None) or {}
    parsed._input_tokens = int(usage.get("input_tokens", 0))
    parsed._output_tokens = int(usage.get("output_tokens", 0))
    return parsed
