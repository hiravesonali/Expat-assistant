"""Typed events emitted by the RAG pipeline (expat.rag.pipeline.run) and rendered by the Streamlit UI.

This replaces the HTTP/SSE contract of docs/api-contract.md for the Streamlit-primary MVP (ADR-0009):
the pipeline is a generator of these events; a future FastAPI layer would serialise the same events as SSE.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class StepEvent(BaseModel):
    type: Literal["step"] = "step"
    name: Literal["query_analysis", "retrieval", "rerank", "tool_call", "generation", "safety"]
    status: Literal["started", "completed", "failed"]
    detail: dict[str, Any] = Field(default_factory=dict)


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    args: dict[str, Any]


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    name: str
    result: dict[str, Any]
    error: str | None = None


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class Citation(BaseModel):
    id: str  # "S1" (retrieved source) or "T1" (tool result)
    kind: Literal["source", "tool"] = "source"
    title: str
    source_name: str = ""
    source_url: str = ""
    heading_path: str = ""
    legal_reference: str = ""
    last_verified: str = ""
    quote: str = ""


class CitationsEvent(BaseModel):
    type: Literal["citations"] = "citations"
    citations: list[Citation]


class AnswerMetaEvent(BaseModel):
    type: Literal["answer_meta"] = "answer_meta"
    confidence: Literal["grounded", "partial", "insufficient"]
    stale_sources: list[str] = Field(default_factory=list)
    unverified_refs: list[str] = Field(default_factory=list)  # § tripwire hits
    # Tokens are streamed BEFORE post-checks run; this is the cleaned text (invalid citations stripped)
    # that the UI should persist/re-render. None = use the streamed text as-is.
    final_answer: str | None = None


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    run_id: str | None = None
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    retryable: bool = False


PipelineEvent = (
    StepEvent | ToolCallEvent | ToolResultEvent | TokenEvent | CitationsEvent | AnswerMetaEvent | DoneEvent | ErrorEvent
)
