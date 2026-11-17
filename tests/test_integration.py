"""Offline integration test: the REAL retriever + tools + pipeline wired together via `Pipeline`.

Only the LLMs and embeddings are fakes. This guards the seams between modules that were built
in parallel (retrieval contract, tool registry, event stream, Streamlit adapter expectations).
"""

import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).parent / "rag"))  # shared fakes live in tests/rag/fakes.py
from fakes import ScriptedChatModel

from expat.config import Settings
from expat.llm import EmbeddingAdapter
from expat.rag.pipeline import Pipeline
from expat.rag.prompts import FEW_SHOT_EXAMPLES
from expat.rag.query_analysis import QueryAnalysis
from expat.rag.retrieve import HybridRetriever
from expat.schemas import (
    CitationsEvent,
    DoneEvent,
    ErrorEvent,
    RetrievalPlan,
    StepEvent,
    TokenEvent,
    UserProfile,
)
from expat.store.bm25 import BM25Index
from expat.store.docstore import ParentDocstore
from expat.store.index import index_corpus
from expat.store.synthetic import synthetic_chunks, synthetic_parents
from expat.store.vectorstore import ChunkVectorStore
from expat.tools import get_tools

PROFILE = UserProfile(citizenship="non_eu", residence_status="blue_card", housing="renting", children_count=2)


class CannedAnalysis:
    """Analysis model whose structured output is a fixed QueryAnalysis (the first few-shot example)."""

    def with_structured_output(self, schema: type, **kwargs: Any):
        from langchain_core.runnables import RunnableLambda

        parsed = QueryAnalysis.model_validate(FEW_SHOT_EXAMPLES[1].output)
        return RunnableLambda(lambda _: {"raw": AIMessage("{}"), "parsed": parsed, "parsing_error": None})


@pytest.fixture
def pipeline(tmp_path: Path) -> Pipeline:
    settings = Settings(data_dir=tmp_path)
    store = ChunkVectorStore(
        EmbeddingAdapter(DeterministicFakeEmbedding(size=32), "test/fake"),
        persist_dir=tmp_path / "chroma",
        collection_name="integration",
        settings=settings,
    )
    docstore = ParentDocstore(tmp_path / "docstore.sqlite")
    index_corpus(synthetic_chunks(), synthetic_parents(), store, docstore, tmp_path / "bm25")
    retriever = HybridRetriever(
        store, docstore, bm25=BM25Index.load(tmp_path / "bm25"), today=lambda: date(2026, 11, 17), settings=settings
    )
    answer = ScriptedChatModel(script=[AIMessage("You must give notice in writing [S1].")])
    return Pipeline(
        retriever=retriever,
        analysis_llm=CannedAnalysis(),  # type: ignore[arg-type]
        answer_llm=answer,
        _static_tools=get_tools(),
    )


def test_analyze_returns_a_plan_for_the_debugger(pipeline: Pipeline) -> None:
    plan = pipeline.analyze("How much notice do I have to give?")
    assert isinstance(plan, RetrievalPlan) and plan.sub_queries


def test_profile_adds_the_checklist_tool(pipeline: Pipeline) -> None:
    names = {t.name for t in pipeline.tools_for(PROFILE)}
    assert "generate_document_checklist" in names
    assert "generate_document_checklist" not in {t.name for t in pipeline.tools_for(None)}


def test_end_to_end_events_with_real_retriever_and_tools(pipeline: Pipeline) -> None:
    events = list(pipeline.run("How much notice do I have to give my landlord?", [], PROFILE))
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert not errors, errors
    steps = [e.name for e in events if isinstance(e, StepEvent) and e.status == "completed"]
    assert "query_analysis" in steps and "retrieval" in steps
    assert any(isinstance(e, TokenEvent) for e in events)
    citations = next(e for e in events if isinstance(e, CitationsEvent)).citations
    assert citations and citations[0].id == "S1"
    assert isinstance(events[-1], DoneEvent)
