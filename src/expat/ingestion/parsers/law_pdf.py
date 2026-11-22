"""Parser for state regulations published as PDF (official gazettes / Verkündungsplattformen).

Why PDFs: the consolidated state law portals (gesetze.berlin.de, landesrecht-hamburg.de,
rv.hessenrecht.hessen.de, landesrecht-bw.de) disallow crawlers in robots.txt, but the official
gazette PDFs are allowed. Produces the same LawDocument as the XML / Bayern.Recht parsers, so the
law chunker, deep links and keyword headers work unchanged.

Layout found in the 2025/2026 rent-cap regulations (BE, HH, HE, BW):
    [preamble] "Auf Grund des § 556d ... verordnet:"
    "§ 1"                      <- a line of its own (references inside sentences are not headings)
    "Gebietsbestimmung"        <- title line (optional)
    "(1) ..." "(2) ..."        <- Absätze
    "Anlage 1 (zu § 1)"        <- optional annex, e.g. the list of municipalities
    "Begründung" / "A." + "Begründung:"  <- explanatory memorandum: not norm text, parsing stops there
A whole gazette issue (Hamburg) holds several laws: `start` / `end` regexes cut out the one we want.
"""

from __future__ import annotations

import re
from datetime import date

import pymupdf

from expat.ingestion.documents import LawDocument, LawNorm
from expat.ingestion.text import normalize_whitespace

_SPACE = r"[ \t   ]"
_HEADING_RE = re.compile(rf"^{_SPACE}*§{_SPACE}*(\d+[a-z]?){_SPACE}*$", re.MULTILINE)
_ANNEX_RE = re.compile(rf"^{_SPACE}*(Anlage(?:{_SPACE}+\d+)?)\b[^\n]*$", re.MULTILINE)
# Where the norm text ends: "Begründung" on its own line (optionally after an outline letter, "A." on the
# line before), or the signature line "Stuttgart, den 10. November 2026" that follows the last §.
DEFAULT_END = (
    rf"^{_SPACE}*(?:[A-Z]\.\s*)?Begründung\b"
    rf"|^{_SPACE}*[A-ZÄÖÜ][\w.\- ]*, den \d{{1,2}}\."
    rf"|^{_SPACE}*Gegeben in der Versammlung des Senats"  # Hamburg's signature formula
)
_ABSATZ_RE = re.compile(r"(?m)^\s*(?=\(\d+[a-z]?\)\s)")
_PAGE_NUMBER_LINE = re.compile(r"(?m)^\s*(?:-\s*)?(?:Seite\s+)?\d{1,3}(?:\s*von\s+\d{1,3})?(?:\s*-)?\s*$\n?")
# Running headers/footers of gazettes, e.g. "Gesetz- und Verordnungsblatt für das Land Hessen - Nr. 78 vom ...".
_GAZETTE_LINE = re.compile(r"(?im)^.*(?:verordnungsblatt|gesetzblatt für|amtsblatt für).*(?:nr\.|jahrgang).*$\n?")
# A first line starting like a sentence is norm text, not a § title.
_SENTENCE_STARTS = ("Die ", "Der ", "Das ", "Diese ", "Dieser ", "In ", "Für ", "Auf ", "Soweit ", "Abweichend ")


def pdf_text(data: bytes) -> str:
    """Plain text of all pages, in reading order."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _clean(text: str) -> str:
    text = _GAZETTE_LINE.sub("", text)
    text = _PAGE_NUMBER_LINE.sub("", text)
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # words hyphenated across lines: "Woh-\nnung" -> "Wohnung"


def _cut(text: str, start: str, end: str) -> str:
    if start:
        match = re.search(start, text, re.MULTILINE)
        if not match:
            raise ValueError(f"start marker {start!r} not found in the PDF text")
        text = text[match.start() :]
    # Search the end only after the first § heading: gazettes print "Wiesbaden, den 19. November 2026" as a
    # header line above the regulation, which must not end it.
    first = _HEADING_RE.search(text)
    end_match = re.compile(end or DEFAULT_END, re.MULTILINE).search(text, first.end() if first else 0)
    return text[: end_match.start()] if end_match else text


def _looks_like_title(line: str) -> bool:
    """'Gebietsbestimmung' is a title; 'Die Mieterschutzverordnung ... wird aufgehoben.' is the norm text."""
    line = line.strip()
    return bool(line) and not line.startswith("(") and len(line) <= 80 and not line.startswith(_SENTENCE_STARTS)


def _paragraphs(body: str) -> list[str]:
    """Split a § body into Absätze at '(1)', '(2)' ...; join the lines of each into one paragraph."""
    parts = [p for p in _ABSATZ_RE.split(body) if p.strip()]
    return [normalize_whitespace(p.replace("\n", " ")) for p in parts]


def _list_entries(body: str) -> list[str]:
    """Lines of an annex list. Numbers printed on their own line ('20.') are joined with the next line."""
    entries: list[str] = []
    for line in (normalize_whitespace(ln) for ln in body.splitlines()):
        if not line:
            continue
        if entries and re.fullmatch(r"\d+\.", entries[-1]):
            entries[-1] = f"{entries[-1]} {line}"
        else:
            entries.append(line)
    return entries


def parse_law_pdf(
    data: bytes,
    source_url: str,
    abbrev: str,
    *,
    long_title: str = "",
    start: str = "",
    end: str = "",
    valid_from: date | None = None,
    valid_until: date | None = None,
) -> LawDocument:
    text = _cut(_clean(pdf_text(data)), start, end)
    norms: list[LawNorm] = []

    headings = list(_HEADING_RE.finditer(text))
    annex = _ANNEX_RE.search(text, headings[-1].end()) if headings else _ANNEX_RE.search(text)
    norm_area_end = annex.start() if annex else len(text)
    for i, match in enumerate(headings):
        stop = headings[i + 1].start() if i + 1 < len(headings) else norm_area_end
        lines = text[match.end() : stop].strip("\n").splitlines()
        title = ""
        if len(lines) > 1 and _looks_like_title(lines[0]):
            title = normalize_whitespace(lines.pop(0))
        absaetze = _paragraphs("\n".join(lines))
        if absaetze:
            paragraph = match.group(1).lower()
            norms.append(
                LawNorm(
                    enbez=f"§ {match.group(1)}", paragraph=paragraph, title=title, absaetze=absaetze, url=source_url
                )
            )

    if annex:
        next_annex = _ANNEX_RE.search(text, annex.end())
        entries = _list_entries(text[annex.end() : next_annex.start() if next_annex else len(text)])
        if entries:
            norms.append(
                LawNorm(
                    enbez=normalize_whitespace(annex.group(1)),
                    paragraph="anlage",
                    title=normalize_whitespace(annex.group(0)[len(annex.group(1)) :]).strip(" :()"),
                    absaetze=["\n".join(entries)],
                    url=source_url,
                )
            )

    return LawDocument(
        abbrev=abbrev,
        long_title=long_title,
        url=source_url,
        valid_from=valid_from,
        valid_until=valid_until,
        norms=norms,
    )
