"""Ablation runner with fake targets: no index, no LLM, no network."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from expat.evals.dataset import DEFAULT_GOLDEN_PATH, load_golden
from expat.evals.retrieval_eval import (
    AnalysisCache,
    ablation_variants,
    make_target_factory,
    needs_query_analysis,
    retrieval_examples,
    run_retrieval_ablation,
)
from expat.schemas import RetrievalConfig, RetrievalPlan, RetrievalResult, UserProfile

GOLDEN = {e.question: e for e in load_golden(DEFAULT_GOLDEN_PATH)}
# Dev examples that have expected sources (refusals and "which city?" clarifications have none).
N_DEV_RETRIEVAL = len(retrieval_examples(load_golden(DEFAULT_GOLDEN_PATH, split="dev")))


def oracle_factory(config: RetrievalConfig):
    """Perfect retriever when BM25 is on, useless otherwise: R4/R5 must score 1.0, R0-R3 must score 0.0."""

    def target(question: str, profile: UserProfile) -> list[str]:
        example = GOLDEN[question]
        if config.use_bm25:
            return [*example.required_doc_keys, "noise#1"]
        return ["noise#1", "noise#2"]

    return target


def test_variants_are_cumulative_and_r5_is_production_default() -> None:
    variants = ablation_variants(include_stretch=True)
    assert list(variants) == ["R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    assert variants["R0"] == RetrievalConfig.baseline()
    assert variants["R5"] == RetrievalConfig()
    assert variants["R1"].use_german_rewrite and not variants["R1"].use_multi_query
    assert variants["R4"].use_bm25 and not variants["R4"].use_filters
    assert variants["R6"].use_rerank and not variants["R6"].use_hyde
    assert variants["R7"].use_hyde and not variants["R7"].use_rerank
    assert "R6" not in ablation_variants()


def test_run_retrieval_ablation_local_writes_json(tmp_path: Path) -> None:
    variants = {k: v for k, v in ablation_variants().items() if k in ("R0", "R4")}
    results = run_retrieval_ablation(oracle_factory, variants, split="dev", mode="local", results_dir=tmp_path)

    assert [r.variant for r in results] == ["R0", "R4"]
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 2
    data = json.loads(next(f for f in files if "-R4-" in f.name).read_text(encoding="utf-8"))
    # required keys of the documented format
    assert {"experiment", "config", "metrics", "per_slice", "n", "created_at"} <= data.keys()
    assert data["n"] == N_DEV_RETRIEVAL
    assert data["metrics"]["hit@5"] == 1.0
    assert data["metrics"]["recall@10"] == 1.0
    assert data["metrics"]["mrr@10"] == 1.0
    assert data["metrics"]["latency_p50_ms"] is not None
    assert data["config"]["use_bm25"] is True
    assert "out_of_scope" not in data["per_slice"]
    assert data["per_slice"]["tenancy"]["hit@5"] == 1.0
    assert data["per_slice"]["lang:de"]["n"] == sum(
        1 for e in retrieval_examples(load_golden(DEFAULT_GOLDEN_PATH, split="dev")) if e.language == "de"
    )

    r0 = next(r for r in results if r.variant == "R0")
    assert r0.metrics["hit@5"] == 0.0 and r0.metrics["mrr@10"] == 0.0


def test_failing_target_counts_as_miss_and_error(tmp_path: Path) -> None:
    def factory(config: RetrievalConfig):
        def target(question: str, profile: UserProfile) -> list[str]:
            raise RuntimeError("chroma down")

        return target

    variants = {"R0": RetrievalConfig.baseline()}
    [result] = run_retrieval_ablation(factory, variants, split="holdout", results_dir=tmp_path)
    n_holdout = len(retrieval_examples(load_golden(DEFAULT_GOLDEN_PATH, split="holdout")))
    assert result.errors == result.n == n_holdout
    assert result.metrics["hit@5"] == 0.0
    assert "chroma down" in (result.per_example[0].error or "")


def test_needs_query_analysis() -> None:
    assert not needs_query_analysis(RetrievalConfig.baseline())
    assert needs_query_analysis(ablation_variants()["R1"])


def test_make_target_factory_caches_analysis_and_skips_it_for_r0() -> None:
    calls: list[str] = []

    def analyze(question: str, profile: UserProfile) -> RetrievalPlan:
        calls.append(question)
        return RetrievalPlan.from_raw(question + " (analysed)")

    seen_plans: list[tuple[str, bool]] = []

    class FakeRetriever:
        def retrieve(self, plan, profile=None, config=None) -> RetrievalResult:
            seen_plans.append((plan.standalone_question, config.use_bm25))
            return RetrievalResult(standalone_question=plan.standalone_question, sub_results=[], parents=[])

    cache = AnalysisCache(analyze)
    factory = make_target_factory(FakeRetriever(), cache)
    profile = UserProfile()
    for config in ablation_variants().values():
        factory(config)("q?", profile)

    assert calls == ["q?"]  # one analysis call shared by R1..R5
    assert seen_plans[0] == ("q?", False)  # R0 got the raw question
    assert all(q == "q? (analysed)" for q, _ in seen_plans[1:])


def test_analysis_cache_rejects_wrong_type() -> None:
    cache = AnalysisCache(lambda q, p: {"not": "a plan"})  # type: ignore[arg-type,return-value]
    with pytest.raises(TypeError):
        cache.get("q", UserProfile())


# --- langsmith mode with a fake client ---------------------------------------------------------------------------


class FakeExperimentResults(list):
    """LangSmith's ExperimentResults is iterable over row dicts and exposes `experiment_name`."""

    experiment_name = "R4-retrieval-abc"


class FakeLangSmithClient:
    """Mimics list_examples + evaluate just enough: calls the target and evaluators like LangSmith would."""

    def __init__(self) -> None:
        self.evaluate_kwargs: dict[str, Any] = {}

    def list_examples(self, *, dataset_name: str, splits: list[str]):
        for e in load_golden(DEFAULT_GOLDEN_PATH, split=splits[0]):
            payload = e.to_langsmith_example()
            yield SimpleNamespace(
                inputs=payload["inputs"], outputs=payload["reference_outputs"], metadata=payload["metadata"]
            )

    def evaluate(self, target, *, data, evaluators, **kwargs) -> FakeExperimentResults:
        self.evaluate_kwargs = kwargs
        rows = FakeExperimentResults()
        for ex in data:
            outputs = target(ex.inputs)
            for evaluator in evaluators:
                assert 0.0 <= evaluator(outputs=outputs, reference_outputs=ex.outputs)["score"] <= 1.0
            rows.append({"example": ex, "run": SimpleNamespace(outputs=outputs, error=None)})
        return rows


def test_langsmith_mode_also_writes_local_json(tmp_path: Path) -> None:
    client = FakeLangSmithClient()
    [result] = run_retrieval_ablation(
        oracle_factory,
        {"R4": ablation_variants()["R4"]},
        split="dev",
        mode="langsmith",
        results_dir=tmp_path,
        client=client,
    )
    assert result.mode == "langsmith"
    assert result.langsmith_experiment == "R4-retrieval-abc"
    assert result.n == N_DEV_RETRIEVAL and result.metrics["hit@5"] == 1.0
    assert client.evaluate_kwargs["metadata"]["config"]["use_bm25"] is True
    assert len(list(tmp_path.glob("*.json"))) == 1
