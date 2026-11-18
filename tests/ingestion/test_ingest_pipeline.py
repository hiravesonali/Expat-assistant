"""Chunkers + enrich + orchestrator, end to end on the saved fixtures (no network)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from expat.ingestion.fetch import FetchError, FetchResult
from expat.ingestion.pipeline import run_ingestion
from expat.ingestion.sources import PageConfig, SourceConfig, SourceRegistry
from expat.schemas import ChunkRecord, SectionKind, SourceType

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ingestion"
FETCHED_AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)

BGB = SourceConfig(
    id="bgb",
    name="Bürgerliches Gesetzbuch (BGB)",
    url="https://www.gesetze-im-internet.de/bgb/xml.zip",
    source_type=SourceType.LAW,
    parser="law_xml",
    law_abbrev="BGB",
    domain="tenancy",
    include_ranges=["535-580a"],
    jurisdiction="federal",
)
MUC = SourceConfig(
    id="muc-anmeldung",
    name="Landeshauptstadt München: Wohnsitz anmelden",
    url="https://stadt.muenchen.de/service/info/wohnsitzanmeldung/1063475/n0/",
    source_type=SourceType.PROCEDURE,
    parser="procedure_html",
    domain="bureaucracy",
    jurisdiction="city",
    state="BY",
    city="munich",
)
FILES = {"bgb": "bgb_excerpt.xml", "muc-anmeldung": "muc_procedure.html"}


def fake_fetch(source: SourceConfig, page: PageConfig) -> FetchResult:
    if source.id not in FILES:
        raise FetchError(f"{page.url}: HTTP 503")
    return FetchResult(
        url=page.url,
        final_url=page.url,
        path=FIXTURES / FILES[source.id],
        fetched_at=FETCHED_AT,
        changed=True,
        from_network=False,
    )


def read_chunks(path: Path) -> list[ChunkRecord]:
    return [ChunkRecord.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def processed(tmp_path: Path) -> Path:
    run_ingestion(SourceRegistry(sources=[BGB, MUC]), tmp_path, fake_fetch)
    return tmp_path


def test_law_chunks_are_absatz_level_with_exact_references(processed):
    chunks = [c for c in read_chunks(processed / "chunks.jsonl") if c.metadata.doc_key == "bgb#573c"]
    assert chunks, "§ 573c must be ingested (doc_key used by the golden set)"
    refs = {c.metadata.legal_reference for c in chunks}
    assert "§ 573c Abs. 1 BGB" in refs or refs == {"§ 573c BGB"}
    first = chunks[0]
    assert first.metadata.parent_id == "bgb#573c"
    assert first.metadata.source_url.endswith("__573c.html")
    assert first.metadata.last_verified.isoformat() == "2026-11-18"
    assert first.embed_text.startswith("[BGB") and "[tenancy]" in first.embed_text.splitlines()[0]


def test_include_ranges_filter_out_other_paragraphs(processed):
    keys = {c.metadata.doc_key for c in read_chunks(processed / "chunks.jsonl")}
    assert "bgb#10" not in keys  # outside 535-580a


def test_procedure_page_maps_sections_to_kinds_and_city_metadata(processed):
    chunks = [c for c in read_chunks(processed / "chunks.jsonl") if c.metadata.source_id == "muc-anmeldung"]
    kinds = {c.metadata.section_kind for c in chunks}
    assert {SectionKind.DOCUMENTS, SectionKind.FEES, SectionKind.REQUIREMENTS} <= kinds
    assert all(c.metadata.city == "munich" and c.metadata.state == "BY" for c in chunks)
    assert any(c.metadata.doc_key == "muc-anmeldung#documents" for c in chunks)


def test_ids_are_unique_and_deterministic(tmp_path, processed):
    first = read_chunks(processed / "chunks.jsonl")
    assert len({c.metadata.chunk_id for c in first}) == len(first)
    run_ingestion(SourceRegistry(sources=[BGB, MUC]), tmp_path / "again", fake_fetch)
    again = read_chunks(tmp_path / "again" / "chunks.jsonl")
    assert [c.metadata.chunk_id for c in first] == [c.metadata.chunk_id for c in again]


def test_every_chunk_parent_exists(processed):
    parent_ids = {
        json.loads(line)["parent_id"] for line in (processed / "parents.jsonl").read_text(encoding="utf-8").splitlines()
    }
    assert all(c.metadata.parent_id in parent_ids for c in read_chunks(processed / "chunks.jsonl"))


def test_failed_source_is_reported_and_keeps_previous_records(processed):
    broken_bgb = BGB.model_copy(update={"id": "bgb"})
    files_backup = FILES.pop("bgb")
    try:
        report = run_ingestion(SourceRegistry(sources=[broken_bgb, MUC]), processed, fake_fetch, ["bgb"])
    finally:
        FILES["bgb"] = files_backup
    assert report.statuses[0].status == "failed" and "503" in report.statuses[0].error
    # the old BGB chunks survive a failed re-fetch
    assert any(c.metadata.source_id == "bgb" for c in read_chunks(processed / "chunks.jsonl"))
    manifest = json.loads((processed / "manifest.json").read_text(encoding="utf-8"))
    statuses = {s["source_id"]: s["status"] for s in manifest["sources"]}
    assert statuses == {"bgb": "failed", "muc-anmeldung": "ok"}
