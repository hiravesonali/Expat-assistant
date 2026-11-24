# /// script
# requires-python = ">=3.12"
# dependencies = ["ragas==0.4.4", "openai>=2,<4", "httpx>=0.27", "python-dotenv>=1.0"]
# ///
"""Second opinion on our answer evals with Ragas: faithfulness, context precision, context recall.

    # 1. Project env: run the pipeline + our judges once and keep answers WITH their contexts (~$0.10 for R5 holdout)
    uv run python -m expat.evals answers --split holdout --variants R5 --samples
    # 2. Isolated env: score the same answers with Ragas (prints a cost estimate first; --dry-run stops there)
    uv run --script scripts/ragas_eval.py --dry-run
    uv run --script scripts/ragas_eval.py --limit 3        # smoke run
    uv run --script scripts/ragas_eval.py                  # newest samples file, all scorable answers

Why a separate script with its own environment: Ragas pulls `instructor`, which pins `jiter<0.15`; that forces an
older `openai` than the app uses. Inside the project it would downgrade the deployed app's dependencies.

Why score the samples file and not re-run the pipeline: answers vary between runs. Ragas and our judges must
see the SAME answer, or "do they agree?" means nothing.

Ragas metrics used (LLM = MODEL_JUDGE, the cheap judge):
- faithfulness: share of the answer's statements supported by the evidence (the question, the user's profile,
  retrieved sources and tool results, i.e. what our groundedness judge sees). Compared with our binary verdict.
- context_precision (with reference): are the relevant sources ranked high? One LLM call PER source.
- context_recall: how much of the reference answer is covered by the retrieved sources (sources only, no tools).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO / "evals" / "results" / "samples"
OUT_DIR = REPO / "evals" / "results" / "ragas"
CACHE_ROOT = REPO / "evals" / ".ragas_cache"
OPENROUTER = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
METRICS = ("faithfulness", "context_precision", "context_recall")
SAFETY_FACTOR = 1.25  # same headroom as expat.evals.budget
CHARS_PER_TOKEN = 3.5  # German legal text packs fewer characters per token than English (~4)
FAITHFUL_AT = 0.8  # faithfulness >= this counts as "grounded" when comparing with our binary judge


# --- pure helpers (no Ragas import; unit-tested from the project env) ---------------------------------------------


def tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def load_samples(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def newest_samples(directory: Path = SAMPLES_DIR) -> Path:
    files = sorted(directory.glob("*.jsonl"))  # names end in a sortable UTC timestamp
    if not files:
        raise SystemExit(
            f"no samples in {directory}. First run: "
            "uv run python -m expat.evals answers --split holdout --variants R5 --samples"
        )
    return files[-1]


def skip_reason(record: dict[str, Any]) -> str | None:
    """Why Ragas can't score this answer (None = scorable). Refusals and city questions have no RAG answer."""
    if record.get("error"):
        return "pipeline error"
    if record.get("should_refuse"):
        return "refusal question"
    if record.get("expect_clarification") or record.get("asked_clarification"):
        return "clarification"
    if not record.get("answer", "").strip():
        return "empty answer"
    if not record.get("retrieved_contexts"):
        return "no retrieved sources"
    return None


def user_block(record: dict[str, Any]) -> str:
    """The answer may restate the question ("with an income of 190,000 euros ...") and use the profile ("as a Blue
    Card holder ..."). Our groundedness judge sees both; without them Ragas rejected such statements (fam-006)."""
    profile = json.dumps(record.get("profile", {}), ensure_ascii=False)
    return f"[USER QUESTION]\n{record['question']}\n\n[USER PROFILE]\n{profile}"


def faithfulness_evidence(record: dict[str, Any]) -> list[str]:
    return [user_block(record), *record["retrieved_contexts"], *record.get("tool_contexts", [])]


@dataclass
class Estimate:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def usd(self, price: tuple[float, float]) -> float:
        return (self.input_tokens * price[0] + self.output_tokens * price[1]) / 1_000_000


def estimate(records: list[dict[str, Any]], overhead: dict[str, int], metrics: tuple[str, ...] = METRICS) -> Estimate:
    """Token estimate from the real sample texts. overhead = fixed tokens of each Ragas prompt (instructions +
    few-shot examples): keys statements, nli, precision, recall. Outputs are rough: statements ~ answer length."""
    est = Estimate()
    for r in records:
        q, a, ref = tokens(r["question"]), tokens(r["answer"]), tokens(r["reference"])
        sources = [tokens(c) for c in r["retrieved_contexts"]]
        if "faithfulness" in metrics:
            evidence = sum(tokens(c) for c in faithfulness_evidence(r))
            est.calls += 2  # 1) split the answer into statements, 2) check all statements against the evidence
            est.input_tokens += overhead["statements"] + q + a + overhead["nli"] + a + evidence
            est.output_tokens += a + a  # the statements, then one verdict + reason per statement
        if "context_precision" in metrics:
            est.calls += len(sources)  # one call per retrieved source
            est.input_tokens += len(sources) * (overhead["precision"] + q + ref) + sum(sources)
            est.output_tokens += 80 * len(sources)
        if "context_recall" in metrics:
            est.calls += 1
            est.input_tokens += overhead["recall"] + q + ref + sum(sources)
            est.output_tokens += ref + 100
    return est


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    return statistics.fmean(vals) if vals else None


def compare(rows: list[dict[str, Any]], faithful_at: float = FAITHFUL_AT) -> dict[str, Any]:
    """Where Ragas and our judges agree. rows: {id, faithfulness, context_recall, ..., ours_groundedness,
    ours_correctness}. Only rows where both sides have a value count."""
    pairs = [
        (r["id"], r["faithfulness"], r["ours_groundedness"])
        for r in rows
        if r.get("faithfulness") is not None and r.get("ours_groundedness") is not None
    ]
    agree = [i for i, f, g in pairs if (f >= faithful_at) == (g >= 0.5)]
    disagree = [
        {"id": i, "faithfulness": round(f, 2), "ours_groundedness": g} for i, f, g in pairs if i not in set(agree)
    ]

    def by_verdict(metric: str, ours: str, value: float) -> float | None:
        return _mean([r.get(metric) for r in rows if r.get(ours) == value])

    return {
        "faithful_threshold": faithful_at,
        "groundedness_pairs": len(pairs),
        "groundedness_agreement": len(agree) / len(pairs) if pairs else None,
        "groundedness_disagreements": disagree,
        "faithfulness_when_ours_grounded": by_verdict("faithfulness", "ours_groundedness", 1.0),
        "faithfulness_when_ours_not_grounded": by_verdict("faithfulness", "ours_groundedness", 0.0),
        "context_recall_when_ours_correct": by_verdict("context_recall", "ours_correctness", 1.0),
        "context_recall_when_ours_incorrect": by_verdict("context_recall", "ours_correctness", 0.0),
    }


def render_markdown(result: dict[str, Any]) -> str:
    def f(v: float | None) -> str:
        return "–" if v is None else f"{v:.2f}"

    cfg, means, cmp = result["config"], result["means"], result["comparison"]
    lines = [
        f"# Ragas: {cfg['samples']}",
        "",
        f"Model `{cfg['model']}`, Ragas {cfg['ragas_version']}, {result['n_scored']} answers scored "
        f"({result['n_skipped']} skipped: refusals, city questions, errors). Cost ${result['usage']['cost_usd']:.4f} "
        f"({result['usage']['calls']} paid requests; cached verdicts are free).",
        "",
        "| Metric | Mean |",
        "|---|---|",
        *[f"| {m} | {f(means.get(m))} |" for m in cfg["metrics"]],
        "",
        "## Ragas vs our judges",
        "",
        f"- Groundedness agreement (faithfulness ≥ {cmp['faithful_threshold']} = grounded): "
        f"{f(cmp['groundedness_agreement'])} on {cmp['groundedness_pairs']} answers",
        f"- Mean faithfulness where our judge said grounded / not grounded: "
        f"{f(cmp['faithfulness_when_ours_grounded'])} / {f(cmp['faithfulness_when_ours_not_grounded'])}",
        f"- Mean context recall where our judge said correct / incorrect: "
        f"{f(cmp['context_recall_when_ours_correct'])} / {f(cmp['context_recall_when_ours_incorrect'])}",
        "",
        "| id | faithfulness | ctx precision | ctx recall | ours: grounded | ours: correct |",
        "|---|---|---|---|---|---|",
    ]
    for r in result["per_example"]:
        lines.append(
            f"| {r['id']} | {f(r.get('faithfulness'))} | {f(r.get('context_precision'))} | "
            f"{f(r.get('context_recall'))} | {f(r.get('ours_groundedness'))} | {f(r.get('ours_correctness'))} |"
        )
    if cmp["groundedness_disagreements"]:
        lines += ["", "Disagreements (check by hand): " + ", ".join(d["id"] for d in cmp["groundedness_disagreements"])]
    return "\n".join(lines) + "\n"


def cache_dir_for(model: str) -> Path:
    """Ragas' cache key is (prompt, output schema) WITHOUT the model, so each model needs its own folder."""
    return CACHE_ROOT / re.sub(r"[^A-Za-z0-9._-]+", "_", model)


# --- OpenRouter: prices, key credit, measured usage ----------------------------------------------------------------


def model_price(model: str) -> tuple[float, float] | None:
    import httpx

    for row in httpx.get(f"{OPENROUTER}/models", timeout=30).json().get("data", []):
        if row.get("id") == model:
            p = row.get("pricing", {})
            return float(p.get("prompt", 0)) * 1e6, float(p.get("completion", 0)) * 1e6
    return None


def key_remaining_usd(api_key: str) -> float | None:
    import httpx

    try:
        data = httpx.get(f"{OPENROUTER}/key", headers={"Authorization": f"Bearer {api_key}"}, timeout=30).json()
    except (httpx.HTTPError, ValueError):
        return None
    remaining = data.get("data", {}).get("limit_remaining")
    return None if remaining is None else float(remaining)


@dataclass
class Usage:
    """Measured from every OpenRouter response (including instructor's retries); cache hits make no request."""

    price: tuple[float, float]
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)

    async def on_response(self, response: Any) -> None:
        await response.aread()
        try:
            usage = response.json().get("usage") or {}
        except ValueError:
            return
        self.calls += 1
        pin, pout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        self.input_tokens += pin
        self.output_tokens += pout
        cost = usage.get("cost")  # OpenRouter reports the billed amount; fall back to list prices
        self.cost_usd += float(cost) if cost is not None else (pin * self.price[0] + pout * self.price[1]) / 1e6


# --- Ragas scoring -------------------------------------------------------------------------------------------------


def prompt_overheads(llm: Any) -> dict[str, int]:
    """Fixed token size of each Ragas prompt, measured by rendering it with empty inputs (no API call)."""
    from ragas.metrics.collections import ContextPrecisionWithReference, ContextRecall, Faithfulness

    def size(prompt: Any) -> int:
        model = prompt.input_model
        empty = model(**{k: ([] if "statement" in k else "") for k in model.model_fields})
        return math.ceil(len(prompt.to_string(empty)) / 4)  # the prompts are English

    faith = Faithfulness(llm=llm)
    return {
        "statements": size(faith.statement_generator_prompt),
        "nli": size(faith.nli_statement_prompt),
        "precision": size(ContextPrecisionWithReference(llm=llm).prompt),
        "recall": size(ContextRecall(llm=llm).prompt),
    }


async def score_all(
    records: list[dict[str, Any]], llm: Any, metrics: tuple[str, ...], concurrency: int
) -> list[dict[str, Any]]:
    from ragas.metrics.collections import ContextPrecisionWithReference, ContextRecall, Faithfulness

    def faith_args(r: dict[str, Any]) -> dict[str, Any]:
        return {"user_input": r["question"], "response": r["answer"], "retrieved_contexts": faithfulness_evidence(r)}

    def context_args(r: dict[str, Any]) -> dict[str, Any]:  # sources only: tools are not retrieval
        return {"user_input": r["question"], "reference": r["reference"], "retrieved_contexts": r["retrieved_contexts"]}

    scorers = {
        "faithfulness": (Faithfulness(llm=llm), faith_args),
        "context_precision": (ContextPrecisionWithReference(llm=llm), context_args),
        "context_recall": (ContextRecall(llm=llm), context_args),
    }
    gate = asyncio.Semaphore(concurrency)

    async def one(r: dict[str, Any]) -> dict[str, Any]:
        row: dict[str, Any] = {
            "id": r["id"],
            "ours_groundedness": r.get("ours", {}).get("groundedness"),
            "ours_correctness": r.get("ours", {}).get("correctness"),
            "n_sources": len(r["retrieved_contexts"]),
        }
        async with gate:
            for name in metrics:
                metric, kwargs = scorers[name]
                try:  # one failing metric must not lose the others (or the paid calls already made)
                    value = float((await metric.ascore(**kwargs(r))).value)
                    row[name] = None if math.isnan(value) else value
                except Exception as exc:
                    row[name] = None
                    row.setdefault("errors", []).append(f"{name}: {type(exc).__name__}: {str(exc)[:200]}")
        print(f"  {r['id']}: " + ", ".join(f"{m} {row[m]:.2f}" if row[m] is not None else f"{m} –" for m in metrics))
        return row

    return list(await asyncio.gather(*(one(r) for r in records)))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "samples", nargs="?", type=Path, help="samples .jsonl (default: newest in evals/results/samples)"
    )
    parser.add_argument("--ids", help="comma-separated golden ids")
    parser.add_argument("--limit", type=int, help="score only the first N scorable answers (smoke run)")
    parser.add_argument("--metrics", default=",".join(METRICS), help=f"subset of {','.join(METRICS)}")
    parser.add_argument("--model", help="judge model (default: MODEL_JUDGE from .env)")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="print the estimate and exit (free)")
    parser.add_argument("--force", action="store_true", help="run even if the estimate exceeds the key's credit")
    parser.add_argument("--no-cache", action="store_true", help="ignore cached Ragas verdicts")
    args = parser.parse_args(argv)

    # Ragas sends usage analytics by default; this project sends nothing it doesn't need to.
    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    metrics = tuple(m.strip() for m in args.metrics.split(",") if m.strip())
    if unknown := [m for m in metrics if m not in METRICS]:
        raise SystemExit(f"unknown metric(s) {unknown}; choose from {METRICS}")
    model = args.model or os.environ.get("MODEL_JUDGE") or DEFAULT_MODEL
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set (.env)")

    path = args.samples or newest_samples()
    records = load_samples(path)
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        records = [r for r in records if r["id"] in wanted]
    skipped = {r["id"]: reason for r in records if (reason := skip_reason(r))}
    scorable = [r for r in records if r["id"] not in skipped]
    if args.limit:
        scorable = scorable[: args.limit]
    if not scorable:
        raise SystemExit(f"nothing to score in {path.name} (skipped: {skipped})")

    import httpx
    import ragas
    from openai import AsyncOpenAI
    from ragas.cache import DiskCacheBackend
    from ragas.llms import llm_factory

    price = model_price(model)
    if price is None:
        raise SystemExit(f"model {model!r} not found on OpenRouter")
    usage = Usage(price=price)
    client = AsyncOpenAI(
        base_url=OPENROUTER,
        api_key=api_key,
        http_client=httpx.AsyncClient(timeout=120, event_hooks={"response": [usage.on_response]}),
    )
    cache = None if args.no_cache else DiskCacheBackend(cache_dir=str(cache_dir_for(model)))
    # Ragas' default max_tokens=1024 cut off the statement list of a long answer (IncompleteOutputException on
    # bur-010, 2026-11-24). Output is billed per token used, so a higher cap only costs when it is needed.
    llm = llm_factory(model, provider="openai", client=client, cache=cache, max_tokens=4096)

    est = estimate(scorable, prompt_overheads(llm), metrics)
    remaining = key_remaining_usd(api_key)
    print(
        f"{path.name}: {len(scorable)} answers to score ({len(skipped)} skipped), metrics {', '.join(metrics)}\n"
        f"Estimate: {est.calls} calls, ~{est.input_tokens:,} in / {est.output_tokens:,} out tokens with {model} "
        f"≈ ${est.usd(price):.3f} (before cache hits); key credit left: "
        f"{'no limit' if remaining is None else f'${remaining:.2f}'}"
    )
    if args.dry_run:
        return 0
    needed = est.usd(price) * SAFETY_FACTOR
    if remaining is not None and needed > remaining and not args.force:
        print(
            f"Stopped before spending anything: needs ~${needed:.2f} with headroom, ${remaining:.2f} left.",
            file=sys.stderr,
        )
        return 3

    start = time.perf_counter()
    rows = asyncio.run(score_all(scorable, llm, metrics, args.concurrency))
    run_seconds = time.perf_counter() - start
    result = {
        "config": {
            "samples": path.name,
            "model": model,
            "ragas_version": ragas.__version__,
            "metrics": list(metrics),
            "faithfulness_evidence": "question + profile + retrieved sources + tool results",
            "context_evidence": "retrieved sources only",
        },
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_scored": len(rows),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "means": {m: _mean([r.get(m) for r in rows]) for m in metrics},
        "comparison": compare(rows),
        "usage": {
            "calls": usage.calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": round(usage.cost_usd, 5),
            "estimate_usd": round(est.usd(price), 5),
            "seconds": round(run_seconds, 1),
        },
        "per_example": rows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"ragas-{path.stem.removeprefix('answers-')}"
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown = render_markdown(result)
    (OUT_DIR / f"{stem}.md").write_text(markdown, encoding="utf-8")
    print("\n" + markdown + f"written to {OUT_DIR / stem}.json / .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
