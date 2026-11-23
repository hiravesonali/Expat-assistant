"""Parser for gesetze-im-internet.de XML (`/<abk>/xml.zip`, DTD gii-norm.dtd).

Structure we rely on (verified on BGB, BMG, AufenthG, BEEG, EStG builds of 2026-11):

    <dokumente builddate="20261116220005">
      <norm>                                  first norm: law metadata
        <metadaten><jurabk>BMG</jurabk><langue>Bundesmeldegesetz</langue>
                   <standangabe><standkommentar>Zuletzt geändert durch …</standkommentar>…
      <norm>                                  a structural heading ("Gliederung")
        <metadaten><gliederungseinheit><gliederungskennzahl>030</…><gliederungsbez>Abschnitt 3</…>
                   <gliederungstitel>Allgemeine Meldepflichten</…>
      <norm>                                  a paragraph
        <metadaten><enbez>§ 17</enbez><titel>Anmeldung, Abmeldung</titel>
        <textdaten><text><Content><P>(1) Wer eine Wohnung bezieht, …</P><P>(2) …</P>

Each <P> is one Absatz. Lists inside a <P> are <DL><DT>1.</DT><DD><LA>…</LA></DD></DL>.
We skip the "Inhaltsübersicht" (table of contents), "(weggefallen)" (repealed) norms and
footnotes (`fussnoten`: editorial notes, not law). Anlagen (annexes) are skipped too, unless the source
asks for them by number (`annexes`, e.g. FeV Anlage 11, the country list for licence conversion): those
become table norms, `<enbez>Anlage 11</enbez><titel>(zu § 31)<BR/>Staatenliste …</titel>` + one <table>.
"""

from __future__ import annotations

import re
import zipfile
from datetime import date, datetime
from pathlib import Path

from lxml import etree

from expat.ingestion.documents import LawDocument, LawNorm
from expat.ingestion.text import markdown_table, normalize_whitespace

_ENBEZ_RE = re.compile(r"^§\s*(\d+[a-z]*)$", re.IGNORECASE)
_ANLAGE_RE = re.compile(r"^Anlage\s+(\d+[a-z]*)$", re.IGNORECASE)
_ZU_RE = re.compile(r"^\((zu [^)]*)\)\s*")  # "(zu § 31) Staatenliste …"
_REPEALED_RE = re.compile(r"^\(?\s*weggefallen\s*\)?$", re.IGNORECASE)
_SKIP_TAGS = {"FnR", "FnArea", "Footnotes", "IMG", "img", "noindex"}


def read_law_xml(path: Path) -> bytes:
    """Return the XML bytes from a downloaded `xml.zip` (or a plain .xml file)."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith(".xml")]
            if not members:
                raise ValueError(f"{path}: no XML file in archive")
            return archive.read(members[0])
    return path.read_bytes()


def parse_law_xml(xml: bytes, source_url: str, abbrev: str = "", annexes: tuple[str, ...] = ()) -> LawDocument:
    """Parse a whole law into LawDocument (all norms; range filtering happens in the chunker).

    `source_url` is the xml.zip URL; deep links are derived from it:
    https://www.gesetze-im-internet.de/bgb/xml.zip -> https://www.gesetze-im-internet.de/bgb/__573c.html
    """
    # The DOCTYPE points to a remote DTD: never fetch it, never resolve entities (XXE-safe).
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=True)
    root = etree.fromstring(xml, parser=parser)
    base_url = source_url.rsplit("/", 1)[0] + "/"

    law_abbrev = abbrev
    long_title = ""
    standangabe = ""
    gliederung: list[tuple[int, str]] = []  # (depth, "Abschnitt 3 Allgemeine Meldepflichten")
    norms: list[LawNorm] = []

    for norm in root.iter("norm"):
        meta = norm.find("metadaten")
        if meta is None:
            continue
        law_abbrev = law_abbrev or _text(meta.find("jurabk"))
        if not long_title and meta.find("langue") is not None:
            long_title = _text(meta.find("langue"))
            standangabe = "; ".join(_text(s) for s in meta.iterfind("standangabe/standkommentar") if _text(s))

        unit = meta.find("gliederungseinheit")
        if unit is not None:
            # gliederungskennzahl encodes depth in groups of 3 digits: "010" -> 1, "010020" -> 2.
            depth = max(1, len(_text(unit.find("gliederungskennzahl"))) // 3)
            label = " ".join(p for p in (_text(unit.find("gliederungsbez")), _text(unit.find("gliederungstitel"))) if p)
            gliederung = [(d, lbl) for d, lbl in gliederung if d < depth] + [(depth, label)]
            continue

        enbez = _text(meta.find("enbez"))
        anlage = _ANLAGE_RE.match(enbez)
        if anlage and anlage.group(1).lower() in {a.lower() for a in annexes}:
            annex = _annex_norm(norm, anlage.group(1).lower(), base_url)
            if annex is not None:
                norms.append(annex)
            continue
        match = _ENBEZ_RE.match(enbez)
        if not match:  # Inhaltsübersicht, "§§ 1 bis 3" (repealed ranges), Anlagen, Präambel
            continue
        title = _text(meta.find("titel"))
        absaetze = _absaetze(norm)
        if _REPEALED_RE.match(title) or not absaetze or all(_REPEALED_RE.match(a) for a in absaetze):
            continue
        paragraph = match.group(1).lower()
        norms.append(
            LawNorm(
                enbez=f"§ {match.group(1)}",
                paragraph=paragraph,
                title=title,
                absaetze=absaetze,
                gliederung=[label for _, label in gliederung],
                url=f"{base_url}__{paragraph}.html",
            )
        )

    return LawDocument(
        abbrev=law_abbrev or "?",
        long_title=long_title,
        url=source_url,
        builddate=_builddate(root.get("builddate", "")),
        standangabe=standangabe,
        norms=norms,
    )


def _annex_norm(norm: etree._Element, number: str, base_url: str) -> LawNorm | None:
    """An Anlage with a table -> a table norm ("Anlage 11 (zu § 31)", paragraph "anlage11")."""
    table = norm.find(".//textdaten/text/Content//table")
    if table is None:
        return None
    rendered = _render_table(table, fill_down=True)
    if not rendered:
        return None
    title = _text(norm.find("metadaten/titel"))
    zu = _ZU_RE.match(title)
    enbez = f"Anlage {number.upper() if not number.isdigit() else number}"
    if zu:
        enbez, title = f"{enbez} ({zu.group(1)})", title[zu.end() :]
    return LawNorm(
        enbez=enbez,
        paragraph=f"anlage{number}",
        title=title,
        absaetze=[rendered],
        url=f"{base_url}anlage_{number}.html",
        is_table=True,
    )


def _builddate(value: str) -> date | None:
    try:
        return datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _text(element: etree._Element | None) -> str:
    return normalize_whitespace(" ".join(element.itertext())) if element is not None else ""


def _absaetze(norm: etree._Element) -> list[str]:
    """One string per <P> in the norm's main text. Non-<P> blocks join the previous Absatz."""
    content = norm.find("textdaten/text/Content")
    if content is None:
        return []
    absaetze: list[str] = []
    for child in content:
        if not isinstance(child.tag, str):
            continue  # comments / processing instructions
        rendered = normalize_whitespace(_render(child))
        if not rendered:
            continue
        if child.tag == "P" or not absaetze:
            absaetze.append(rendered)
        else:
            absaetze[-1] = f"{absaetze[-1]}\n{rendered}"
    return absaetze


def _render(element: etree._Element) -> str:
    """Flatten an element to text: its own text, each child rendered, each child's tail.

    Lists become one "1. item" line per entry. Nested lists are not indented (whitespace is
    normalised per line later); their markers ("a)", "aa)") already show the nesting level.
    """
    parts = [element.text or ""]
    for child in element:
        if child.tag == "SUP" and child.get("class") == "Rec":
            parts.append(
                " "
            )  # sentence numbers ("<SUP class="Rec">3</SUP>Bei Eheschließung …", EStG): noise for search
        elif isinstance(child.tag, str) and child.tag not in _SKIP_TAGS:
            if child.tag == "DL":
                parts.append(f"\n{_render_list(child)}\n")
            elif child.tag == "table":
                parts.append(f"\n{_render_table(child)}\n")
            elif child.tag == "BR":
                parts.append("\n")
            else:
                parts.append(_render(child))
        parts.append(child.tail or "")  # text after a child belongs to the parent
    return "".join(parts)


def _render_list(dl: etree._Element) -> str:
    lines: list[str] = []
    marker = ""
    for child in dl:
        if child.tag == "DT":
            marker = normalize_whitespace("".join(child.itertext()))
        elif child.tag == "DD":
            body = normalize_whitespace(_render(child))
            lines.append(f"{marker} {body}".strip())
    return "\n".join(lines)


def _render_table(table: etree._Element, fill_down: bool = False) -> str:
    """CALS table -> markdown. `fill_down`: an empty first cell repeats the row above (a country with
    several class rows), so every row stays self-contained when the table is split into chunks."""
    has_head = table.find(".//thead") is not None
    rows: list[list[str]] = []
    group = ""  # "Fahrerlaubnisse der Kanadischen Provinzen:" above "– Alberta" rows
    for row in table.iter("row"):
        # _render skips footnote markers (FnR); split/join flattens <BR/> so a cell stays on one line
        cells = [" ".join(_render(entry).split()) for entry in row.iter("entry")]
        if fill_down and cells and len(rows) >= int(has_head):
            first = cells[0]
            if _REPEALED_RE.match(first):
                continue
            if first.endswith(":") and not any(cells[1:]):
                group = first.rstrip(":")
            elif first.startswith(("–", "-")) and group:
                cells[0] = f"{group}: {first.lstrip('–- ')}"
            elif not first and rows:
                cells[0] = rows[-1][0]
            elif first:
                group = ""
        rows.append(cells)
    if not rows:
        return ""
    header, body = (rows[0], rows[1:]) if has_head else ([], rows)
    return markdown_table(header, body)
