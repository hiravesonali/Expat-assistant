"""CLI: `uv run expat-ingest [--source ID ...] [--offline]`  (same as `python -m expat.ingestion`).

Examples:
    uv run expat-ingest                     # fetch all sources politely, rebuild data/processed/
    uv run expat-ingest --source bgb bmg    # re-ingest two sources, keep the rest
    uv run expat-ingest --offline           # re-parse the saved snapshots, no network
    uv run expat-ingest --list              # show the source registry

Then build the index: `uv run expat-index`.
"""

from __future__ import annotations

import argparse
import sys

from expat.config import get_settings
from expat.ingestion.fetch import PoliteFetcher, SnapshotStore
from expat.ingestion.pipeline import make_fetch, run_ingestion
from expat.ingestion.sources import load_sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="expat-ingest", description=__doc__.splitlines()[0])
    parser.add_argument("--source", nargs="+", metavar="ID", help="only these source ids (default: all)")
    parser.add_argument("--offline", action="store_true", help="use saved snapshots in data/raw, no network")
    parser.add_argument("--list", action="store_true", help="list the sources and exit")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # German umlauts on a Windows console
    settings = get_settings()
    registry = load_sources()
    if args.list:
        for s in registry.sources:
            print(f"{s.id:32} {s.source_type.value:10} {s.fetch_method:6} {s.name}")
        return 0

    store = SnapshotStore(settings.raw_dir)
    fetcher = None if args.offline else PoliteFetcher(store)
    try:
        report = run_ingestion(registry, settings.processed_dir, make_fetch(fetcher, store, args.offline), args.source)
    finally:
        if fetcher is not None:
            fetcher.close()
    print(report.render())
    return 1 if any(s.status == "failed" for s in report.statuses) else 0


if __name__ == "__main__":
    raise SystemExit(main())
