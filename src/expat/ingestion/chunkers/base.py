"""Shared types and helpers for the chunkers.

Chunkers decide *structure* (what is a child, what is its parent, which section_kind). They emit
drafts; `enrich.py` turns drafts into validated ChunkRecord/ParentRecord with ids, hashes, token
counts, language and the contextual header. Keeping the two apart keeps each piece testable.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from expat.schemas import Domain, SectionKind, SourceType

# Size targets in tokens (docs/vector-db-design.md §3).
LAW_WHOLE_PARAGRAPH_MAX = 350  # a § shorter than this is one child
LAW_CHILD_MAX = 400
LAW_PARENT_MAX = 1500
GUIDE_CHILD_MIN = 200
GUIDE_CHILD_MAX = 400
GUIDE_OVERLAP = 50
GUIDE_PARENT_MAX = 1500
PROCEDURE_CHILD_MAX = 500
PROCEDURE_PAGE_PARENT_MAX = 2000
FAQ_CHILD_MAX = 500
CHECKLIST_MAX = 700
TABLE_MAX = 600


@dataclass
class ParentDraft:
    parent_id: str
    doc_key: str
    text: str
    title: str
    heading_path: str
    source_url: str
    legal_reference: str = ""


@dataclass
class ChunkDraft:
    text: str
    parent_id: str
    doc_key: str
    structural_path: str  # stable position inside the document; part of the chunk_id hash
    title: str
    heading_path: str
    source_type: SourceType
    source_url: str
    section_kind: SectionKind = SectionKind.OTHER
    legal_reference: str = ""
    domain: Domain | None = None  # None -> the source's default domain
    subtopic: str = ""
    alt_lang_url: str = ""


@dataclass
class ChunkedDocument:
    """Everything one source document (a law, a web page) contributes."""

    doc_url: str  # canonical URL -> doc_id
    doc_text: str  # cleaned full text -> doc_version
    title: str
    chunks: list[ChunkDraft] = field(default_factory=list)
    parents: list[ParentDraft] = field(default_factory=list)
    valid_from: date | None = None
    valid_until: date | None = None


def short_hash(*parts: str, length: int = 16) -> str:
    """sha1 over the parts joined with a separator that cannot occur in URLs or headings."""
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]


def join_path(*parts: str) -> str:
    """'BGB › Kapitel 5 … › § 573c …' (empty and repeated parts dropped)."""
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if part and (not out or out[-1] != part):
            out.append(part)
    return " › ".join(out)


# --- section_kind mapping --------------------------------------------------------------------
# Order matters: the first rule that matches wins. "Dauer und Kosten" must be FEES (the question
# users ask is "how much?"), "Erforderliche Unterlagen" must be DOCUMENTS, not REQUIREMENTS.
_SECTION_KIND_RULES: tuple[tuple[SectionKind, re.Pattern[str]], ...] = (
    (SectionKind.DOCUMENTS, re.compile(r"unterlagen|dokumente|nachweise|required documents|documents|paperwork")),
    (SectionKind.FEES, re.compile(r"kosten|gebühr|preis|entgelt|fees?\b|costs?\b|charges?")),
    (SectionKind.REQUIREMENTS, re.compile(r"voraussetzung|anspruch|requirements?|conditions?|eligib|wer kann|who can")),
    (
        SectionKind.DEADLINES,
        re.compile(r"frist|bearbeitungs(dauer|zeit)|dauer|gültigkeit|deadline|processing time|validity|how long"),
    ),
    (SectionKind.LEGAL_BASIS, re.compile(r"rechtsgrundlage|rechtliche grundlage|gesetzliche grundlage|legal basis")),
    (SectionKind.CONTACT, re.compile(r"kontakt|zuständig|ansprechp|öffnungszeit|contact|responsible authorit")),
    (
        SectionKind.STEPS,
        re.compile(r"verfahrensablauf|ablauf|so geht|antrag|vorgehen|procedure|how to apply|steps|application"),
    ),
    (
        SectionKind.OVERVIEW,
        re.compile(r"beschreibung|allgemein|überblick|description|overview|purpose|was ist|what is"),
    ),
)


def section_kind_for(heading: str) -> SectionKind:
    """Map a DE/EN section heading to a SectionKind. Empty heading (page intro) -> OVERVIEW."""
    text = heading.strip().lower()
    if not text:
        return SectionKind.OVERVIEW
    for kind, pattern in _SECTION_KIND_RULES:
        if pattern.search(text):
            return kind
    return SectionKind.OTHER
