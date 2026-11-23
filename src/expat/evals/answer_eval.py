"""Answer-level evals for the full pipeline: judges + deterministic checks, locally or as LangSmith experiments.

Per the plan these run only on R0 and the best retrieval config ("naive vs advanced RAG"), because the LLM judges
are the expensive part. The pipeline is injected as a target factory, exactly like in retrieval_eval.
"""

import json
import time
from collections.abc import Callable, Collection, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from expat.evals.dataset import DEFAULT_DATASET_NAME, DEFAULT_GOLDEN_PATH, GoldenExample, Split, by_id, load_golden
from expat.evals.judges import JudgeSet, JudgeVerdict
from expat.evals.metrics import (
    citation_correctness,
    citation_validity,
    extract_citation_ids,
    looks_like_refusal,
    must_include_score,
    must_not_include_ok,
    paragraph_citation_coverage,
    refusal_correct,
    tool_selection_correct,
)
from expat.evals.results import (
    DEFAULT_RESULTS_DIR,
    ExampleScore,
    ExperimentResult,
    aggregate,
    experiment_name,
    write_result,
)
from expat.schemas import (
    AnswerMetaEvent,
    Citation,
    CitationsEvent,
    ClarificationEvent,
    ContextSource,
    DoneEvent,
    ErrorEvent,
    PipelineEvent,
    RetrievalConfig,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserProfile,
)

Mode = Literal["local", "langsmith"]

ANSWER_METRICS = (
    "groundedness",
    "correctness",
    "citation_validity",
    "citation_coverage",
    "citation_correctness",
    "must_include",
    "must_not_include",
    "tool_selection",
    "refusal_accuracy",
    "clarification",
    "total_tokens",
    "cost_usd",
)


class AnswerOutput(BaseModel):
    """Everything the evaluators need from one pipeline run (built from the event stream by `fold_events`)."""

    answer: str = ""
    contexts: list[ContextSource] = Field(default_factory=list)  # the numbered [S#] sources given to the model
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolCallEvent] = Field(default_factory=list)
    tool_results: list[ToolResultEvent] = Field(default_factory=list)
    confidence: str | None = None
    asked_clarification: bool = False  # the pipeline asked "Which city do you live in?" instead of answering
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None

    def tool_result_ids(self) -> list[str]:
        """Tool results are cited as [T1], [T2], ... in call order (docs/rag-pipeline.md)."""
        return [f"T{i}" for i in range(1, len(self.tool_results) + 1)]

    def available_citation_ids(self) -> list[str]:
        ids = [c.source_id for c in self.contexts] + [c.id for c in self.citations] + self.tool_result_ids()
        return list(dict.fromkeys(ids))

    def context_text(self) -> str:
        """The evidence the groundedness judge sees: retrieved sources AND tool outputs (both are citable)."""
        blocks = [f"[{c.source_id}] {c.title} ({c.legal_reference or c.doc_key})\n{c.text}" for c in self.contexts]
        if not self.contexts:
            # Fallback when the pipeline doesn't expose the context pack: the citation quotes are all we have.
            blocks = [f"[{c.id}] {c.title}\n{c.quote}" for c in self.citations if c.kind == "source"]
        for tid, result in zip(self.tool_result_ids(), self.tool_results, strict=True):
            blocks.append(f"[{tid}] tool {result.name}\n{json.dumps(result.result, ensure_ascii=False, default=str)}")
        return "\n\n".join(blocks)

    def cited_doc_keys(self) -> list[str] | None:
        """doc_keys of the [S#] sources the answer cites; None if we can't map ids to doc_keys (no context pack)."""
        if not self.contexts:
            return None
        key_by_id = {c.source_id: c.doc_key for c in self.contexts}
        return [key_by_id[cid] for cid in extract_citation_ids(self.answer) if cid in key_by_id]


def fold_events(events: Iterable[PipelineEvent], contexts: list[ContextSource] | None = None) -> AnswerOutput:
    """Reduce the pipeline's event stream (what the UI renders) into one AnswerOutput.

    The context pack is taken from `contexts` if given, else from a completed retrieval StepEvent whose
    `detail["sources"]` holds ContextSource dicts (the convention we ask the pipeline to follow).
    """
    out = AnswerOutput(contexts=list(contexts or []))
    tokens: list[str] = []
    final_answer: str | None = None  # citation-validated text: what the UI actually shows (app/Home.py)
    for event in events:
        match event:
            case TokenEvent():
                tokens.append(event.text)
            case ToolCallEvent():
                out.tool_calls.append(event)
            case ToolResultEvent():
                out.tool_results.append(event)
            case CitationsEvent():
                out.citations = list(event.citations)
            case ClarificationEvent():
                out.asked_clarification = True
            case AnswerMetaEvent():
                out.confidence = event.confidence
                final_answer = event.final_answer or final_answer
            case DoneEvent():
                out.latency_ms = float(event.latency_ms) if event.latency_ms else None
                out.input_tokens = event.input_tokens
                out.output_tokens = event.output_tokens
            case ErrorEvent():
                out.error = f"{event.code}: {event.message}"
            case StepEvent(name="retrieval", status="completed") if not out.contexts:
                out.contexts = [ContextSource.model_validate(s) for s in event.detail.get("sources", [])]
            case _:
                pass
    out.answer = final_answer or "".join(tokens)
    return out


AnswerTarget = Callable[[str, UserProfile], AnswerOutput]
AnswerTargetFactory = Callable[[RetrievalConfig], AnswerTarget]


def default_answer_target_factory() -> AnswerTargetFactory:  # pragma: no cover - needs index + API keys
    """Wire the default Pipeline (a generator of PipelineEvents), built once. Imported lazily."""
    from expat.rag.pipeline import build_default_pipeline

    pipeline = build_default_pipeline()

    def factory(config: RetrievalConfig) -> AnswerTarget:
        def target(question: str, profile: UserProfile) -> AnswerOutput:
            return fold_events(pipeline.run(question, (), profile, config=config))

        return target

    return factory


def default_answer_variants() -> dict[str, RetrievalConfig]:
    """Naive RAG (R0) vs the production config (R5): the headline comparison."""
    from expat.evals.retrieval_eval import ablation_variants

    variants = ablation_variants()
    return {"R0": variants["R0"], "R5": variants["R5"]}


# --- scoring ---------------------------------------------------------------------------------------------------


def score_answer(
    example: GoldenExample,
    output: AnswerOutput,
    judges: JudgeSet | None = None,
    price_per_mtok: tuple[float, float] | None = None,
    with_groundedness: bool = True,
) -> ExampleScore:
    """All answer metrics for one example. Metrics that don't apply are None and drop out of the averages.

    with_groundedness=False skips the groundedness judge (the most expensive call: it reads the whole context);
    the metric is then None, not 0, so it drops out of the averages instead of looking like a failure.

    - Answerable questions: citations, must_include, tool selection, groundedness + correctness (if judges).
    - Refusal questions: refusal accuracy, must_not_include, and "no tool was called".
    - Refusal accuracy is measured on ALL examples, because over-refusing an easy question is also a failure.
    """
    expected_tool = example.expected_tool.model_dump() if example.expected_tool else None
    metrics: dict[str, float | None] = dict.fromkeys(ANSWER_METRICS)
    details: dict[str, Any] = {"answer": output.answer, "tool_calls": [c.name for c in output.tool_calls]}

    if output.error:
        # The user got an error instead of an answer: every applicable metric fails.
        metrics.update(must_include=0.0, tool_selection=0.0, refusal_accuracy=0.0)
        return ExampleScore(id=example.id, metrics=metrics, error=output.error, details=details)

    # Asking for the city exactly when it is needed: scored on every example (asking needlessly is a failure too).
    metrics["clarification"] = float(output.asked_clarification == example.expect_clarification)
    details["asked_clarification"] = output.asked_clarification
    if example.expect_clarification:
        return ExampleScore(id=example.id, metrics=metrics, latency_ms=output.latency_ms, details=details)

    metrics["must_not_include"] = float(must_not_include_ok(output.answer, example.must_not_include))
    metrics["tool_selection"] = float(tool_selection_correct(expected_tool, output.tool_calls))

    def judge(metric: str, fn: Callable[..., JudgeVerdict], **kwargs: Any) -> None:
        """One judge call. A failing judge leaves only ITS metric empty (None) and records why; the free,
        deterministic metrics of the example survive. Counted in `details["judge_errors"]`."""
        try:
            verdict = fn(**kwargs)
        except Exception as exc:
            details.setdefault("judge_errors", []).append(f"{metric}: {type(exc).__name__}: {str(exc)[:200]}")
            return
        metrics[metric] = float(verdict.score)
        details[f"{metric}_reasoning"] = verdict.reasoning

    if judges is not None:
        judge(
            "refusal_accuracy",
            judges.refusal,
            question=example.question,
            answer=output.answer,
            should_refuse=example.should_refuse,
        )
    else:
        metrics["refusal_accuracy"] = float(refusal_correct(example.should_refuse, looks_like_refusal(output.answer)))

    if not example.should_refuse:
        metrics["citation_validity"] = citation_validity(output.answer, output.available_citation_ids())
        metrics["citation_coverage"] = paragraph_citation_coverage(output.answer)
        cited = output.cited_doc_keys()
        metrics["citation_correctness"] = None if cited is None else citation_correctness(cited, example.all_doc_keys)
        metrics["must_include"] = must_include_score(output.answer, example.must_include)
        if judges is not None:
            context = output.context_text()
            if context and with_groundedness:
                # The answer may legitimately use the question and the user's profile ("as a Blue Card holder
                # in Munich ..."). Without them the judge flagged such sentences as invented (first dev run).
                user = (
                    f"[USER QUESTION]\n{example.question}\n\n"
                    f"[USER PROFILE]\n{example.profile.model_dump_json(exclude_none=True)}\n\n"
                )
                judge("groundedness", judges.groundedness, answer=output.answer, context=user + context)
            judge(
                "correctness",
                judges.correctness,
                question=example.question,
                answer=output.answer,
                reference=example.reference_answer,
            )

    if output.input_tokens is not None and output.output_tokens is not None:
        metrics["total_tokens"] = float(output.input_tokens + output.output_tokens)
        if price_per_mtok is not None:
            price_in, price_out = price_per_mtok
            metrics["cost_usd"] = (output.input_tokens * price_in + output.output_tokens * price_out) / 1_000_000

    return ExampleScore(id=example.id, metrics=metrics, latency_ms=output.latency_ms, details=details)


def _call_target(target: AnswerTarget, example: GoldenExample) -> AnswerOutput:
    start = time.perf_counter()
    try:
        output = target(example.question, example.profile)
    except Exception as exc:  # one failing example must not abort a whole (paid) eval run
        return AnswerOutput(error=f"{type(exc).__name__}: {exc}")
    if output.latency_ms is None:
        output.latency_ms = (time.perf_counter() - start) * 1000
    return output


def _run_langsmith(
    target: AnswerTarget,
    examples: list[GoldenExample],
    *,
    variant: str,
    config: RetrievalConfig,
    split: str,
    dataset_name: str,
    client: Any,
    max_concurrency: int,
    judges: JudgeSet | None,
    price_per_mtok: tuple[float, float] | None,
    with_groundedness: bool = True,
) -> tuple[list[ExampleScore], str | None]:
    """LangSmith experiment whose single evaluator reports all metrics; scores are also kept for the local JSON.

    Scoring happens once inside the evaluator and is memoised by example id, so the (paid) judges never run twice.
    """
    examples_by_id = by_id(examples)
    by_question = {e.question: e for e in examples}  # LangSmith inputs carry question + profile, not our id
    scored: dict[str, ExampleScore] = {}

    def ls_target(inputs: dict[str, Any]) -> dict[str, Any]:
        return _call_target(target, by_question[inputs["question"]]).model_dump(mode="json")

    def all_metrics_evaluator(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
        example = examples_by_id[reference_outputs["id"]]
        score = score_answer(
            example, AnswerOutput.model_validate(outputs), judges, price_per_mtok, with_groundedness=with_groundedness
        )
        scored[example.id] = score
        return {"results": [{"key": k, "score": v} for k, v in score.metrics.items() if v is not None]}

    data = [
        ex
        for ex in client.list_examples(dataset_name=dataset_name, splits=[split])
        if (ex.metadata or {}).get("id") in examples_by_id
    ]
    results = client.evaluate(
        ls_target,
        data=data,
        evaluators=[all_metrics_evaluator],
        experiment_prefix=f"{variant}-answers",
        metadata={"variant": variant, "split": split, "kind": "answers", "config": config.model_dump()},
        max_concurrency=max_concurrency,
    )
    list(results)  # make sure the (possibly lazy) experiment has finished before reading `scored`
    return [scored[e.id] for e in examples if e.id in scored], getattr(results, "experiment_name", None)


def run_answer_eval(
    target_factory: AnswerTargetFactory,
    variants: dict[str, RetrievalConfig] | None = None,
    split: Split | None = "dev",
    mode: Mode = "local",
    *,
    judges: JudgeSet | None = None,
    price_per_mtok: tuple[float, float] | None = None,
    golden_path: Path = DEFAULT_GOLDEN_PATH,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    dataset_name: str = DEFAULT_DATASET_NAME,
    client: Any = None,
    max_concurrency: int = 4,
    ids: list[str] | None = None,
    judge_model: str | None = None,
    groundedness_variants: Collection[str] | None = None,
) -> list[ExperimentResult]:
    """Run the full pipeline per variant and write `evals/results/answers-<variant>-<split>-<ts>.json`.

    judges=None runs only the deterministic metrics (free; refusal falls back to the keyword heuristic).
    price_per_mtok=(input_usd, output_usd) per million tokens enables the cost_usd metric.
    groundedness_variants: run the groundedness judge only for these variants (None = all). The CLI default is
    R5 only: the naive-vs-system headline uses correctness, and groundedness is ~60% of the judge cost.
    """
    variants = variants if variants is not None else default_answer_variants()
    examples = load_golden(golden_path, split=split)
    if ids:  # cheap smoke runs on a few questions before a full (paid) run
        unknown = set(ids) - {e.id for e in examples}
        if unknown:
            raise ValueError(f"unknown example id(s) for split {split!r}: {sorted(unknown)}")
        examples = [e for e in examples if e.id in ids]
    split_label = split or "all"
    if mode == "langsmith" and client is None:
        from langsmith import Client

        client = Client()

    results: list[ExperimentResult] = []
    for variant, config in variants.items():
        target = target_factory(config)
        ls_name: str | None = None
        grounded = groundedness_variants is None or variant in groundedness_variants
        if mode == "local":
            scores = [
                score_answer(e, _call_target(target, e), judges, price_per_mtok, with_groundedness=grounded)
                for e in examples
            ]
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
                judges=judges,
                price_per_mtok=price_per_mtok,
                with_groundedness=grounded,
            )
        now = datetime.now(UTC)
        metrics, per_slice = aggregate(scores, by_id(examples), ANSWER_METRICS)
        result = ExperimentResult(
            experiment=experiment_name("answers", variant, split_label, now),
            kind="answers",
            variant=variant,
            split=split_label,
            config={
                **config.model_dump(),
                "judges": judges is not None,
                "judge_model": judge_model,
                "groundedness_judged": judges is not None and grounded,
            },
            metrics=metrics,
            per_slice=per_slice,
            n=len(scores),
            errors=sum(1 for s in scores if s.error),
            created_at=now,
            mode=mode,
            dataset=golden_path.name if mode == "local" else dataset_name,
            langsmith_experiment=ls_name,
            per_example=scores,
        )
        write_result(result, results_dir)
        results.append(result)
    return results
