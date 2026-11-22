"""HTML parser against SYNTHETIC pages that mimic the real templates (no scraped content committed)."""

from pathlib import Path

from expat.ingestion.documents import BlockKind
from expat.ingestion.parsers.html import parse_html

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ingestion"


def _parse(name: str, url: str):
    return parse_html((FIXTURES / name).read_text(encoding="utf-8"), url)


def test_munich_sections_and_noise_removal():
    doc = _parse("muc_procedure.html", "https://stadt.muenchen.de/service/info/test/1/")
    assert doc.title == "Testanmeldung"
    headings = [s.heading for s in doc.sections]
    assert headings == [
        "",  # intro paragraph before the first H2
        "Beschreibung",
        "Voraussetzungen",
        "Benötigte Unterlagen",
        "Dauer und Kosten",
        "Fragen und Antworten",
        "Rechtliche Grundlagen",
    ]
    all_text = " ".join(b.text for s in doc.sections for b in s.blocks)
    for noise in ("Seiteninhalt", "Kontaktformular", "Termin vereinbaren", "Online beantragen", "Vorlesen"):
        assert noise not in all_text


def test_munich_accordion_becomes_faq_pairs():
    doc = _parse("muc_procedure.html", "https://stadt.muenchen.de/service/info/test/1/")
    faq = next(s for s in doc.sections if s.heading == "Fragen und Antworten")
    assert [b.kind for b in faq.blocks] == [BlockKind.FAQ, BlockKind.FAQ]
    assert faq.blocks[0].question == "Muss ich mich bei einem Umzug im gleichen Haus ummelden?"
    assert faq.blocks[0].text == "Ja, auch ein Umzug innerhalb des Hauses muss gemeldet werden."


def test_table_is_one_intact_markdown_block():
    doc = _parse("muc_procedure.html", "https://stadt.muenchen.de/service/info/test/1/")
    costs = next(s for s in doc.sections if s.heading == "Dauer und Kosten")
    assert [b.kind for b in costs.blocks] == [BlockKind.HEADING, BlockKind.TABLE]
    assert costs.blocks[1].text.splitlines() == [
        "| Leistung | Gebühr |",
        "|---|---|",
        "| Anmeldung | kostenfrei |",
        "| Adressänderung Fahrzeugpapiere | 12,60 Euro |",
    ]


def test_lists_are_kept_intact_with_their_items():
    doc = _parse("muc_procedure.html", "https://stadt.muenchen.de/service/info/test/1/")
    docs = next(s for s in doc.sections if s.heading == "Benötigte Unterlagen")
    lists = [b for b in docs.blocks if b.kind == BlockKind.LIST]
    assert len(lists) == 1
    assert lists[0].text.count("\n- ") == 2  # three items in one block


def test_bayernportal_uses_h3_sections_and_drops_widgets():
    doc = _parse("bayernportal_procedure.html", "https://www.bayernportal.de/dokumente/leistung/1")
    assert doc.title == "Testkarte; Beantragung"
    assert [s.heading for s in doc.sections] == [
        "Beschreibung",
        "Voraussetzung",
        "Erforderliche Unterlagen",
        "Kosten",
        "Fristen",
        "Rechtsgrundlagen",
    ]
    unterlagen = doc.sections[2].blocks[0].text
    assert "(ID:" not in unterlagen and "Reisepass" in unterlagen
    assert doc.stand == "Stand: 18.09.2026"


def test_familienportal_title_subheadings_and_table():
    doc = _parse("fp_guide.html", "https://familienportal.de/familienportal/x")
    assert doc.title == "Wie viel Testgeld kann ich bekommen?"
    hoehe = next(s for s in doc.sections if s.heading == "Höhe des Testgeldes")
    assert [b.kind for b in hoehe.blocks] == [BlockKind.TEXT, BlockKind.TABLE, BlockKind.HEADING, BlockKind.TEXT]


def test_rundfunkbeitrag_faq_headings_and_back_links():
    doc = _parse("rb_faq.html", "https://www.rundfunkbeitrag.de/welcome/english/students-and-apprentices")
    assert [s.heading for s in doc.sections] == [
        "I live in a shared flat. Who pays?",
        "I live in a student hall of residence. Do I have to pay?",
    ]
    assert all("back to" not in b.text for s in doc.sections for b in s.blocks)


STUTTGART_PAGE = """<html><body><main><div class="SP-ArticleContent">
<h1 class="SP-Headline--article">Wohnsitz anmelden</h1>
<p>Sie müssen sich innerhalb von zwei Wochen anmelden.</p>
<section class="SP-Collapsible"><h2 class="SP-Collapsible__trigger">Benötigte Unterlagen</h2>
<div class="SP-Collapsible__content" aria-hidden="true" style="display:none"><p>Personalausweis und
Wohnungsgeberbestätigung.</p></div></section>
<div class="visually-hidden" aria-hidden="true"><p>Screenreader-Hinweis</p></div>
</div></main></body></html>"""


def test_stuttgart_collapsed_sections_are_unhidden_but_other_hidden_text_is_still_dropped():
    """stuttgart.de marks every accordion body aria-hidden in the server HTML (70-90 % of the text)."""
    doc = parse_html(STUTTGART_PAGE, "https://www.stuttgart.de/organigramm/leistungen/wohnsitz-anmelden")
    sections = {s.heading: " ".join(b.text for b in s.blocks) for s in doc.sections}
    assert "Wohnungsgeberbestätigung" in sections["Benötigte Unterlagen"]
    assert "Screenreader" not in " ".join(sections.values())


def test_welcome_stuttgart_demotes_accordion_triggers_below_the_permit_heading():
    page = """<html><body><div class="SP-ArticleContent"><h1 class="SP-Headline--article">Niederlassungserlaubnis</h1>
    <section class="SP-Section"><h2>Niederlassungserlaubnis für Fachkräfte</h2>
    <section class="SP-Collapsible"><div class="SP-Collapsible__trigger"><h2 class="SP-Collapsible__trigger__text">
    Voraussetzung</h2></div><div class="SP-Collapsible__content" aria-hidden="true"><p>Drei Jahre Aufenthalt.</p>
    </div></section></section></div></body></html>"""
    doc = parse_html(page, "https://welcome.stuttgart.de/einreise/niederlassungserlaubnis")
    assert [s.heading for s in doc.sections] == ["Niederlassungserlaubnis für Fachkräfte"]
    assert "Drei Jahre Aufenthalt" in " ".join(b.text for b in doc.sections[0].blocks)
