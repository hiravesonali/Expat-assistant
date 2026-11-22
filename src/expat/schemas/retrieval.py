"""Retrieval contracts: config flags (for ablations), results, and the retriever protocol.

The SAME `retrieve()` implementation is used by the Streamlit chat, the debugger page and the
eval harness (docs/PLAN.md, "one retrieval code path").
"""

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from expat.schemas.chunks import ChunkMetadata, Domain, SectionKind
from expat.schemas.profile import UserProfile


def doc_key_matches(retrieved: str, expected: str) -> bool:
    """Golden-set matching rule: exact match, or `expected` is a prefix at a '#' boundary.

    expected "muc-anmeldung" matches retrieved "muc-anmeldung#documents";
    expected "bgb#573c" matches only "bgb#573c" (not "bgb#573").
    """
    return retrieved == expected or retrieved.startswith(expected + "#")


class SubQuery(BaseModel):
    """One retrieval unit produced by query analysis (rag/query_analysis.py), consumed by retrieval."""

    text: str  # the (sub-)question in English
    queries_en: list[str] = Field(default_factory=list)  # paraphrases (multi-query)
    queries_de: list[str] = Field(default_factory=list)  # German rewrites (cross-lingual)
    step_back: str | None = None
    domain: Domain | None = None
    domain_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    section_kinds: list[SectionKind] = Field(default_factory=list)
    legal_references: list[str] = Field(default_factory=list)  # e.g. ["§ 573c BGB"]


class Location(BaseModel):
    """Where the question is about, resolved once per turn (docs/plan-germany-wide.md, "Location rules").

    Local chunks are kept only if their city/state is listed here; nationwide chunks ("") always stay.
    Empty lists = location unknown = nationwide sources only (never another city's rules).
    """

    cities: list[str] = Field(default_factory=list)  # chunk `city` slugs, e.g. ["berlin", "munich"]
    states: list[str] = Field(default_factory=list)  # state codes, e.g. ["BE", "BY"]
    source: Literal["question", "profile", "unknown"] = "unknown"

    @property
    def known(self) -> bool:
        return bool(self.cities or self.states)


class RetrievalPlan(BaseModel):
    """The hand-off contract between query analysis and hybrid retrieval.

    Retrieval decides WHICH of these variants to use based on RetrievalConfig flags
    (e.g. R0 baseline uses only `standalone_question`).
    """

    standalone_question: str
    sub_queries: list[SubQuery]
    location: Location | None = None  # None = derive from the profile (older callers, eval plans)

    @classmethod
    def from_raw(cls, question: str) -> "RetrievalPlan":
        """Fallback/baseline plan: the raw question only (used for R0 and when analysis fails)."""
        return cls(standalone_question=question, sub_queries=[SubQuery(text=question)])


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
    # BM25 tuning (only used when use_bm25). See docs/evaluation-plan.md, "BM25 investigation".
    bm25_queries: Literal["all", "german"] = "all"  # which query variants also go to BM25
    bm25_weight: float = Field(default=1.0, ge=0.0)  # vote of a BM25 list in RRF (dense lists = 1.0)
    bm25_legal_refs: bool = False  # extra BM25 query from the extracted legal references ("573c BGB")
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
    valid_until: str = ""  # ISO date or "" (no expiry); past dates mark the source as stale
    text: str


RetrievalResult.model_rebuild()


class Retriever(Protocol):
    """Implemented by expat.rag.retrieve.HybridRetriever. Query analysis happens BEFORE this call."""

    def retrieve(
        self,
        plan: RetrievalPlan,
        profile: UserProfile | None = None,
        config: RetrievalConfig | None = None,
    ) -> RetrievalResult: ...
