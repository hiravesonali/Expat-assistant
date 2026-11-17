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

    report = sub.add_parser("report", help="render evals/results/*.json to REPORT.md")
    report.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser


def _print_report(results_dir: Path) -> None:
    from expat.evals.report import write_report

    path, text = write_report(results_dir)
    print(text)
    print(f"written to {path}")


def main(argv: Sequence[str] | None = None) -> int:
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
        from expat.evals.judges import JudgeSet, default_judge_model
        from expat.evals.retrieval_eval import ablation_variants

        all_variants = ablation_variants(include_stretch=True)
        variants = _select(all_variants, args.variants) if args.variants else default_answer_variants()
        price = (args.price_in, args.price_out) if args.price_in is not None and args.price_out is not None else None
        run_answer_eval(
            default_answer_target_factory(),
            variants,
            split=args.split,
            mode=args.mode,
            judges=None if args.no_judge else JudgeSet.from_model(default_judge_model()),
            price_per_mtok=price,
            results_dir=args.results_dir,
            dataset_name=args.dataset,
            max_concurrency=args.max_concurrency,
        )
    _print_report(args.results_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
