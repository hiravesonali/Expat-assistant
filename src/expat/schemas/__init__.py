"""Pydantic data contracts (think: TypeScript interfaces + zod) shared across the package."""

from expat.schemas.chunks import (
    Audience,
    ChunkMetadata,
    ChunkRecord,
    Domain,
    Jurisdiction,
    ParentRecord,
    SectionKind,
    SourceType,
)
from expat.schemas.events import (
    AnswerMetaEvent,
    Citation,
    CitationsEvent,
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
    RankedHit,
    RetrievalConfig,
    RetrievalResult,
    Retriever,
    SubQuestionResult,
)

__all__ = [
    "AnswerMetaEvent",
    "Audience",
    "ChunkMetadata",
    "ChunkRecord",
    "Citation",
    "CitationsEvent",
    "ContextSource",
    "Domain",
    "DoneEvent",
    "ErrorEvent",
    "Jurisdiction",
    "ParentRecord",
    "PipelineEvent",
    "RankedHit",
    "RetrievalConfig",
    "RetrievalResult",
    "Retriever",
    "SectionKind",
    "SourceType",
    "StepEvent",
    "SubQuestionResult",
    "TokenEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "UserProfile",
]
