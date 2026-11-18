"""Intermediate, parser-neutral document models (the output of `parsers/`, the input of `chunkers/`).

Why an intermediate layer instead of chunking straight from HTML/XML?
Parsers deal with messy markup; chunkers deal with structure and token budgets. Keeping a small
typed model between them means the chunkers can be tested with hand-built documents, and adding
a new site only touches a parser.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------------------------
# Laws and regulations
# ---------------------------------------------------------------------------------------------


class LawNorm(BaseModel):
    """One § (or an Anlage) with its Absätze, in reading order."""

    enbez: str  # as printed: "§ 573c", "Anlage (zu § 1)"
    paragraph: str  # normalised key used in doc_key: "573c", "anlage"
    title: str = ""  # "Kündigungsfristen"
    absaetze: list[str]  # one string per Absatz (<P>); lists are kept inline as "1. …" lines
    gliederung: list[str] = Field(default_factory=list)  # outer -> inner: ["Buch 2 …", "Abschnitt 8 …"]
    url: str  # deep link to this § (citation target)
    is_table: bool = False  # Anlage tables: chunk as table (split by rows), not by Absatz


class LawDocument(BaseModel):
    abbrev: str  # "BGB"
    long_title: str = ""
    url: str  # canonical URL of the whole law (doc_id is derived from it)
    builddate: date | None = None  # gesetze-im-internet build date (freshness signal)
    standangabe: str = ""  # "Zuletzt geändert durch …"
    valid_from: date | None = None
    valid_until: date | None = None
    norms: list[LawNorm]


# ---------------------------------------------------------------------------------------------
# Web pages
# ---------------------------------------------------------------------------------------------


class BlockKind(StrEnum):
    TEXT = "text"  # a paragraph (markdown)
    LIST = "list"  # a whole <ul>/<ol>/<dl> as markdown, kept intact
    TABLE = "table"  # a whole <table> as a markdown table
    HEADING = "heading"  # a sub-heading below the section level (e.g. an H3 inside an H2 section)
    FAQ = "faq"  # one question + answer (accordion item / <details>)


class Block(BaseModel):
    kind: BlockKind
    text: str  # markdown; for FAQ the answer
    question: str = ""  # only for FAQ


class Section(BaseModel):
    """A run of blocks under one heading at the profile's section level (usually H2).

    `heading` is empty for content before the first section heading (the page intro).
    `context` holds headings *above* the section level that are still open (rare; e.g. the
    BayernPortal "Leistungsdetails" H2 above its H3 sections).
    """

    heading: str = ""
    context: list[str] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)


class WebDocument(BaseModel):
    url: str  # canonical URL (doc_id derives from it)
    title: str  # page H1
    sections: list[Section]
    stand: str = ""  # "last updated" text if the page shows one
