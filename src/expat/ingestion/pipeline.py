"""Ingestion orchestrator: sources.yaml -> fetch -> parse -> chunk -> enrich -> data/processed/.

Outputs (the indexer `python -m expat.store` reads the first two):
    chunks.jsonl      one ChunkRecord per line
    parents.jsonl     one ParentRecord per line
    manifest.json     {"generated_at": ..., "sources": [{source_id, status, chunks, parents, ...}]}
    quarantine.jsonl  chunks that failed validation (empty file = all good)

A partial run (`--source bgb`) replaces only that source's records and keeps the others, so one
broken site never forces a full re-crawl. One failing source is recorded as `failed` in the
manifest and does not stop the run.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from expat.ingestion.chunkers.base import ChunkedDocument
from expat.ingestion.chunkers.law import chunk_law
from expat.ingestion.chunkers.web import chunk_web
from expat.ingestion.enrich import EnrichResult, deduplicate, enrich
from expat.ingestion.fetch import FetchResult, PoliteFetcher, SnapshotStore, read_manual
from expat.ingestion.parsers.bayern_recht import parse_bayern_recht
from expat.ingestion.parsers.html import parse_html
from expat.ingestion.parsers.law_pdf import parse_law_pdf
from expat.ingestion.parsers.law_xml import parse_law_xml, read_law_xml
from expat.ingestion.sources import PageConfig, SourceConfig, SourceRegistry
from expat.schemas import ChunkRecord, ParentRecord

Fetch = Callable[[SourceConfig, PageConfig], FetchResult]


def source_of(doc_key: str) -> str:
    """'bgb#573c' -> 'bgb'. doc_keys always start with the source id (schemas/chunks.py)."""
    return doc_key.split("#", 1)[0]


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def chunk_page(source: SourceConfig, page: PageConfig, fetched: FetchResult) -> ChunkedDocument:
    """Parse + chunk one fetched page with the parser named in sources.yaml."""
    abbrev = source.law_abbrev
    if source.parser == "law_xml":
        return chunk_law(
            parse_law_xml(read_law_xml(fetched.path), page.url, abbrev, tuple(source.include_annexes)), source
        )
    if source.parser == "law_pdf":
        law = parse_law_pdf(
            fetched.path.read_bytes(),
            page.url,
            abbrev,
            long_title=source.name,
            start=source.pdf_start,
            end=source.pdf_end,
            valid_from=source.valid_from,
            valid_until=source.valid_until,
        )
        return chunk_law(law, source)
    html = _decode(fetched.path.read_bytes())
    if source.parser == "bayern_recht_html":
        return chunk_law(parse_bayern_recht(html, page.url, abbrev), source)
    return chunk_web(parse_html(html, page.url), source, page)


class SourceStatus(BaseModel):
    source_id: str
    name: str
    status: str  # ok | empty | failed
    chunks: int = 0
    parents: int = 0
    quarantined: int = 0
    pages: int = 0
    changed: bool = False
    fetched_at: str = ""
    language: str = ""
    error: str = ""


@dataclass
class IngestReport:
    statuses: list[SourceStatus] = field(default_factory=list)
    chunks: list[ChunkRecord] = field(default_factory=list)
    parents: list[ParentRecord] = field(default_factory=list)
    quarantine: list[dict[str, str]] = field(default_factory=list)
    duplicates_dropped: int = 0

    def render(self) -> str:
        lines = [f"{'source':32} {'status':7} {'chunks':>6} {'parents':>7}  note"]
        for s in self.statuses:
            note = s.error[:70] if s.error else ("changed" if s.changed else "")
            lines.append(f"{s.source_id:32} {s.status:7} {s.chunks:>6} {s.parents:>7}  {note}")
        lines.append(
            f"total: {len(self.chunks)} chunks, {len(self.parents)} parents, "
            f"{self.duplicates_dropped} duplicates dropped, {len(self.quarantine)} quarantined"
        )
        return "\n".join(lines)


def ingest_source(source: SourceConfig, fetch: Fetch) -> tuple[SourceStatus, EnrichResult]:
    status = SourceStatus(source_id=source.id, name=source.name, status="ok", language=source.language)
    total = EnrichResult()
    pages = source.all_pages()
    try:
        for page in pages:
            fetched = fetch(source, page)
            doc = chunk_page(source, page, fetched)
            part = enrich(doc, source, fetched.fetched_at.date())
            total.chunks += part.chunks
            total.parents += part.parents
            total.quarantine += part.quarantine
            status.changed = status.changed or fetched.changed
            status.fetched_at = max(status.fetched_at, fetched.fetched_at.isoformat())
    except Exception as exc:  # one broken site must not stop the run
        return status.model_copy(update={"status": "failed", "error": f"{type(exc).__name__}: {exc}"}), EnrichResult()
    status.pages = len(pages)
    status.chunks, status.parents, status.quarantined = len(total.chunks), len(total.parents), len(total.quarantine)
    if not total.chunks:
        status.status = "empty"
        status.error = "parser found no content (selector drift or bot page?)"
    return status, total


def make_fetch(fetcher: PoliteFetcher | None, store: SnapshotStore, offline: bool) -> Fetch:
    def fetch(source: SourceConfig, page: PageConfig) -> FetchResult:
        if source.fetch_method == "manual":
            path = source.manual_file()
            assert path is not None  # guaranteed by SourceConfig validation
            return read_manual(source.id, page.url, path)
        if offline or fetcher is None:
            return store.latest(source.id, page.url)
        return fetcher.fetch(source.id, page.url)

    return fetch


def run_ingestion(
    registry: SourceRegistry,
    processed_dir: Path,
    fetch: Fetch,
    source_ids: Iterable[str] | None = None,
) -> IngestReport:
    selected = [registry.get(i) for i in source_ids] if source_ids else registry.sources
    report = IngestReport()
    for source in selected:
        status, result = ingest_source(source, fetch)
        print(f"  {source.id}: {status.status} ({status.chunks} chunks)", flush=True)
        report.statuses.append(status)
        report.chunks += result.chunks
        report.parents += result.parents
        report.quarantine += result.quarantine

    # Partial run: keep records of sources that were not re-ingested (or that failed this time).
    replaced = {s.source_id for s in report.statuses if s.status != "failed"}
    old_chunks, old_parents, old_status = _read_previous(processed_dir)
    report.chunks = [c for c in old_chunks if c.metadata.source_id not in replaced] + report.chunks
    report.parents = [p for p in old_parents if source_of(p.doc_key) not in replaced] + report.parents
    report.chunks, report.duplicates_dropped = deduplicate(report.chunks)
    report.parents = list({p.parent_id: p for p in report.parents}.values())

    new_ids = {s.source_id for s in report.statuses}
    statuses = [s for s in old_status if s.get("source_id") not in new_ids] + [s.model_dump() for s in report.statuses]
    _write(processed_dir, report, statuses)
    return report


def _read_previous(processed_dir: Path) -> tuple[list[ChunkRecord], list[ParentRecord], list[dict[str, Any]]]:
    def read(name: str, model: type[BaseModel]) -> list[Any]:
        path = processed_dir / name
        if not path.exists():
            return []
        return [model.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    manifest = processed_dir / "manifest.json"
    statuses = json.loads(manifest.read_text(encoding="utf-8")).get("sources", []) if manifest.exists() else []
    return read("chunks.jsonl", ChunkRecord), read("parents.jsonl", ParentRecord), statuses


def _write(processed_dir: Path, report: IngestReport, statuses: list[dict[str, Any]]) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)

    def write_jsonl(name: str, lines: Iterable[str]) -> None:
        text = "".join(f"{line}\n" for line in lines)
        (processed_dir / name).write_text(text, encoding="utf-8", newline="\n")

    write_jsonl("chunks.jsonl", (c.model_dump_json() for c in report.chunks))
    write_jsonl("parents.jsonl", (p.model_dump_json() for p in report.parents))
    write_jsonl("quarantine.jsonl", (json.dumps(q, ensure_ascii=False) for q in report.quarantine))
    manifest = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "total_chunks": len(report.chunks),
        "total_parents": len(report.parents),
        "sources": sorted(statuses, key=lambda s: s["source_id"]),
    }
    (processed_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
