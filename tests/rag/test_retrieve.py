"""Offline tests for HybridRetriever over the synthetic corpus (fake hash embeddings + real BM25)."""

from datetime import date
from pathlib import Path

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from expat.config import Settings
from expat.llm import EmbeddingAdapter
from expat.rag.retrieve import HybridRetriever, select_sub_queries, select_variants
from expat.schemas import (
    Domain,
    RetrievalConfig,
    RetrievalPlan,
    Retriever,
    SubQuery,
    UserProfile,
)
from expat.store.bm25 import BM25Index
from expat.store.docstore import ParentDocstore
from expat.store.index import index_corpus
from expat.store.synthetic import synthetic_chunks, synthetic_parents
from expat.store.vectorstore import ChunkVectorStore

SETTINGS = Settings(_env_file=None)
MUNICH = UserProfile(city="munich")  # the synthetic corpus has Munich + Berlin procedures


@pytest.fixture
def retriever(tmp_path: Path) -> HybridRetriever:
    store = ChunkVectorStore(
        EmbeddingAdapter(DeterministicFakeEmbedding(size=32), "test/fake"),
        persist_dir=tmp_path / "chroma",
        collection_name="test",
        settings=SETTINGS,
    )
    docstore = ParentDocstore(tmp_path / "docstore.sqlite")
    index_corpus(synthetic_chunks(), synthetic_parents(), store, docstore, tmp_path / "bm25")
    return HybridRetriever(
        store,
        docstore,
        bm25=BM25Index.load(tmp_path / "bm25"),
        today=lambda: date(2026, 11, 17),
        settings=SETTINGS,
    )


def _plan() -> RetrievalPlan:
    return RetrievalPlan(
        standalone_question="What notice period applies when I cancel my Munich rental and register?",
        sub_queries=[
            SubQuery(
                text="What is the notice period for tenants?",
                queries_en=["tenant notice period termination"],
                queries_de=["Kündigungsfristen Mietvertrag § 573c"],
                step_back="How can a residential lease be terminated in Germany?",
                domain=Domain.TENANCY,
                domain_confidence=0.9,
                legal_references=["§ 573c BGB"],
            ),
            SubQuery(
                text="Which documents do I need to register my address?",
                queries_de=["Anmeldung Unterlagen Reisepass Wohnungsgeberbestätigung"],
                domain=Domain.BUREAUCRACY,
                domain_confidence=0.9,
            ),
        ],
    )


def test_satisfies_retriever_protocol(retriever: HybridRetriever) -> None:
    proto: Retriever = retriever  # static check; runtime check below
    assert callable(proto.retrieve)


def test_r0_uses_only_the_standalone_question() -> None:
    subs = select_sub_queries(_plan(), RetrievalConfig.baseline())
    assert len(subs) == 1
    assert [v.text for v in select_variants(subs[0], RetrievalConfig.baseline())] == [_plan().standalone_question]


def test_full_config_variant_selection() -> None:
    cfg = RetrievalConfig()
    subs = select_sub_queries(_plan(), cfg)
    assert [s.text for s in subs] == [s.text for s in _plan().sub_queries]
    labels = [v.label for v in select_variants(subs[0], cfg)]
    assert labels == ["en:0", "de:0", "en:1", "stepback:0"]


def test_decomposition_off_merges_rewrites_into_one_sub_query() -> None:
    cfg = RetrievalConfig(use_decomposition=False, use_multi_query=False, use_step_back=False)
    (merged,) = select_sub_queries(_plan(), cfg)
    assert merged.text == _plan().standalone_question
    assert merged.domain is None  # two different domains -> no domain
    assert [v.label for v in select_variants(merged, cfg)] == ["en:0", "de:0", "de:1"]


def test_r0_run_is_dense_only_and_unfiltered(retriever: HybridRetriever) -> None:
    debug = retriever.retrieve_debug(_plan(), MUNICH, RetrievalConfig.baseline())
    (sub,) = debug.sub_questions
    assert [lst.name for lst in sub.lists] == ["dense:en:0"]
    assert sub.where is None
    assert len(debug.result.sub_results[0].hits) == len(synthetic_chunks())  # nothing filtered out


def test_full_run_filters_and_finds_exact_paragraph(retriever: HybridRetriever) -> None:
    result = retriever.retrieve(_plan(), MUNICH, RetrievalConfig())
    tenancy, bureaucracy = result.sub_results
    assert tenancy.hits[0].metadata.doc_key == "bgb#573c"  # BM25 "573c" + § boost
    assert {"dense:en:0", "bm25:de:0"} <= set(tenancy.hits[0].ranks)
    assert {h.metadata.domain for h in tenancy.hits} == {"tenancy"}  # confident -> hard domain filter
    assert "by-mieterschutzv#1" not in {h.metadata.doc_key for h in tenancy.hits}  # expired
    assert bureaucracy.hits[0].metadata.doc_key == "muc-anmeldung#documents"
    assert "ber-anmeldung#documents" not in {h.metadata.doc_key for h in bureaucracy.hits}  # other city


def test_parents_are_deduplicated_and_numbered(retriever: HybridRetriever) -> None:
    result = retriever.retrieve(_plan(), MUNICH, RetrievalConfig())
    parent_ids = [s.parent_id for s in result.parents]
    assert len(parent_ids) == len(set(parent_ids))
    assert [s.source_id for s in result.parents] == [f"S{i}" for i in range(1, len(parent_ids) + 1)]
    bgb = next(s for s in result.parents if s.parent_id == "bgb#573c")
    assert len(bgb.chunk_ids) == 2  # Abs. 1 and Abs. 2 -> one parent block
    # Round-robin order: the top hit of EACH sub-question comes before any second-ranked hit.
    assert parent_ids[:2] == ["bgb#573c", "muc-anmeldung"]


def test_budget_falls_back_to_child_chunks(retriever: HybridRetriever) -> None:
    # Budget 40 -> quota 20 per sub-question. The § 573c parent (54 tok) never fits; in the second
    # pass its top child (~39 tok) does, so we get a small child-only block instead of no context.
    retriever.context_token_budget = 40
    debug = retriever.retrieve_debug(_plan(), MUNICH, RetrievalConfig())
    assert debug.context_tokens <= 40
    (source,) = debug.result.parents
    child_texts = {c.text for c in synthetic_chunks()}
    assert source.parent_id == "bgb#573c"
    assert source.text in child_texts


def test_all_doc_keys_ranked(retriever: HybridRetriever) -> None:
    keys = retriever.retrieve(_plan(), MUNICH, RetrievalConfig()).all_doc_keys()
    assert keys[0] == "bgb#573c"
    assert len(keys) == len(set(keys))


def _sub_and_variants():
    from expat.rag.retrieve import QueryVariant

    sub = SubQuery(
        text="When does my tenancy end?",
        queries_de=["Kündigungsfrist Mieter"],
        queries_en=["tenant notice period"],
        legal_references=["§ 573c Abs. 1 BGB"],
    )
    variants = [
        QueryVariant(label="en:0", text=sub.text),
        QueryVariant(label="de:0", text="Kündigungsfrist Mieter"),
        QueryVariant(label="en:1", text="tenant notice period"),
    ]
    return sub, variants


def test_bm25_queries_all_mirrors_dense_variants() -> None:
    from expat.rag.retrieve import bm25_queries

    sub, variants = _sub_and_variants()
    assert [label for label, _ in bm25_queries(sub, variants, RetrievalConfig())] == ["en:0", "de:0", "en:1"]


def test_bm25_queries_german_only_plus_legal_reference_query() -> None:
    from expat.rag.retrieve import bm25_queries

    sub, variants = _sub_and_variants()
    cfg = RetrievalConfig(bm25_queries="german", bm25_legal_refs=True)
    assert bm25_queries(sub, variants, cfg) == [("de:0", "Kündigungsfrist Mieter"), ("ref:0", "573c 1 BGB")]


def test_bm25_queries_german_falls_back_to_the_question_without_rewrites() -> None:
    from expat.rag.retrieve import QueryVariant, bm25_queries

    sub = SubQuery(text="Wie lang ist die Kündigungsfrist?")
    only = [QueryVariant(label="en:0", text=sub.text)]
    assert bm25_queries(sub, only, RetrievalConfig(bm25_queries="german")) == [("en:0", sub.text)]
