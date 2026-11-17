"""Offline fakes for the answer agent and pipeline tests (imported as `from fakes import ...`:
pytest puts a test folder without __init__.py on sys.path).

LangChain's `GenericFakeChatModel` replays scripted messages but (a) raises on `bind_tools`, which
`create_agent` calls, and (b) drops `tool_calls` when streaming. `ScriptedChatModel` fixes both,
records the prompts it receives, and can raise a scripted exception (to test retries).
"""

import re
from collections.abc import Iterator, Sequence
from datetime import date
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import tool
from pydantic import Field

from expat.schemas import ChunkMetadata, ContextSource, RankedHit, RetrievalResult, SubQuestionResult
from expat.schemas.profile import UserProfile
from expat.schemas.retrieval import RetrievalConfig, RetrievalPlan


class ScriptedChatModel(BaseChatModel):
    script: list[Any]  # AIMessage | Exception; Any avoids pydantic coercing an Exception into a message
    received: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: str | None = None, **kwargs: Any) -> Runnable:
        return self

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        self.received.append(messages)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        message = self._next(messages)
        tokens = [t for t in re.split(r"(\s)", message.text) if t] or [""]
        for i, token in enumerate(tokens):
            last = i == len(tokens) - 1
            chunk = AIMessageChunk(
                content=token,
                id=message.id,
                tool_call_chunks=[
                    {"name": c["name"], "args": _json(c["args"]), "id": c["id"], "index": n}
                    for n, c in enumerate(message.tool_calls)
                ]
                if last
                else [],
                usage_metadata=message.usage_metadata if last else None,
            )
            if last:
                chunk.chunk_position = "last"
            if run_manager:
                run_manager.on_llm_new_token(token, chunk=ChatGenerationChunk(message=chunk))
            yield ChatGenerationChunk(message=chunk)


def _json(value: Any) -> str:
    import json

    return json.dumps(value)


def tool_call_message(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


@tool
def notice_period(tenancy_start: str, notice_date: str) -> dict:
    """Calculate the landlord's notice period (fake for tests)."""
    return {"notice_months": 6, "end_date": "2027-05-31", "legal_basis": "§ 573c BGB"}


def make_source(source_id: str = "S1", **overrides: Any) -> ContextSource:
    data: dict[str, Any] = {
        "source_id": source_id,
        "parent_id": "bgb#573c",
        "chunk_ids": ["c1"],
        "doc_key": "bgb#573c",
        "title": "Kündigungsfristen",
        "heading_path": "BGB > § 573c",
        "source_name": "Gesetze im Internet",
        "source_url": "https://www.gesetze-im-internet.de/bgb/__573c.html",
        "legal_reference": "§ 573c BGB",
        "language": "de",
        "last_verified": "2026-11-10",
        "text": "(1) Die Kündigung ist spätestens am dritten Werktag eines Kalendermonats zulässig ...",
    }
    data.update(overrides)
    return ContextSource(**data)


def _hit(source: ContextSource) -> RankedHit:
    metadata = ChunkMetadata(
        chunk_id=source.chunk_ids[0],
        parent_id=source.parent_id,
        doc_id="d1",
        doc_key=source.doc_key,
        doc_version="v1",
        content_hash="h",
        domain="tenancy",
        source_type="law",
        source_id="bgb",
        source_name=source.source_name,
        source_url=source.source_url,
        title=source.title,
        language="de",
        jurisdiction="federal",
        last_verified=date.fromisoformat(source.last_verified),
    )
    return RankedHit(chunk_id=metadata.chunk_id, text=source.text, metadata=metadata, fused_score=0.0328)


class FakeRetriever:
    """Implements the `Retriever` protocol with canned sources and records the plan it got."""

    def __init__(self, sources: list[ContextSource] | None = None, error: Exception | None = None) -> None:
        self.sources = [make_source()] if sources is None else sources
        self.error = error
        self.calls: list[tuple[RetrievalPlan, UserProfile | None, RetrievalConfig | None]] = []

    def retrieve(
        self, plan: RetrievalPlan, profile: UserProfile | None = None, config: RetrievalConfig | None = None
    ) -> RetrievalResult:
        self.calls.append((plan, profile, config))
        if self.error:
            raise self.error
        sub_results = [
            SubQuestionResult(
                sub_question=q.text, queries=[q.text, *q.queries_de], hits=[_hit(s) for s in self.sources]
            )
            for q in plan.sub_queries
        ]
        return RetrievalResult(
            standalone_question=plan.standalone_question, sub_results=sub_results, parents=self.sources
        )
