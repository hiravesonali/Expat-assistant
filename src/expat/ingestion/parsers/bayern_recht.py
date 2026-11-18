"""Parser for Bayern.Recht (gesetze-bayern.de) "Gesamtansicht" pages of Bavarian regulations.

Used for the Bavarian Mieterschutzverordnung (MiSchuV). Bavarian law is not on
gesetze-im-internet.de, and the official gazette page (verkuendung-bayern.de) links the
municipality list (Anlage) only as a PDF. Bayern.Recht renders the consolidated text, including
the Anlage as an HTML table, so it is the better source. It produces the same LawDocument as the
federal XML parser, so the law chunker handles both.

Markup (verified 2026-11 on BayMiSchuV2025/true):
    div#doc-metadata   "Text gilt ab: 01.01.2026" / "Gesamtvorschrift gilt bis: 31.12.2029"
    h1.titelzeile      long title
    div.cont           one per § / Anlage:
        div.paraheading > div.paranr "§ 1" + div.paratitel "Anwendungsbereich …"
        div.paratext    one per Absatz (sup.satznr = sentence numbers, dropped)
        div.annexnr "Anlage (zu § 1)" + div.annextitel + <table>
"""

from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from expat.ingestion.documents import LawDocument, LawNorm
from expat.ingestion.text import markdown_table, normalize_whitespace

_PARANR_RE = re.compile(r"^§\s*(\d+[a-z]*)$", re.IGNORECASE)
_DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")


def parse_bayern_recht(html: str, source_url: str, abbrev: str) -> LawDocument:
    soup = BeautifulSoup(html, "lxml")
    for sup in soup.select("sup.satznr, sup.fnnr"):
        sup.decompose()
    # Deep links: ".../Content/Document/BayMiSchuV2025/true" -> ".../BayMiSchuV2025-1" per §.
    doc_base = re.sub(r"/true/?$", "", source_url)

    title_el = soup.select_one("h1.titelzeile")
    long_title = normalize_whitespace(title_el.get_text(" ")) if title_el else ""
    long_title = re.sub(r"\s*\[\d+\]\s*", " ", long_title).strip()
    meta_el = soup.select_one("#doc-metadata")
    metadata = normalize_whitespace(meta_el.get_text("\n")) if meta_el else ""

    norms: list[LawNorm] = []
    for cont in soup.select("#content div.cont"):
        paranr = cont.select_one(".paranr")
        annexnr = cont.select_one(".annexnr")
        if paranr is not None:
            match = _PARANR_RE.match(normalize_whitespace(paranr.get_text(" ")))
            if not match:
                continue
            paragraph = match.group(1).lower()
            title_el = cont.select_one(".paratitel")
            absaetze = [normalize_whitespace(p.get_text(" ")) for p in cont.select(".paratext")]
            absaetze = [a for a in absaetze if a]
            if absaetze:
                norms.append(
                    LawNorm(
                        enbez=f"§ {match.group(1)}",
                        paragraph=paragraph,
                        title=normalize_whitespace(title_el.get_text(" ")) if title_el else "",
                        absaetze=absaetze,
                        url=f"{doc_base}-{paragraph}",
                    )
                )
        elif annexnr is not None:
            table = cont.find("table")
            title_el = cont.select_one(".annextitel")
            if isinstance(table, Tag):
                index = sum(1 for n in norms if n.is_table) + 1
                norms.append(
                    LawNorm(
                        enbez=normalize_whitespace(annexnr.get_text(" ")),
                        paragraph="anlage" if index == 1 else f"anlage{index}",
                        title=normalize_whitespace(title_el.get_text(" ")) if title_el else "",
                        absaetze=[_table_markdown(table)],
                        url=f"{doc_base}-ANL_{index}",
                        is_table=True,
                    )
                )

    return LawDocument(
        abbrev=abbrev,
        long_title=long_title,
        url=source_url,
        valid_from=_date_after(metadata, "gilt ab"),
        valid_until=_date_after(metadata, "gilt bis"),
        norms=norms,
    )


def _date_after(text: str, label: str) -> date | None:
    index = text.find(label)
    if index < 0:
        return None
    match = _DATE_RE.search(text, index)
    return datetime.strptime(match.group(1), "%d.%m.%Y").date() if match else None


def _table_markdown(table: Tag) -> str:
    def cells(row: Tag) -> list[str]:
        return [normalize_whitespace(c.get_text(" ")) for c in row.find_all(["th", "td"])]

    head_rows = table.select("thead tr")
    body_rows = table.select("tbody tr") or [r for r in table.find_all("tr") if r not in head_rows]
    header = cells(head_rows[0]) if head_rows else []
    rows = [c for c in (cells(r) for r in body_rows) if any(c)]
    return markdown_table(header, rows)
