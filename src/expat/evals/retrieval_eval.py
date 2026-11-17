"""Retrieval ablation runner: R0..R5 (+ R6/R7) from docs/evaluation-plan.md §3, locally or as LangSmith experiments.

Dependency injection: the runner never imports the retriever. It receives a `target_factory` that turns a
RetrievalConfig into a target `(question, profile) -> RetrievalResult | list[doc_key]`. That keeps this module
testable with a fake target and independent of the RAG code being written in parallel.
"""

import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from expat.evals.dataset import DEFAULT_DATASET_NAME, DEFAULT_GOLDEN_PATH, GoldenExample, Split, by_id, load_golden
from expat.evals.metrics import hit_at_k, mrr_at_k, recall_at_k
from expat.evals.results import (
    DEFAULT_RESULTS_DIR,
    ExampleScore,
    ExperimentResult,
    aggregate,
    experiment_name,
    write_result,
)
from expat.schemas import RetrievalConfig, RetrievalPlan, RetrievalResult, Retriever, UserProfile

Mode = Literal["local", "langsmith"]
RetrievalOutput = RetrievalResult | Sequence[str]
RetrievalTarget = Callable[[str, UserProfile], RetrievalOutput]
TargetFactory = Callable[[RetrievalConfig], RetrievalTarget]
Analyzer = Callable[[str, UserProfile], RetrievalPlan]

HIT_K = 5
RECALL_K = 10
MRR_K = 10
RETRIEVAL_METRICS = ("hit@5", "recall@10", "mrr@10")


# --- the ablation matrix ---------------------------------------------------------------------------------------


def ablation_variants(include_stretch: bool = False) -> dict[str, RetrievalConfig]:
    """The cumulative ablation rows. Each row switches on exactly one more technique than the previous one.

    Step-back is not a separate row in the plan; it is switched on together with multi-query in R2 because both
    only add query variants that are fused with RRF (RAG-Fusion). R5 therefore equals the production default
    `RetrievalConfig()`, which a test asserts, so "R5" in the report is literally what users get.
    """
    r0 = RetrievalConfig.baseline()
    r1 = r0.model_copy(update={"use_german_rewrite": True})
    r2 = r1.model_copy(update={"use_multi_query": True, "use_step_back": True})
    r3 = r2.model_copy(update={"use_decomposition": True})
    r4 = r3.model_copy(update={"use_bm25": True})
    r5 = r4.model_copy(update={"use_filters": True})
    variants = {"R0": r0, "R1": r1, "R2": r2, "R3": r3, "R4": r4, "R5": r5}
    if include_stretch:
        variants["R6"] = r5.model_copy(update={"use_rerank": True})
        variants["R7"] = r5.model_copy(update={"use_hyde": True})
    return variants


VARIANT_DESCRIPTIONS: dict[str, str] = {
    "R0": "Vector only, raw query, no filters (baseline)",
    "R1": "R0 + German rewrite (EN+DE, RRF)",
    "R2": "R1 + multi-query + step-back (RAG-Fusion)",
    "R3": "R2 + decomposition (multi-domain)",
    "R4": "R3 + BM25 hybrid",
    "R5": "R4 + profile/metadata filters",
    "R6": "R5 + reranker",
    "R7": "R5 + HyDE",
}


# --- wiring the real retriever (used by the CLI) ---------------------------------------------------------------


class AnalysisCache:
    """Runs query analysis ONCE per (question, profile) and reuses the plan for every variant.

    Why: query analysis is an LLM call and not perfectly deterministic. If R1 and R4 got different plans, we
    couldn't tell whether BM25 or a lucky rewrite caused the difference. Caching makes the retrieval flags the only
    thing that changes between rows. Call `warm()` before the ablation so latency numbers measure retrieval only.
    """

    def __init__(self, analyze: Analyzer) -> None:
        self._analyze = analyze
        self._plans: dict[tuple[str, str], RetrievalPlan] = {}

    def get(self, question: str, profile: UserProfile) -> RetrievalPlan:
        key = (question, profile.model_dump_json())
        if key not in self._plans:
            plan = self._analyze(question, profile)
            if not isinstance(plan, RetrievalPlan):
                raise TypeError(f"analyze() must return RetrievalPlan, got {type(plan).__name__}")
            self._plans[key] = plan
        return self._plans[key]

    def warm(self, examples: Iterable[GoldenExample]) -> None:
        for example in examples:
            self.get(example.question, example.profile)


def needs_query_analysis(config: RetrievalConfig) -> bool:
    """R0 uses the raw question only, so it must not pay for (or be influenced by) the analysis LLM call."""
    return any(
        (
            config.use_german_rewrite,
            config.use_multi_query,
            config.use_decomposition,
            config.use_step_back,
            config.use_hyde,
        )
    )


def make_target_factory(retriever: Retriever, analysis: AnalysisCache) -> TargetFactory:
    """Build the production target: (cached) query analysis -> `Retriever.retrieve(plan, profile, config)`."""

    def factory(config: RetrievalConfig) -> RetrievalTarget:
        def target(question: str, profile: UserProfile) -> RetrievalResult:
            plan = analysis.get(question, profile) if needs_query_analysis(config) else RetrievalPlan.from_raw(question)
            return retriever.retrieve(plan, profile, config)

        return target

    return factory


def default_target_factory() -> tuple[TargetFactory, AnalysisCache]:  # pragma: no cover - needs the real index
    """Wire the SAME Pipeline the chat uses (its retriever + analyze step). Imported lazily: needs an index + keys."""
    from expat.rag.pipeline import build_default_pipeline

    pipeline = build_default_pipeline()
    cache = AnalysisCache(lambda question, profile: pipeline.analyze(question, (), profile))
    return make_target_factory(pipeline.retriever, cache), cache


# --- scoring ---------------------------------------------------------------------------------------------------


def doc_keys_of(output: RetrievalOutput) -> list[str]:
    """Accept either a RetrievalResult or a plain ranked list of doc_keys (handy for fakes and baselines)."""
    if isinstance(output, RetrievalResult):
        return output.all_doc_keys()
    return list(output)


def score_retrieval(example: GoldenExample, doc_keys: Sequence[str]) -> dict[str, float | None]:
    expected = example.required_doc_keys
    return {
        "hit@5": hit_at_k(doc_keys, expected, HIT_K),
        "recall@10": recall_at_k(doc_keys, expected, RECALL_K),
        "mrr@10": mrr_at_k(doc_keys, expected, MRR_K),
    }


def retrieval_examples(examples: Iterable[GoldenExample]) -> list[GoldenExample]:
    """Refusal examples have no expected sources (and the pipeline skips retrieval for them), so they are excluded."""
    return [e for e in examples if not e.should_refuse]


def _run_one(target: RetrievalTarget, example: GoldenExample) -> ExampleScore:
    start = time.perf_counter()
    try:
        keys = doc_keys_of(target(example.question, example.profile))
    except Exception as exc:  # one failing example must not abort a whole (paid) eval run
        # A crash is a retrieval failure from the user's point of view, so it scores 0 (and is counted in `errors`).
        return ExampleScore(
            id=example.id,
            metrics={m: 0.0 for m in RETRIEVAL_METRICS},
            error=f"{type(exc).__name__}: {exc}",
        )
    latency_ms = (time.perf_counter() - start) * 1000
    return ExampleScore(
        id=example.id,
        metrics=score_retrieval(example, keys),
        latency_ms=latency_ms,
        details={"doc_keys": keys[:RECALL_K]},
    )


def _build_result(
    scores: list[ExampleScore],
    examples: list[GoldenExample],
    *,
    variant: str,
    config: RetrievalConfig,
    split: str,
    mode: Mode,
    dataset: str,
    langsmith_experiment: str | None = None,
) -> ExperimentResult:
    now = datetime.now(UTC)
    metrics, per_slice = aggregate(scores, by_id(examples), RETRIEVAL_METRICS)
    return ExperimentResult(
        experiment=experiment_name("retrieval", variant, split, now),
        kind="retrieval",
        variant=variant,
        split=split,
        config=config.model_dump(),
        metrics=metrics,
        per_slice=per_slice,
        n=len(scores),
        errors=sum(1 for s in scores if s.error),
        created_at=now,
        mode=mode,
        dataset=dataset,
        langsmith_experiment=langsmith_experiment,
        per_example=scores,
    )


# --- LangSmith evaluators (same metrics, LangSmith's function signature) ---------------------------------------


def _required_keys(reference_outputs: dict[str, Any]) -> list[str]:
    return [s["doc_key"] for s in reference_outputs.get("expected_sources", []) if s.get("required", True)]


def hit_at_5_evaluator(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "hit@5", "score": hit_at_k(outputs["doc_keys"], _required_keys(reference_outputs), HIT_K)}


def recall_at_10_evaluator(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "recall@10", "score": recall_at_k(outputs["doc_keys"], _required_keys(reference_outputs), RECALL_K)}


def mrr_at_10_evaluator(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "mrr@10", "score": mrr_at_k(outputs["doc_keys"], _required_keys(reference_outputs), MRR_K)}


RETRIEVAL_EVALUATORS = [hit_at_5_evaluator, recall_at_10_evaluator, mrr_at_10_evaluator]


def _run_langsmith(
    target: RetrievalTarget,
    examples: list[GoldenExample],
    *,
    variant: str,
    config: RetrievalConfig,
    split: str,
    dataset_name: str,
    client: Any,
    max_concurrency: int,
) -> tuple[list[ExampleScore], str | None]:
    """Run as a LangSmith experiment, then rebuild the per-example scores locally from the run outputs.

    Recomputing locally (instead of reading LangSmith feedback back) keeps one aggregation code path for both modes.
    """
    wanted = {e.id for e in examples}

    def ls_target(inputs: dict[str, Any]) -> dict[str, Any]:
        profile = UserProfile.model_validate(inputs["profile"])
        start = time.perf_counter()
        keys = doc_keys_of(target(inputs["question"], profile))
        return {"doc_keys": keys, "latency_ms": (time.perf_counter() - start) * 1000}

    data = [
        ex
        for ex in client.list_examples(dataset_name=dataset_name, splits=[split])
        if (ex.metadata or {}).get("id") in wanted
    ]
    results = client.evaluate(
        ls_target,
        data=data,
        evaluators=RETRIEVAL_EVALUATORS,
        experiment_prefix=f"{variant}-retrieval",
        description=VARIANT_DESCRIPTIONS.get(variant, variant),
        metadata={"variant": variant, "split": split, "kind": "retrieval", "config": config.model_dump()},
        max_concurrency=max_concurrency,
    )
    examples_by_id = by_id(examples)
    scores: list[ExampleScore] = []
    for row in results:
        example = examples_by_id[row["example"].metadata["id"]]
        run = row["run"]
        if run.error or not run.outputs:
            scores.append(
                ExampleScore(id=example.id, metrics={m: 0.0 for m in RETRIEVAL_METRICS}, error=str(run.error))
            )
            continue
        keys = list(run.outputs["doc_keys"])
        scores.append(
            ExampleScore(
                id=example.id,
                metrics=score_retrieval(example, keys),
                latency_ms=run.outputs.get("latency_ms"),
                details={"doc_keys": keys[:RECALL_K]},
            )
        )
    return scores, getattr(results, "experiment_name", None)


# --- public entry point ----------------------------------------------------------------------------------------


def run_retrieval_ablation(
    target_factory: TargetFactory,
    variants: dict[str, RetrievalConfig] | None = None,
    split: Split | None = "dev",
    mode: Mode = "local",
    *,
    golden_path: Path = DEFAULT_GOLDEN_PATH,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    dataset_name: str = DEFAULT_DATASET_NAME,
    client: Any = None,
    max_concurrency: int = 4,
) -> list[ExperimentResult]:
    """Run every variant on the chosen split and write one `evals/results/<experiment>.json` per variant.

    split=None runs dev + holdout together (only do that for the final report; tune on dev).
    In langsmith mode the dataset must have been uploaded first (`python -m expat.evals upload`).
    """
    variants = variants if variants is not None else ablation_variants()
    examples = retrieval_examples(load_golden(golden_path, split=split))
    split_label = split or "all"
    if mode == "langsmith" and client is None:
        from langsmith import Client

        client = Client()

    results: list[ExperimentResult] = []
    for variant, config in variants.items():
        target = target_factory(config)
        ls_name: str | None = None
        if mode == "local":
            scores = [_run_one(target, example) for example in examples]
        else:
            if split is None:
                raise ValueError("langsmith mode needs an explicit split")
            scores, ls_name = _run_langsmith(
                target,
                examples,
                variant=variant,
                config=config,
                split=split,
                dataset_name=dataset_name,
                client=client,
                max_concurrency=max_concurrency,
            )
        result = _build_result(
            scores,
            examples,
            variant=variant,
            config=config,
            split=split_label,
            mode=mode,
            dataset=golden_path.name if mode == "local" else dataset_name,
            langsmith_experiment=ls_name,
        )
        write_result(result, results_dir)
        results.append(result)
    return results
