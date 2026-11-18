"""Source registry: the typed view of `sources.yaml`.

Why a Pydantic model instead of reading the YAML as a dict?
`sources.yaml` is hand-edited. A typo ("procedur", a missing domain) should fail loudly when the
pipeline starts, not as a `KeyError` halfway through a 10-minute crawl. The model is the single
place that documents which keys exist and what they mean.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from expat.config import REPO_ROOT
from expat.schemas import Audience, Domain, Jurisdiction, SourceType

DEFAULT_SOURCES_PATH = REPO_ROOT / "sources.yaml"

# Parser names follow docs/data-sources.md. All *_html parsers share one implementation
# (parsers/html.py); the distinction documents intent and picks the default chunker.
ParserName = Literal["law_xml", "bayern_recht_html", "guide_html", "procedure_html", "faq_html"]

_PARAGRAPH_RE = re.compile(r"^(\d+)([a-z]*)$")


def paragraph_sort_key(paragraph: str) -> tuple[int, str]:
    """Turn a paragraph label into a sortable key: "573c" -> (573, "c").

    Plain string comparison would put "58" after "573c" ("5" < "7"), so ranges like
    "535-580a" need numeric comparison of the number part and alphabetic of the suffix.
    """
    m = _PARAGRAPH_RE.match(paragraph.strip().lower())
    if not m:
        raise ValueError(f"not a paragraph label: {paragraph!r}")
    return int(m.group(1)), m.group(2)


class ParagraphRange(BaseModel):
    """An inclusive § range such as "535-580a" or a single "17"."""

    start: str
    end: str

    @classmethod
    def parse(cls, spec: str) -> ParagraphRange:
        start, _, end = spec.replace(" ", "").partition("-")
        paragraph_sort_key(start)  # validate early
        paragraph_sort_key(end or start)
        return cls(start=start.lower(), end=(end or start).lower())

    def contains(self, paragraph: str) -> bool:
        try:
            key = paragraph_sort_key(paragraph)
        except ValueError:
            return False
        return paragraph_sort_key(self.start) <= key <= paragraph_sort_key(self.end)


class DomainRange(BaseModel):
    """Maps a § range of a law to a routing domain (e.g. EStG §§ 62-78 -> family)."""

    range: str
    domain: Domain
    subtopic: str = ""

    def contains(self, paragraph: str) -> bool:
        return ParagraphRange.parse(self.range).contains(paragraph)


class PageConfig(BaseModel):
    """One web page of a source. A source may span several pages (e.g. several FAQ pages)."""

    url: str
    source_type: SourceType | None = None  # overrides the source-level type for this page
    alt_lang_url: str = ""


class SourceConfig(BaseModel):
    """One entry of sources.yaml. Field meanings: docs/data-sources.md (`sources.yaml` entry format)."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    publisher: str = ""
    url: str | None = None
    pages: list[PageConfig] = Field(default_factory=list)
    source_type: SourceType
    parser: ParserName
    domain: Domain | None = None
    subtopic: str = ""
    domain_map: list[DomainRange] = Field(default_factory=list)
    include_ranges: list[str] = Field(default_factory=list)
    law_abbrev: str = ""  # display abbreviation, e.g. "AufenthG" (falls back to the XML's jurabk)
    language: Literal["de", "en"] = "de"
    jurisdiction: Jurisdiction
    state: str = ""
    city: str = ""
    applies_to: list[Audience] = Field(default_factory=lambda: [Audience.ALL], min_length=1)
    alt_lang_urls: dict[str, str] = Field(default_factory=dict)
    is_machine_translated: bool = False
    fetch_method: Literal["http", "manual"] = "http"
    manual_path: str | None = None  # relative to the repo root, e.g. data/manual/miig-blue-card.html
    refresh: Literal["weekly", "monthly", "quarterly"] = "monthly"
    terms: str = ""
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> SourceConfig:
        if self.domain is None and not self.domain_map:
            raise ValueError(f"{self.id}: needs `domain` or `domain_map`")
        if self.fetch_method == "manual" and not self.manual_path:
            raise ValueError(f"{self.id}: fetch_method=manual requires `manual_path`")
        if self.fetch_method == "http" and not self.all_pages():
            raise ValueError(f"{self.id}: needs `url` or `pages`")
        for spec in self.include_ranges:
            ParagraphRange.parse(spec)
        return self

    def all_pages(self) -> list[PageConfig]:
        """The primary `url` (if any) followed by the extra `pages`, in file order."""
        primary = [PageConfig(url=self.url, alt_lang_url=self.alt_lang_urls.get("en", ""))] if self.url else []
        return primary + list(self.pages)

    def includes_paragraph(self, paragraph: str) -> bool:
        """True if a law § is in scope. No include_ranges means 'the whole law'."""
        if not self.include_ranges:
            return True
        return any(ParagraphRange.parse(spec).contains(paragraph) for spec in self.include_ranges)

    def domain_for(self, paragraph: str | None = None) -> tuple[Domain, str]:
        """Routing domain + subtopic, using the § specific `domain_map` when it matches."""
        if paragraph:
            for entry in self.domain_map:
                if entry.contains(paragraph):
                    return entry.domain, entry.subtopic or self.subtopic
        if self.domain is not None:
            return self.domain, self.subtopic
        # Only a domain_map was given and nothing matched: use its first entry as the default.
        return self.domain_map[0].domain, self.domain_map[0].subtopic or self.subtopic

    def manual_file(self, repo_root: Path = REPO_ROOT) -> Path | None:
        return repo_root / self.manual_path if self.manual_path else None


class SourceRegistry(BaseModel):
    """The whole file. Wrapping the list lets us validate cross-entry rules (unique ids)."""

    sources: list[SourceConfig]

    @model_validator(mode="after")
    def _unique_ids(self) -> SourceRegistry:
        seen: set[str] = set()
        for source in self.sources:
            if source.id in seen:
                raise ValueError(f"duplicate source id: {source.id}")
            seen.add(source.id)
        return self

    def get(self, source_id: str) -> SourceConfig:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise KeyError(f"unknown source id {source_id!r}; known: {', '.join(s.id for s in self.sources)}")


def load_sources(path: Path = DEFAULT_SOURCES_PATH) -> SourceRegistry:
    """Load and validate sources.yaml. The file is a plain YAML list of entries."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain a YAML list of sources")
    return SourceRegistry(sources=raw)
