# ruff: noqa: E501  (data file: long reference answers read better on one line)
"""Append the Germany-wide golden questions (docs/plan-germany-wide.md, phase 4) to golden_v1.jsonl.

Facts come from the ingested official pages (2026-11-22). Re-running is a no-op if the ids already exist.
    uv run python evals/golden/add_germany_v1.py
"""

import json
from pathlib import Path

GOLDEN = Path(__file__).with_name("golden_v1.jsonl")
TWO_WEEKS = "two weeks|2 weeks|zwei Wochen|14 days|14 Tage"
NON_EU_RENTER = {
    "citizenship": "non_eu",
    "residence_status": "blue_card",
    "employment": "employee",
    "housing": "renting",
}
FAMILY = {"citizenship": "non_eu", "family_status": "married", "children_count": 1, "youngest_child_age": 1}


def q(
    id,
    split,
    question,
    *,
    sources,
    ref,
    domains,
    category="single_domain",
    lang="en",
    profile=None,
    must=(),
    tool=None,
    clarify=False,
    notes="",
):
    return {
        "id": id,
        "split": split,
        "question": question,
        "language": lang,
        "profile": profile or {},
        "domains": domains,
        "category": category,
        "expected_sources": [{"doc_key": k, "required": r} for k, r in sources],
        "expected_tool": tool,
        "reference_answer": ref,
        "must_include": list(must),
        "must_not_include": [],
        "should_refuse": False,
        "expect_clarification": clarify,
        "notes": notes,
    }


B, T, F = ["bureaucracy"], ["tenancy"], ["family"]
NEW = [
    # ---- Berlin
    q(
        "bur-012",
        "dev",
        "I just moved to Berlin. Which documents do I need to register my address?",
        sources=[("ber-anmeldung", True), ("bmg#17", False)],
        domains=B,
        must=["Wohnungsgeber"],
        ref="Register at a Bürgeramt (online with an eID or on site with the registration form): an ID card or passport "
        "(for foreign nationals the national passport, with the residence permit/eAT if you have one) and the "
        "landlord's confirmation (Wohnungsgeberbestätigung). You must register within two weeks (§ 17 BMG).",
        notes="City named in the question, empty profile.",
    ),
    q(
        "bur-013",
        "holdout",
        "How much does an EU Blue Card cost at the Berlin immigration office (LEA)?",
        sources=[("ber-lea-blaue-karte", True)],
        domains=B,
        category="numeric",
        must=["100"],
        ref="At the LEA Berlin: 100 euros for the first Blue Card as an electronic residence permit (93 euros for a "
        "renewal); 56 / 49 euros if issued as a label.",
    ),
    q(
        "ten-012",
        "dev",
        "Does the rent cap (Mietpreisbremse) apply in Berlin, and until when?",
        sources=[("be-mietpreisbremse", True)],
        domains=T,
        category="legal_lookup",
        must=["2029"],
        ref="Yes. The Berlin Mietenbegrenzungsverordnung declares the whole city a tight housing market (§ 556d (2) BGB), "
        "so the rent at the start of a lease may be at most 10% above the local comparative rent. It applies from "
        "1 January 2026 until 31 December 2029.",
    ),
    q(
        "fam-010",
        "dev",
        "How do I get a Kita place for my daughter in Berlin?",
        sources=[("ber-kita", True)],
        domains=F,
        profile=FAMILY,
        must=["Gutschein|voucher"],
        ref="You need a Kita-Gutschein (daycare voucher) from the youth office (Jugendamt). It sets how many hours your "
        "child may be cared for (depending on age, among other things) and you redeem it at any publicly funded "
        "Berlin Kita or childminder with a free place.",
    ),
    # ---- Hamburg
    q(
        "bur-020",
        "dev",
        "I moved to Hamburg from abroad. Do I need to register, and by when?",
        sources=[("ham-anmeldung", True), ("bmg#17", False)],
        domains=B,
        must=[TWO_WEEKS],
        ref="Yes, if you plan to stay in Hamburg longer than 3 months you must register with the responsible office; your "
        "address is entered in the population register and you get an official registration certificate "
        "(Meldebestätigung). The deadline is two weeks after moving in (§ 17 BMG).",
    ),
    q(
        "bur-021",
        "holdout",
        "Where do I apply for my Blue Card in Hamburg?",
        sources=[("ham-welcome-blaue-karte", True), ("ham-blaue-karte", False)],
        domains=B,
        profile=NON_EU_RENTER,
        must=["Welcome Center"],
        ref="At the Hamburg Welcome Center (Amt für Migration). If you meet the requirements you are entitled to an EU "
        "Blue Card under § 18g AufenthG.",
    ),
    q(
        "fam-011",
        "holdout",
        "When should I apply for the Kita-Gutschein in Hamburg?",
        sources=[("ham-kita", True)],
        domains=F,
        profile=FAMILY,
        must=["three|3"],
        ref="Three to six months before the desired start of care (at least six months ahead for a voucher with "
        "integration assistance). You can apply online.",
    ),
    q(
        "ten-016",
        "dev",
        "Is there a rent cap in Hamburg?",
        sources=[("hh-mietpreisbremse-info", True), ("hh-mietpreisbremse", False)],
        domains=T,
        category="legal_lookup",
        must=["2029"],
        ref="Yes. Hamburg's Mietpreisbegrenzungsverordnung covers the whole city; the current regulation applies until "
        "31 December 2029. New rents may be at most 10% above the local comparative rent (Mietenspiegel), with "
        "exceptions e.g. for new builds and comprehensive modernisation.",
    ),
    # ---- Frankfurt am Main
    q(
        "bur-019",
        "holdout",
        "What salary do I need for a Blue Card in Frankfurt if I work in a shortage occupation?",
        sources=[("fra-auslaenderbehoerde-blaue-karte", True), ("bamf-blue-card", False)],
        domains=B,
        category="numeric",
        must=["3.827|3,827"],
        ref="In a shortage occupation at least 3,827.85 euros gross per month (current threshold stated by the Frankfurt "
        "foreign office); you need a university degree and a job that matches it.",
    ),
    q(
        "bur-022",
        "dev",
        "When can I get a settlement permit with my Blue Card in Frankfurt?",
        sources=[("fra-auslaenderbehoerde-niederlassung", True), ("aufenthg#18c", False), ("bamf-settlement", False)],
        domains=B,
        profile=NON_EU_RENTER,
        ref="A settlement permit (Niederlassungserlaubnis) is an unlimited residence permit. Blue Card holders can get it "
        "after 27 months of qualified work with pension contributions, or after 21 months with German at B1 level "
        "(§ 18c (2) AufenthG); you apply online with the Frankfurt foreign office.",
    ),
    q(
        "fam-012",
        "dev",
        "How do I register my child for a daycare place in Frankfurt?",
        sources=[("fra-kita", True)],
        domains=F,
        profile=FAMILY,
        must=["kindernet"],
        ref="Register on kindernetfrankfurt.de with an email address, then create reservations (Vormerkungen) for the "
        "places you want online; you are notified by email when a place is offered.",
    ),
    q(
        "ten-013",
        "holdout",
        "Is Frankfurt am Main covered by the rent cap?",
        sources=[("he-mietpreisbremse", True)],
        domains=T,
        category="legal_lookup",
        must=["10"],
        ref="Yes. Frankfurt am Main is listed in Annex 1 of the Hessian Mieterschutzverordnung of 17 November 2026: the "
        "rent at the start of a lease may be at most 10% above the local comparative rent (until 31 December 2029); "
        "the cap on rent increases is 15%.",
    ),
    q(
        "ten-017",
        "holdout",
        "What is the Frankfurt Mietspiegel and what is it used for?",
        sources=[("fra-mietspiegel", True)],
        domains=T,
        ref="The Frankfurt Mietspiegel 2026 is the city's qualified rent index. It shows the local comparative rent "
        "(ortsübliche Vergleichsmiete), which matters for rent increases and for the rent cap at the start of a "
        "lease.",
    ),
    # ---- Köln / Cologne
    q(
        "bur-014",
        "dev",
        "Do I have to pay a fee to register my address in Köln?",
        sources=[("cgn-anmeldung", True)],
        domains=B,
        must=["free|no fee|gebührenfrei|kostenlos|no charge|not charge"],
        ref="No, registering your address in Cologne is free of charge.",
    ),
    q(
        "bur-015",
        "holdout",
        "We moved to Cologne. What do I need to bring for the Anmeldung as a non-EU citizen renting a flat?",
        sources=[("cgn-anmeldung", True)],
        domains=B,
        profile=NON_EU_RENTER,
        must=["Wohnungsgeber"],
        ref="Your national passport and residence documents (e.g. electronic residence permit), and the landlord's "
        "confirmation of moving in (Wohnungsgeberbescheinigung) - a rental contract is not enough.",
    ),
    q(
        "bur-016",
        "dev",
        "Wie viel kostet die Blaue Karte EU bei der Ausländerbehörde Köln?",
        sources=[("cgn-auslaenderbehoerde-blaue-karte", True)],
        domains=B,
        category="numeric",
        lang="de",
        must=["100", "93"],
        ref="Ersterteilung 100 Euro, Verlängerung 93 Euro.",
    ),
    q(
        "fam-013",
        "holdout",
        "Wie finde ich in Köln einen Kitaplatz?",
        sources=[("cgn-kita", True)],
        domains=F,
        lang="de",
        profile=FAMILY,
        must=["LITTLE BIRD|Little Bird|little bird"],
        ref="Über das Online-Portal LITTLE BIRD: dort sind alle städtischen und über 400 freie Kitas hinterlegt; nach der "
        "Registrierung im Elternportal können Sie Ihr Kind bei Ihren bevorzugten Einrichtungen vormerken.",
    ),
    q(
        "ten-014",
        "dev",
        "Gilt die Mietpreisbremse in Köln?",
        sources=[("nw-mietpreisbremse-anlage", True), ("nw-mietpreisbremse", False)],
        domains=T,
        category="legal_lookup",
        lang="de",
        ref="Ja. Köln steht in der Anlage der Mieterschutzverordnung NRW; dort gilt die Mietpreisbremse (Miete bei "
        "Mietbeginn höchstens 10 % über der ortsüblichen Vergleichsmiete), befristet bis 31.12.2029.",
    ),
    # ---- Stuttgart
    q(
        "bur-017",
        "holdout",
        "I'm moving to Stuttgart next month. By when do I have to register and what do I need?",
        sources=[("str-anmeldung", True), ("bmg#17", False)],
        domains=B,
        must=[TWO_WEEKS],
        ref="Within two weeks of moving in. Bring your ID card or passport (and those of family members; birth "
        "certificates for children without ID), the landlord's confirmation (Wohnungsgeberbestätigung) and your "
        "electronic residence permit if you have one.",
    ),
    q(
        "bur-018",
        "dev",
        "How much is the first Blue Card at the Stuttgart foreign office?",
        sources=[("str-auslaenderbehoerde-blaue-karte", True)],
        domains=B,
        category="numeric",
        must=["100"],
        ref="100 euros for the first issue (93 euros for an extension of more than 3 months); half for minors.",
    ),
    q(
        "fam-014",
        "dev",
        "How do I request a daycare place in Stuttgart?",
        sources=[("str-kita", True)],
        domains=F,
        profile=FAMILY,
        must=["Elternkonto|parent account|parents' account"],
        ref="Via the Kita-Portal (stuttgart.de/kitafinder): create a parent account (Elternkonto), add your child and send "
        "a care request (Betreuungsplatz-Anfrage) to the specific facility, stating up to 7 hours or more per day.",
    ),
    q(
        "ten-015",
        "holdout",
        "Does the rent cap apply in Stuttgart?",
        sources=[("bw-mietpreisbremse-info", True)],
        domains=T,
        category="legal_lookup",
        must=["2026"],
        ref="Yes. Stuttgart is part of Baden-Württemberg's list of 130 municipalities with a tight housing market; the "
        "current regulation applies until 31 December 2026 and a successor regulation covers 2027-2029.",
    ),
    # ---- Cross-city
    q(
        "mul-005",
        "holdout",
        "I'm moving from Berlin to Hamburg next month. Do I have to deregister in Berlin first?",
        sources=[("bmg#17", True)],
        domains=B,
        must=[TWO_WEEKS],
        ref="No. When you move within Germany you only register at the new address in Hamburg within two weeks; "
        "deregistration (Abmeldung) is only needed when you move abroad or give up a flat without a new one in "
        "Germany (§ 17 BMG).",
        notes="Two cities named: both allowed, no other city.",
    ),
    q(
        "mul-006",
        "dev",
        "I'm relocating from Munich to Stuttgart for a new job. What do I need to register in Stuttgart?",
        sources=[("str-anmeldung", True)],
        domains=B,
        profile={"city": "munich", **NON_EU_RENTER},
        must=["Wohnungsgeber"],
        ref="Register in Stuttgart within two weeks with your passport, electronic residence permit and the landlord's "
        "confirmation (Wohnungsgeberbestätigung).",
        notes="The question's city (Stuttgart) must override the profile city (Munich).",
    ),
    # ---- Follow-up question expected (location-dependent, no city anywhere)
    q(
        "bur-023",
        "dev",
        "Where do I book an appointment to register my address?",
        sources=[],
        domains=B,
        clarify=True,
        ref="Ask which city the user lives in (appointments are booked with the local citizens' office).",
    ),
    q(
        "fam-015",
        "holdout",
        "How do I apply for a Kita voucher?",
        sources=[],
        domains=F,
        profile=FAMILY,
        clarify=True,
        ref="Ask which city the user lives in (Kita registration differs by city).",
    ),
    q(
        "ten-018",
        "dev",
        "Does the rent cap apply where I live?",
        sources=[],
        domains=T,
        clarify=True,
        ref="Ask which city the user lives in (the rent cap is set per state and municipality).",
    ),
    q(
        "bur-024",
        "holdout",
        "Which foreign office handles my Blue Card application and how do I book an appointment?",
        sources=[],
        domains=B,
        profile={"citizenship": "non_eu", "residence_status": "blue_card"},
        clarify=True,
        ref="Ask which city the user lives in (the local Ausländerbehörde is responsible).",
    ),
    # ---- No follow-up expected: federal rules, or a named (unsupported) city
    q(
        "ten-019",
        "dev",
        "As a tenant, how much notice do I have to give to end my lease?",
        sources=[("bgb#573c", True)],
        domains=T,
        category="legal_lookup",
        must=["three months|3 months|drei Monate"],
        ref="Three months (§ 573c (1) BGB); the notice must reach the landlord by the third working day of a month.",
        notes="Empty profile: federal rule, must NOT ask for the city.",
    ),
    q(
        "fam-016",
        "holdout",
        "How much Kindergeld do I get per child?",
        sources=[("estg#66", True), ("fp-kindergeld", False)],
        domains=F,
        category="numeric",
        must=["259"],
        ref="259 euros per month for each child (§ 66 EStG).",
        notes="Empty profile: federal, must NOT ask.",
    ),
    q(
        "bur-025",
        "dev",
        "I live in Leipzig. By when do I have to register my new address?",
        sources=[("bmg#17", True)],
        domains=B,
        must=[TWO_WEEKS],
        ref="Within two weeks of moving in (§ 17 BMG), at the Leipzig citizens' office; I have no Leipzig-specific sources.",
        notes="Unsupported city: must not ask again and must not use another city's pages.",
    ),
]

if __name__ == "__main__":
    existing = {json.loads(line)["id"] for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()}
    new = [e for e in NEW if e["id"] not in existing]
    with GOLDEN.open("a", encoding="utf-8") as f:
        for example in new:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    print(f"appended {len(new)} of {len(NEW)} examples to {GOLDEN.name}")
