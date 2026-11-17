"""Hybrid retrieval: query variants x (dense + BM25) -> RRF -> soft boosts -> parent expansion.

This is the ONE retrieval code path used by the chat, the Streamlit debugger and the evals
(docs/PLAN.md). Query analysis already happened; we receive a `RetrievalPlan` and decide, from the
`RetrievalConfig` flags, which of its query variants to actually use. That is what makes the
ablation rows R0..R5 (docs/evaluation-plan.md) a pure config change:

    R0  standalone question only, dense only, no filters        RetrievalConfig.baseline()
    R1  + German rewrites (queries_de)                          use_german_rewrite
    R2  + English paraphrases (queries_en)                      use_multi_query
    R3  + one retrieval per sub-question                        use_decomposition
    R4  + BM25 for every variant                                use_bm25
    R5  + hard filters and soft boosts                          use_filters
    (step-back query: use_step_back)

Per sub-question we run every (variant x retriever) as one ranked list, fuse them with RRF, apply
soft boosts, keep `k_final`. Then children are mapped to parents ("small-to-big"), deduplicated and
packed into numbered source blocks [S1]..[Sn] within the token budget.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field

from expat.config import Settings, get_settings
from expat.rag.filters import build_where, soft_boost
from expat.rag.fusion import reciprocal_rank_fusion
from expat.schemas import (
    ChunkMetadata,
    ContextSource,
    ParentRecord,
    RankedHit,
    RetrievalConfig,
    RetrievalPlan,
    RetrievalResult,
    SubQuery,
    SubQuestionResult,
    UserProfile,
)
from expat.store.bm25 import BM25Index
from expat.store.docstore import ParentDocstore
from expat.store.vectorstore import ChunkVectorStore
from expat.store.where import Where

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------------ debug model


class QueryVariant(BaseModel):
    """One query string sent to the retrievers. `label` is e.g. "de:0" and prefixes the list names."""

    label: str
    text: str


class RankedList(BaseModel):
    """The raw output of one retriever for one variant, before fusion (shown in the debugger)."""

    name: str  # "dense:de:0" / "bm25:en:1"
    query: str
    chunk_ids: list[str]
    scores: list[float]  # cosine distance (dense, lower = better) or BM25 score (higher = better)


class SubQuestionDebug(BaseModel):
    sub_question: str
    variants: list[QueryVariant]
    where: dict | None
    lists: list[RankedList]
    rrf_scores: dict[str, float] = Field(default_factory=dict)  # before soft boosts
    boosts: dict[str, float] = Field(default_factory=dict)  # chunk_id -> relative boost


class RetrievalDebug(BaseModel):
    """Everything the Streamlit debugger needs to explain a ranking; `result` is what `retrieve()` returns."""

    result: RetrievalResult
    sub_questions: list[SubQuestionDebug]
    context_tokens: int


# -------------------------------------------------------------------------------- variant choice


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i.strip() for i in items if i and i.strip()))


def select_sub_queries(plan: RetrievalPlan, config: RetrievalConfig) -> list[SubQuery]:
    """Decomposition on: the plan's sub-queries. Off: ONE sub-query built from the standalone question.

    When decomposition is off we still merge the rewrites of all sub-queries into that single
    sub-query, so R1/R2 (German rewrites, paraphrases) stay measurable independently of R3.
    """
    if config.use_decomposition and plan.sub_queries:
        return plan.sub_queries
    subs = plan.sub_queries
    domains = {s.domain for s in subs}
    single_domain = len(domains) == 1 and None not in domains
    return [
        SubQuery(
            text=plan.standalone_question,
            queries_en=_unique([q for s in subs for q in s.queries_en]),
            queries_de=_unique([q for s in subs for q in s.queries_de]),
            step_back=next((s.step_back for s in subs if s.step_back), None),
            domain=subs[0].domain if single_domain else None,
            domain_confidence=min(s.domain_confidence for s in subs) if single_domain else 0.0,
            section_kinds=list(dict.fromkeys(k for s in subs for k in s.section_kinds)),
            legal_references=_unique([r for s in subs for r in s.legal_references]),
        )
    ]


def select_variants(sub: SubQuery, config: RetrievalConfig) -> list[QueryVariant]:
    """The query strings for one sub-question, according to the flags. Duplicate strings run once."""
    candidates: list[tuple[str, str]] = [("en:0", sub.text)]
    if config.use_german_rewrite:
        candidates += [(f"de:{i}", q) for i, q in enumerate(sub.queries_de)]
    if config.use_multi_query:
        candidates += [(f"en:{i + 1}", q) for i, q in enumerate(sub.queries_en)]
    if config.use_step_back and sub.step_back:
        candidates.append(("stepback:0", sub.step_back))
    seen: set[str] = set()
    variants: list[QueryVariant] = []
    for label, text in candidates:
        key = text.strip().lower()
        if key and key not in seen:
            seen.add(key)
            variants.append(QueryVariant(label=label, text=text.strip()))
    return variants


# ------------------------------------------------------------------------------------- retriever


@dataclass
class _Candidate:
    text: str
    metadata: ChunkMetadata


@dataclass
class _Block:
    """A context block under construction (a parent, or a child-only fallback)."""

    parent_id: str
    chunk_ids: list[str]
    text: str
    tokens: int
    parent: ParentRecord | None
    first_meta: ChunkMetadata


def estimate_tokens(text: str) -> int:
    """Rough fallback when ingestion did not record `token_count`: ~3 chars/token is conservative for German."""
    return max(1, len(text) // 3)


class HybridRetriever:
    """Implements `expat.schemas.Retriever`. Construct via `from_settings()` in the app."""

    def __init__(
        self,
        vector_store: ChunkVectorStore,
        docstore: ParentDocstore,
        bm25: BM25Index | None = None,
        context_token_budget: int | None = None,
        today: Callable[[], date] = date.today,
        max_workers: int = 8,
        settings: Settings | None = None,
    ) -> None:
        s = settings or get_settings()
        self.vector_store = vector_store
        self.docstore = docstore
        self.bm25 = bm25
        self.context_token_budget = context_token_budget or s.context_token_budget
        self._today = today
        self.max_workers = max_workers

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> HybridRetriever:
        """Production wiring: OpenRouter embeddings + persisted Chroma, docstore and BM25 index."""
        from expat.llm import get_embeddings

        s = settings or get_settings()
        return cls(
            vector_store=ChunkVectorStore(get_embeddings(s), settings=s),
            docstore=ParentDocstore(s.docstore_path),
            bm25=BM25Index.load(s.bm25_dir),
            settings=s,
        )

    # ------------------------------------------------------------------------------- public API

    def retrieve(
        self,
        plan: RetrievalPlan,
        profile: UserProfile | None = None,
        config: RetrievalConfig | None = None,
    ) -> RetrievalResult:
        return self.retrieve_debug(plan, profile, config).result

    def retrieve_debug(
        self,
        plan: RetrievalPlan,
        profile: UserProfile | None = None,
        config: RetrievalConfig | None = None,
    ) -> RetrievalDebug:
        cfg = config or RetrievalConfig()
        if cfg.use_bm25 and self.bm25 is None:
            raise RuntimeError("use_bm25=True but no BM25 index was loaded")
        today = self._today()
        subs = select_sub_queries(plan, cfg)
        plans = [(sub, select_variants(sub, cfg), build_where(profile, sub, cfg, today=today)) for sub in subs]

        lists_per_sub = self._run_searches(plans, cfg)

        sub_results: list[SubQuestionResult] = []
        debugs: list[SubQuestionDebug] = []
        for (sub, variants, where), (lists, candidates) in zip(plans, lists_per_sub, strict=True):
            fused = reciprocal_rank_fusion({lst.name: lst.chunk_ids for lst in lists}, c=cfg.rrf_c)
            # Soft boosts belong to "structured retrieval" (R5): off together with the hard filters,
            # so the R4 -> R5 delta measures both.
            boosts = {
                cid: soft_boost(candidates[cid].metadata, profile, sub) if cfg.use_filters else 0.0
                for cid, _, _ in fused
            }
            hits = [
                RankedHit(
                    chunk_id=cid,
                    text=candidates[cid].text,
                    metadata=candidates[cid].metadata,
                    fused_score=score * (1.0 + boosts[cid]),
                    ranks=ranks,
                )
                for cid, score, ranks in fused
            ]
            hits.sort(key=lambda h: (-h.fused_score, h.chunk_id))
            sub_results.append(
                SubQuestionResult(
                    sub_question=sub.text,
                    queries=[v.text for v in variants],
                    where=where,
                    hits=hits[: cfg.k_final],
                )
            )
            debugs.append(
                SubQuestionDebug(
                    sub_question=sub.text,
                    variants=variants,
                    where=where,
                    lists=lists,
                    rrf_scores={cid: score for cid, score, _ in fused},
                    boosts={cid: b for cid, b in boosts.items() if b},
                )
            )

        sources, used_tokens = self._expand_parents(sub_results)
        result = RetrievalResult(standalone_question=plan.standalone_question, sub_results=sub_results, parents=sources)
        return RetrievalDebug(result=result, sub_questions=debugs, context_tokens=used_tokens)

    # ------------------------------------------------------------------------------- searching

    def _run_searches(
        self,
        plans: list[tuple[SubQuery, list[QueryVariant], Where | None]],
        cfg: RetrievalConfig,
    ) -> list[tuple[list[RankedList], dict[str, _Candidate]]]:
        """Run every (sub-question x variant x retriever) search in a thread pool.

        Dense search is dominated by the embedding API round-trip (~100-300 ms), so running the
        variants concurrently turns N sequential round-trips into roughly one. Results are collected
        in submission order, so the output is deterministic regardless of thread timing.
        """
        jobs: list[tuple[int, str, str, Where | None, str]] = []  # (sub_idx, retriever, label, where, query)
        for i, (_, variants, where) in enumerate(plans):
            for v in variants:
                jobs.append((i, "dense", v.label, where, v.text))
                if cfg.use_bm25:
                    jobs.append((i, "bm25", v.label, where, v.text))

        def run(job: tuple[int, str, str, Where | None, str]) -> tuple[RankedList, dict[str, _Candidate]]:
            _, retriever, label, where, query = job
            name = f"{retriever}:{label}"
            if retriever == "dense":
                dense = self.vector_store.query(query, k=cfg.k_dense, where=where)
                cands = {h.chunk_id: _Candidate(h.text, h.metadata) for h in dense}
                return RankedList(
                    name=name, query=query, chunk_ids=[h.chunk_id for h in dense], scores=[h.distance for h in dense]
                ), cands
            assert self.bm25 is not None
            sparse = self.bm25.search(query, k=cfg.k_sparse, where=where)
            cands = {h.chunk_id: _Candidate(h.text, h.metadata) for h in sparse}
            return RankedList(
                name=name, query=query, chunk_ids=[h.chunk_id for h in sparse], scores=[h.score for h in sparse]
            ), cands

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            outputs = list(pool.map(run, jobs))

        per_sub: list[tuple[list[RankedList], dict[str, _Candidate]]] = [([], {}) for _ in plans]
        for job, (ranked, cands) in zip(jobs, outputs, strict=True):
            lists, candidates = per_sub[job[0]]
            lists.append(ranked)
            candidates.update(cands)
        return per_sub

    # ------------------------------------------------------------------------- parent expansion

    def _expand_parents(self, sub_results: list[SubQuestionResult]) -> tuple[list[ContextSource], int]:
        """Map children to parents, dedupe, and pack within the token budget.

        * Each sub-question gets an equal quota (budget / n) so one domain cannot crowd out the
          others ("moving with kids on a Blue Card" needs Anmeldung AND Kindergeld context).
        * Hits are visited round-robin by rank across sub-questions (rank 1 of each, then rank 2...),
          which also defines the S1..Sn order: the best evidence for every sub-question comes first.
        * Two Absätze of the same § -> one block (dedupe by parent_id), chunk_ids accumulate.
        * If a parent does not fit the remaining quota, fall back to the child chunk alone: a small
          precise block beats no context for that sub-question.
        * A second pass hands unused quota to any sub-question that still has hits.
        """
        n = len(sub_results)
        if n == 0:
            return [], 0
        budget = self.context_token_budget
        quota = budget // n
        parents = self.docstore.get_many(h.metadata.parent_id for s in sub_results for h in s.hits)

        blocks: dict[str, _Block] = {}  # insertion order = source order
        spent = [0] * n
        total = 0
        placed: set[str] = set()

        def try_place(sub_idx: int, hit: RankedHit, limit_for_sub: int) -> None:
            nonlocal total
            pid = hit.metadata.parent_id
            existing = blocks.get(pid)
            if existing is not None:
                if hit.chunk_id not in existing.chunk_ids:
                    existing.chunk_ids.append(hit.chunk_id)
                    # A child-only block has only its own text: add this sibling's text if it fits.
                    extra = hit.metadata.token_count or estimate_tokens(hit.text)
                    if existing.parent is None and spent[sub_idx] + extra <= limit_for_sub and total + extra <= budget:
                        existing.text += "\n\n" + hit.text
                        existing.tokens += extra
                        spent[sub_idx] += extra
                        total += extra
                placed.add(hit.chunk_id)
                return
            parent = parents.get(pid)
            options: list[tuple[str, int, ParentRecord | None]] = []
            if parent is not None:
                options.append((parent.text, parent.token_count or estimate_tokens(parent.text), parent))
            else:
                logger.warning("parent %s missing from docstore; using the child chunk", pid)
            child_tokens = hit.metadata.token_count or estimate_tokens(hit.text)
            options.append((hit.text, child_tokens, None))
            for text, tokens, maybe_parent in options:
                if spent[sub_idx] + tokens <= limit_for_sub and total + tokens <= budget:
                    blocks[pid] = _Block(pid, [hit.chunk_id], text, tokens, maybe_parent, hit.metadata)
                    spent[sub_idx] += tokens
                    total += tokens
                    placed.add(hit.chunk_id)
                    return

        max_rank = max(len(s.hits) for s in sub_results)
        for limit in (quota, budget):  # pass 1: fair quotas; pass 2: share what is left
            for rank in range(max_rank):
                for i, sub in enumerate(sub_results):
                    if rank < len(sub.hits) and sub.hits[rank].chunk_id not in placed:
                        try_place(i, sub.hits[rank], limit)

        sources = [self._to_source(f"S{i}", b) for i, b in enumerate(blocks.values(), start=1)]
        return sources, total

    @staticmethod
    def _to_source(source_id: str, block: _Block) -> ContextSource:
        p, m = block.parent, block.first_meta
        return ContextSource(
            source_id=source_id,
            parent_id=block.parent_id,
            chunk_ids=block.chunk_ids,
            doc_key=p.doc_key if p else m.doc_key,
            title=p.title if p else m.title,
            heading_path=p.heading_path if p else m.heading_path,
            source_name=p.source_name if p else m.source_name,
            source_url=p.source_url if p else m.source_url,
            legal_reference=p.legal_reference if p else m.legal_reference,
            language=p.language if p else m.language,
            last_verified=(p.last_verified if p else m.last_verified).isoformat(),
            text=block.text,
        )
