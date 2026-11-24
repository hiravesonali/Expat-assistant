"""CLI: `uv run python -m expat.evals upload|retrieval|answers|report [--split dev] [--mode local]`.

argparse (stdlib) instead of click/typer: no extra dependency, and four subcommands don't need more.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from expat.evals.dataset import DEFAULT_DATASET_NAME, DEFAULT_GOLDEN_PATH, Split, load_golden
from expat.evals.results import DEFAULT_RESULTS_DIR
from expat.schemas import RetrievalConfig


def _split(value: str) -> Split | None:
    if value == "all":
        return None
    if value not in ("dev", "holdout"):
        raise argparse.ArgumentTypeError("split must be dev, holdout or all")
    return value  # type: ignore[return-value]


def _select(available: dict[str, RetrievalConfig], names: str | None) -> dict[str, RetrievalConfig]:
    if not names:
        return available
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    unknown = [n for n in wanted if n not in available]
    if unknown:
        raise SystemExit(f"unknown variant(s) {unknown}; choose from {list(available)}")
    return {n: available[n] for n in wanted}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m expat.evals", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    upload = sub.add_parser("upload", help="push the golden JSONL to a LangSmith dataset")
    upload.add_argument("--name", default=DEFAULT_DATASET_NAME)
    upload.add_argument("--path", type=Path, default=DEFAULT_GOLDEN_PATH)

    for name, help_text in (("retrieval", "run the retrieval ablation"), ("answers", "run answer-level evals")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--split", type=_split, default="dev", help="dev (default), holdout or all")
        cmd.add_argument("--mode", choices=("local", "langsmith"), default="local")
        cmd.add_argument("--variants", help="comma-separated subset, e.g. R0,R4,R5")
        cmd.add_argument("--dataset", default=DEFAULT_DATASET_NAME, help="LangSmith dataset (langsmith mode)")
        cmd.add_argument("--max-concurrency", type=int, default=4)
        cmd.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    sub.choices["retrieval"].add_argument("--stretch", action="store_true", help="also run R6 (rerank) and R7 (HyDE)")
    answers = sub.choices["answers"]
    answers.add_argument("--no-judge", action="store_true", help="deterministic metrics only (free)")
    answers.add_argument("--price-in", type=float, help="USD per 1M input tokens (enables cost_usd)")
    answers.add_argument("--price-out", type=float, help="USD per 1M output tokens")
    answers.add_argument("--ids", help="comma-separated golden ids, for a cheap smoke run")
    answers.add_argument(
        "--groundedness-all",
        action="store_true",
        help="run the groundedness judge for every variant (default: R5 only; it is the most expensive judge)",
    )
    answers.add_argument("--no-cache", action="store_true", help="ignore cached judge verdicts")
    answers.add_argument("--dry-run", action="store_true", help="print the cost estimate and exit (free)")
    answers.add_argument("--force", action="store_true", help="run even if the estimate exceeds the key's credit")
    answers.add_argument(
        "--samples",
        action="store_true",
        help="also write evals/results/samples/<experiment>.jsonl (answers + contexts) for scripts/ragas_eval.py",
    )

    report = sub.add_parser("report", help="render evals/results/*.json to REPORT.md")
    report.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser


def _print_report(results_dir: Path) -> None:
    from expat.evals.report import write_report

    path, text = write_report(results_dir)
    # The report has "Δ" and "§"; a Windows console (cp1252) can't print them and would crash after the run.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    print(text)
    print(f"written to {path}")


def main(argv: Sequence[str] | None = None) -> int:
    # Output has "≈", "Δ" and "§"; a Windows console (cp1252) can't print them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)

    if args.command == "upload":
        from expat.evals.dataset import upload_dataset

        dataset_id = upload_dataset(args.name, args.path)
        print(f"uploaded {args.path.name} to LangSmith dataset {args.name!r} (id {dataset_id})")
        return 0

    if args.command == "report":
        _print_report(args.results_dir)
        return 0

    if args.command == "retrieval":
        from expat.evals.retrieval_eval import ablation_variants, default_target_factory, run_retrieval_ablation

        variants = _select(ablation_variants(include_stretch=args.stretch), args.variants)
        factory, analysis_cache = default_target_factory()
        # Run query analysis for every question up front, so per-variant latency measures retrieval only.
        analysis_cache.warm(e for e in load_golden(split=args.split) if not e.should_refuse)
        run_retrieval_ablation(
            factory,
            variants,
            split=args.split,
            mode=args.mode,
            results_dir=args.results_dir,
            dataset_name=args.dataset,
            max_concurrency=args.max_concurrency,
        )
    elif args.command == "answers":
        from expat.evals.answer_eval import default_answer_target_factory, default_answer_variants, run_answer_eval
        from expat.evals.judges import JudgeCache, JudgeSet, default_judge_model
        from expat.evals.retrieval_eval import ablation_variants

        all_variants = ablation_variants(include_stretch=True)
        variants = _select(all_variants, args.variants) if args.variants else default_answer_variants()
        from expat.config import get_settings

        settings = get_settings()
        price = (args.price_in, args.price_out) if args.price_in is not None and args.price_out is not None else None
        ids = [i.strip() for i in args.ids.split(",")] if args.ids else None
        grounded_variants = None if args.groundedness_all else {"R5"}

        # Spend guard (free calls): estimate from live prices, compare with the key's remaining credit.
        from expat.evals.budget import check_budget, estimate_answer_eval, key_remaining_usd, model_price

        examples = [e for e in load_golden(split=args.split) if not ids or e.id in ids]
        answer_price = price or (settings.price_in_per_mtok, settings.price_out_per_mtok)
        judge_price = None if args.no_judge else (model_price(settings.model_judge) or answer_price)
        estimate = estimate_answer_eval(
            examples, variants, answer_price=answer_price, judge_price=judge_price,
            groundedness_variants=grounded_variants,
        )  # fmt: skip
        key = settings.openrouter_api_key
        secret = key.get_secret_value() if key is not None and hasattr(key, "get_secret_value") else key
        remaining = key_remaining_usd(str(secret)) if secret else None
        print(
            f"Estimate: {estimate.pipeline_runs} answers + {estimate.judge_calls} judge calls "
            f"({'no judge' if args.no_judge else settings.model_judge}) ≈ ${estimate.total_usd:.2f} "
            f"(answers ${estimate.answers_usd:.2f}, judges ${estimate.judges_usd:.2f}); "
            f"key credit left: {'no limit' if remaining is None else f'${remaining:.2f}'}"
        )
        if args.dry_run:
            return 0
        problem = check_budget(estimate, remaining)
        if problem and not args.force:
            print(f"Stopped before spending anything: {problem}", file=sys.stderr)
            return 3

        judges, judge_model = None, None
        cache: JudgeCache | None = None
        if not args.no_judge:
            model = default_judge_model()
            judge_model = settings.model_judge
            try:  # pre-flight: a blocked/unknown judge must fail in seconds, not after N paid pipeline runs
                model.invoke("Reply with OK.")
            except Exception as exc:
                print(f"Judge model {judge_model!r} is not usable: {exc}", file=sys.stderr)
                print("Set MODEL_JUDGE to an allowed model, or run with --no-judge.", file=sys.stderr)
                return 2
            cache = None if args.no_cache else JudgeCache()
            judges = JudgeSet.from_model(model, cache=cache, model_name=judge_model)
        run_answer_eval(
            default_answer_target_factory(),
            variants,
            split=args.split,
            mode=args.mode,
            judges=judges,
            judge_model=judge_model,
            price_per_mtok=price,
            results_dir=args.results_dir,
            dataset_name=args.dataset,
            max_concurrency=args.max_concurrency,
            ids=ids,
            groundedness_variants=grounded_variants,
            write_sample_files=args.samples,
        )
        if cache is not None:
            print(f"Judge cache: {cache.hits} hits (free), {cache.misses} new verdicts")
    _print_report(args.results_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
