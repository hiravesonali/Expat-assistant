"""Law parsers: gesetze-im-internet XML (real BGB excerpt) and Bayern.Recht HTML (synthetic)."""

from datetime import date
from pathlib import Path

import pytest

from expat.ingestion.parsers.bayern_recht import parse_bayern_recht
from expat.ingestion.parsers.law_xml import parse_law_xml

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ingestion"
BGB_URL = "https://www.gesetze-im-internet.de/bgb/xml.zip"


@pytest.fixture(scope="module")
def bgb():
    return parse_law_xml((FIXTURES / "bgb_excerpt.xml").read_bytes(), BGB_URL)


def test_573c_is_split_into_its_four_absaetze(bgb):
    norm = next(n for n in bgb.norms if n.paragraph == "573c")
    assert norm.enbez == "§ 573c"
    assert norm.title == "Fristen der ordentlichen Kündigung"
    assert [a[:3] for a in norm.absaetze] == ["(1)", "(2)", "(3)", "(4)"]
    assert "dritten Werktag" in norm.absaetze[0]
    assert norm.url == "https://www.gesetze-im-internet.de/bgb/__573c.html"


def test_gliederung_path_and_law_metadata(bgb):
    norm = next(n for n in bgb.norms if n.paragraph == "573c")
    assert norm.gliederung[-1].startswith("Unterkapitel 2")
    assert norm.gliederung[0].startswith("Buch 2")
    assert bgb.abbrev == "BGB"
    assert bgb.builddate is not None


def test_lists_inside_an_absatz_stay_in_that_absatz(bgb):
    norm = next(n for n in bgb.norms if n.paragraph == "556d")
    assert len(norm.absaetze) == 2
    assert "\n1. die Mieten deutlich stärker steigen" in norm.absaetze[1]
    assert norm.absaetze[1].rstrip().endswith("um Abhilfe zu schaffen.")


def test_repealed_norms_are_skipped(bgb):
    assert "10" not in {n.paragraph for n in bgb.norms}  # § 10 BGB is "(weggefallen)"


def test_table_of_contents_and_footnotes_are_skipped():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<dokumente builddate="20261116220005">
  <norm><metadaten><jurabk>BMG</jurabk><langue>Bundesmeldegesetz</langue></metadaten></norm>
  <norm><metadaten><jurabk>BMG</jurabk><enbez>Inhaltsübersicht</enbez></metadaten>
    <textdaten><text><Content><TOC><P>§ 1 Meldebehörden</P></TOC></Content></text></textdaten></norm>
  <norm><metadaten><jurabk>BMG</jurabk><enbez>§ 17</enbez><titel>Anmeldung, Abmeldung</titel></metadaten>
    <textdaten><text><Content><P>(1) Wer eine Wohnung bezieht, hat sich anzumelden.</P></Content></text>
    <fussnoten><Content><P>(+++ Editorial note +++)</P></Content></fussnoten></textdaten></norm>
</dokumente>""".encode()
    doc = parse_law_xml(xml, "https://www.gesetze-im-internet.de/bmg/xml.zip")
    assert [n.enbez for n in doc.norms] == ["§ 17"]
    assert doc.norms[0].absaetze == ["(1) Wer eine Wohnung bezieht, hat sich anzumelden."]
    assert doc.long_title == "Bundesmeldegesetz"
    assert doc.builddate == date(2026, 11, 16)


FEV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dokumente builddate="20261026220007">
  <norm><metadaten><jurabk>FeV</jurabk><langue>Fahrerlaubnis-Verordnung</langue></metadaten></norm>
  <norm><metadaten><jurabk>FeV</jurabk><enbez>§ 29</enbez><titel>Ausländische Fahrerlaubnisse</titel></metadaten>
    <textdaten><text><Content><P>(1) <SUP class="Rec">1</SUP>Die Berechtigung besteht noch sechs Monate. <SUP
      class="Rec">2</SUP>Die Frist kann verlängert werden.</P></Content></text></textdaten></norm>
  <norm><metadaten><jurabk>FeV</jurabk><enbez>Anlage 11</enbez>
    <titel>(zu § 31)<BR/>Staatenliste zu den Sonderbestimmungen</titel></metadaten>
    <textdaten><text><Content><P><table><tgroup cols="4">
      <thead><row><entry>Ausstellungsstaat</entry><entry>Klasse(n)</entry><entry>theoretische<BR/> Prüfung</entry>
        <entry>praktische Prüfung</entry></row></thead>
      <tbody>
        <row><entry>Albanien<FnR ID="x"/></entry><entry>A, B</entry><entry>nein</entry><entry>nein</entry></row>
        <row><entry/><entry>AM</entry><entry>nein</entry><entry>ja</entry></row>
        <row><entry>(weggefallen)</entry><entry/><entry/><entry/></row>
        <row><entry>Fahrerlaubnisse der Kanadischen Provinzen:</entry><entry/><entry/><entry/></row>
        <row><entry>– Ontario</entry><entry>G</entry><entry>nein</entry><entry>nein</entry></row>
      </tbody></tgroup></table></P></Content></text></textdaten></norm>
  <norm><metadaten><jurabk>FeV</jurabk><enbez>Anlage 12</enbez><titel>(zu § 34)</titel></metadaten>
    <textdaten><text><Content><P><table><tgroup cols="1"><tbody><row><entry>x</entry></row></tbody></tgroup></table>
    </P></Content></text></textdaten></norm>
</dokumente>""".encode()


def test_sentence_numbers_are_dropped_without_gluing_sentences():
    doc = parse_law_xml(FEV_XML, "https://www.gesetze-im-internet.de/fev_2010/xml.zip")
    assert doc.norms[0].absaetze == [
        "(1) Die Berechtigung besteht noch sechs Monate. Die Frist kann verlängert werden."
    ]


def test_annexes_only_when_asked_and_rows_stay_self_contained():
    url = "https://www.gesetze-im-internet.de/fev_2010/xml.zip"
    assert [n.paragraph for n in parse_law_xml(FEV_XML, url).norms] == ["29"]

    annex = parse_law_xml(FEV_XML, url, annexes=("11",)).norms[-1]
    assert annex.is_table
    assert (annex.enbez, annex.paragraph, annex.title) == (
        "Anlage 11 (zu § 31)",
        "anlage11",
        "Staatenliste zu den Sonderbestimmungen",
    )
    assert annex.url == "https://www.gesetze-im-internet.de/fev_2010/anlage_11.html"
    table = annex.absaetze[0]
    assert "| Ausstellungsstaat | Klasse(n) | theoretische Prüfung | praktische Prüfung |" in table
    assert "| Albanien | AM | nein | ja |" in table  # empty first cell filled from the row above
    assert "| Fahrerlaubnisse der Kanadischen Provinzen: Ontario | G | nein | nein |" in table  # group prefix
    assert "weggefallen" not in table


BAYERN_HTML = """<html><body><div id="content">
<div id="doc-metadata"><div>MiSchuV</div><div>Text gilt ab: 01.01.2026</div>
  <div>Gesamtvorschrift gilt bis: 31.12.2029</div></div>
<div class="cont"><h1 class="absatz titelzeile">Mieterschutzverordnung (MiSchuV)</h1></div>
<div class="cont"><div class="paraheading"><div class="absatz paranr">§ 1</div>
  <div class="absatz paratitel">Anwendungsbereich</div></div>
  <div class="absatz paratext"><sup class="satznr">1</sup>Die in der Anlage aufgeführten Gemeinden …</div></div>
<div class="cont"><div class="paraheading"></div><div class="absatz paratext">München, den 16. Dezember 2025</div></div>
<div class="cont"><div class="annexnr">Anlage (zu § 1)</div><div class="annextitel">Örtlicher Anwendungsbereich</div>
  <table><thead><tr><th>Nr.</th><th>Gemeinde</th></tr></thead>
  <tbody><tr><td>1.1.2</td><td>München</td></tr><tr><td>1.1.3</td><td>Rosenheim</td></tr></tbody></table></div>
</div></body></html>"""


def test_bayern_recht_paragraphs_annex_and_validity():
    url = "https://www.gesetze-bayern.de/Content/Document/BayMiSchuV2025/true"
    doc = parse_bayern_recht(BAYERN_HTML, url, "MiSchuV")
    assert [n.enbez for n in doc.norms] == ["§ 1", "Anlage (zu § 1)"]
    assert doc.norms[0].absaetze == ["Die in der Anlage aufgeführten Gemeinden …"]  # Satz number dropped
    assert doc.norms[0].url.endswith("BayMiSchuV2025-1")
    annex = doc.norms[1]
    assert annex.is_table and annex.paragraph == "anlage"
    assert annex.absaetze[0].splitlines()[0] == "| Nr. | Gemeinde |"
    assert "| 1.1.2 | München |" in annex.absaetze[0]
    assert (doc.valid_from, doc.valid_until) == (date(2026, 1, 1), date(2029, 12, 31))
