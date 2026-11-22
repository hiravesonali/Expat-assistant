"""law_pdf: state regulations from gazette PDFs (built here with pymupdf, so the test needs no fixture file)."""

from datetime import date

import pymupdf
import pytest

from expat.ingestion.parsers.law_pdf import parse_law_pdf

GAZETTE = """Wiesbaden, den 19. November 2026
Nr. 78
Verordnung zur Bestimmung des Geltungsbereichs
Auf Grund des § 556d Abs. 2 des Bürgerlichen Gesetzbuches wird verordnet:
§ 1
Gebietsbestimmung
(1) Gebiete mit angespanntem Wohnungsmarkt sind die in Anlage 1 genannten Gemeinden.
(2) Die Mietpreisbremse gilt nach § 556d Abs. 1 des Bürgerlichen Gesetzbuches.
§ 2
Die Mieterschutzverordnung vom 18. November 2020 wird aufgehoben.
§ 3
Inkrafttreten
Diese Verordnung tritt am Tag nach der Verkündung in Kraft.
Seite 2 von 9
Anlage 1 (zu § 1)
1.
Darmstadt
2.
Frankfurt am Main
A.
Begründung:
Lange Begründung, die nicht zum Normtext gehört. § 9 wird hier nur erwähnt.
"""


def _pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 40
    for line in text.splitlines():
        page.insert_text((40, y), line, fontsize=9)
        y += 13
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(scope="module")
def law():
    return parse_law_pdf(_pdf(GAZETTE), "https://example.org/gvbl.pdf", "MiSchuV HE", valid_until=date(2029, 12, 31))


def test_norms_titles_and_absaetze(law):
    assert [n.enbez for n in law.norms] == ["§ 1", "§ 2", "§ 3", "Anlage 1"]
    first = law.norms[0]
    assert first.title == "Gebietsbestimmung" and len(first.absaetze) == 2
    assert first.absaetze[0].startswith("(1) Gebiete mit angespanntem Wohnungsmarkt")


def test_one_sentence_norm_is_text_not_title(law):
    """§ 2 has no title line: its only sentence must stay the norm text (it was dropped once)."""
    assert law.norms[1].title == "" and "wird aufgehoben" in law.norms[1].absaetze[0]


def test_page_footer_and_explanatory_memorandum_are_excluded(law):
    text = "\n".join(a for n in law.norms for a in n.absaetze)
    assert "Seite 2 von 9" not in text and "Begründung" not in text and "§ 9" not in text
    assert law.norms[2].absaetze == ["Diese Verordnung tritt am Tag nach der Verkündung in Kraft."]


def test_annex_list_joins_numbers_with_names(law):
    annex = law.norms[-1]
    assert annex.paragraph == "anlage" and annex.title == "zu § 1"
    assert annex.absaetze == ["1. Darmstadt\n2. Frankfurt am Main"]


def test_start_marker_cuts_one_law_out_of_a_gazette_issue():
    issue = "Inhalt\nAndere Verordnung\n§ 1\nAnderes\nText der anderen Verordnung.\n" + GAZETTE.split("Nr. 78\n")[1]
    law = parse_law_pdf(_pdf(issue), "u", "X", start=r"^Verordnung zur Bestimmung")
    assert law.norms[0].absaetze[0].startswith("(1) Gebiete mit angespanntem")
    with pytest.raises(ValueError, match="start marker"):
        parse_law_pdf(_pdf(issue), "u", "X", start=r"^Gibt es nicht")
