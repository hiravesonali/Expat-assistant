"""Retrieval contracts: config flags (for ablations), results, and the retriever protocol.

The SAME `retrieve()` implementation is used by the Streamlit chat, the debugger page and the
eval harness (docs/PLAN.md, "one retrieval code path").
"""

from typing import Protocol

from pydantic import BaseModel, Field

from expat.schemas.chunks import ChunkMetadata
from expat.schemas.profile import UserProfile


class RetrievalConfig(BaseModel):
    """Feature flags map 1:1 to the ablation rows R0..R7 in docs/evaluation-plan.md."""

    use_german_rewrite: bool = True  # R1
    use_multi_query: bool = True  # R2
    use_decomposition: bool = True  # R3
    use_bm25: bool = True  # R4
    use_filters: bool = True  # R5
    use_rerank: bool = False  # R6 (stretch)
    use_hyde: bool = False  # R7 (stretch)
    use_step_back: bool = True
    k_dense: int = 20
    k_sparse: int = 20
    k_final: int = 8
    rrf_c: int = 60

    @classmethod
    def baseline(cls) -> "RetrievalConfig":
        """R0: raw query, vector only, no filters."""
        return cls(
            use_german_rewrite=False,
            use_multi_query=False,
            use_decomposition=False,
            use_bm25=False,
            use_filters=False,
            use_step_back=False,
        )


class RankedHit(BaseModel):
    """A child chunk with its fused score and per-list ranks (shown in the debugger)."""

    chunk_id: str
    text: str
    metadata: ChunkMetadata
    fused_score: float
    ranks: dict[str, int] = Field(default_factory=dict)  # e.g. {"dense:de:0": 3, "bm25:de:0": 1}


class SubQuestionResult(BaseModel):
    sub_question: str
    queries: list[str]
    where: dict | None = None
    hits: list[RankedHit]


class RetrievalResult(BaseModel):
    standalone_question: str
    sub_results: list[SubQuestionResult]
    parents: list["ContextSource"]  # expanded + deduplicated, in rank order

    def all_doc_keys(self) -> list[str]:
        """Ranked, deduplicated doc_keys across sub-questions (used by retrieval evals)."""
        seen: dict[str, None] = {}
        for sub in self.sub_results:
            for hit in sub.hits:
                seen.setdefault(hit.metadata.doc_key, None)
        return list(seen)


class ContextSource(BaseModel):
    """A numbered source block handed to the answer model ([S1], [S2], ...)."""

    source_id: str  # "S1"
    parent_id: str
    chunk_ids: list[str]
    doc_key: str
    title: str
    heading_path: str
    source_name: str
    source_url: str
    legal_reference: str = ""
    language: str
    last_verified: str
    text: str


RetrievalResult.model_rebuild()


class Retriever(Protocol):
    def retrieve(
        self,
        question: str,
        profile: UserProfile | None = None,
        history: list[dict] | None = None,
        config: RetrievalConfig | None = None,
    ) -> RetrievalResult: ...
