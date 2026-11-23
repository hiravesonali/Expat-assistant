# ruff: noqa: E501  (data file: long reference answers read better on one line)
"""Append the nationwide-topics golden questions (docs/plan-germany-wide.md, phase 3) to golden_v1.jsonl.

Health insurance, citizenship, foreign driving licence, tax ID and tax classes. Facts come from the ingested
official texts (2026-11-23: SGB V, StAG, FeV incl. Anlage 11, EStG, AO, BMG, BMI, BAMF, BMV, BZSt, OFD NRW).
Re-running is a no-op if the ids already exist.
    uv run python evals/golden/add_nationwide_v1.py
"""

import json
from pathlib import Path

GOLDEN = Path(__file__).with_name("golden_v1.jsonl")
BLUE_CARD = {"citizenship": "non_eu", "residence_status": "blue_card", "employment": "employee"}


def q(
    id, split, question, *, sources, ref, domains, category="single_domain", lang="en", profile=None, must=(), notes=""
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
        "expected_tool": None,
        "reference_answer": ref,
        "must_include": list(must),
        "must_not_include": [],
        "should_refuse": False,
        "expect_clarification": False,
        "notes": notes,
    }


B, H, X = ["bureaucracy"], ["health"], ["taxes"]
NEW = [
    # ---- Health insurance
    q(
        "hea-001",
        "dev",
        "I'm starting a job in Germany with a salary of 85,000 euros. Do I have to join public health insurance, or can I go private?",
        sources=[("sgbv#6", True), ("bmg-krankenversicherung", True), ("sgbv#9", False)],
        domains=H,
        category="numeric",
        profile=BLUE_CARD,
        must=["77,400|77.400|77 400"],
        ref="Employees earning above the annual income threshold (Jahresarbeitsentgeltgrenze, 77,400 euros in 2026) are not compulsorily insured (versicherungsfrei, § 6 (1) No. 1 SGB V), so with 85,000 euros you can choose private insurance (PKV). If it is your first job in Germany you can also join a public fund voluntarily (§ 9 (1) No. 3 SGB V); you must tell the fund within three months of starting the job.",
    ),
    q(
        "hea-002",
        "dev",
        "My wife doesn't work and we have two kids. Can they be insured through my Krankenkasse for free?",
        sources=[("sgbv#10", True), ("bmg-krankenversicherung", False)],
        domains=H,
        profile={
            "citizenship": "non_eu",
            "family_status": "married",
            "children_count": 2,
            "youngest_child_age": 4,
            "employment": "employee",
        },
        must=["Familienversicherung|family insurance"],
        ref="Yes, through family insurance (Familienversicherung, § 10 SGB V): a spouse and children who live in Germany are insured free of charge if their own income stays under the limit (603 euros a month in 2026). Children are covered up to 18, up to 23 if they are not working and up to 25 while in education.",
    ),
    q(
        "hea-003",
        "holdout",
        "How long do I have to stay with my health insurance fund before I can switch to another one?",
        sources=[("sgbv#175", True), ("bmg-krankenversicherung", False)],
        domains=H,
        category="numeric",
        must=["12 months|twelve months|zwölf Monate|12 Monate"],
        ref="You are bound to your chosen fund for at least 12 months (§ 175 (4) SGB V); after that you can cancel to the end of the second following month. If your fund raises its additional contribution (Zusatzbeitrag) you have a special right to cancel.",
    ),
    q(
        "hea-004",
        "holdout",
        "Ich bin seit Jahren privat versichert und verdiene jetzt weniger. Kann ich einfach zurück in die gesetzliche Krankenversicherung?",
        sources=[("bmg-krankenversicherung", True), ("sgbv#6", False)],
        domains=H,
        lang="de",
        ref="Nur unter Bedingungen: Fällt das Arbeitsentgelt unter die Jahresarbeitsentgeltgrenze, werden Arbeitnehmer wieder versicherungspflichtig und kommen in die GKV zurück. Ab 55 Jahren ist die Rückkehr in der Regel ausgeschlossen, wenn man in den letzten fünf Jahren nicht gesetzlich versichert war.",
    ),
    # ---- Citizenship
    q(
        "bur-026",
        "dev",
        "After how many years in Germany can I apply for German citizenship?",
        sources=[("stag#10", True), ("bmi-einbuergerung-en", False), ("bamf-einbuergerung", False)],
        domains=B,
        category="numeric",
        profile=BLUE_CARD,
        must=["five years|5 years"],
        ref="After five years of lawful habitual residence (§ 10 (1) StAG), if you also meet the other conditions: commitment to the constitution, a secure livelihood, German at level B1, the naturalisation test and no relevant criminal convictions. The former three-year fast track for special integration was abolished on 30 October 2025.",
        notes="Must not offer the abolished 3-year route (BAMF's stale English page is excluded on purpose).",
    ),
    q(
        "bur-027",
        "dev",
        "Do I have to give up my Indian passport to become a German citizen?",
        sources=[("bmi-einbuergerung", True), ("stag#10", False)],
        domains=B,
        profile={"citizenship": "non_eu"},
        ref="No. Since the citizenship reform took effect on 27 June 2024, Germany generally accepts multiple citizenship, so you do not have to give up your previous citizenship for German naturalisation. Whether India lets you keep its citizenship is decided by Indian law.",
    ),
    q(
        "bur-028",
        "holdout",
        "My husband is German. Can I get naturalised sooner than the normal five years?",
        sources=[("stag#9", True)],
        domains=B,
        category="numeric",
        profile={"citizenship": "non_eu", "family_status": "married"},
        must=["three years|3 years"],
        ref="Yes. Spouses of Germans should be naturalised after three years of lawful residence in Germany if the marriage has existed for two years (§ 9 (1) StAG); the other conditions of § 10 (1) StAG, such as German at B1 and the naturalisation test, still apply.",
    ),
    q(
        "bur-029",
        "holdout",
        "How much does naturalisation cost, and is it cheaper for my children?",
        sources=[("stag#38", True), ("bmi-einbuergerung-en", False)],
        domains=B,
        category="numeric",
        must=["255"],
        ref="The fee is 255 euros per person (§ 38 (2) StAG). For a minor child who is naturalised together with a parent and has no income of their own, it is reduced to 51 euros.",
    ),
    # ---- Foreign driving licence
    q(
        "bur-030",
        "dev",
        "I moved to Germany from India and have an Indian driving licence. How long can I keep driving with it?",
        sources=[("fev#29", True), ("bmv-fuehrerschein-en", True)],
        domains=B,
        category="numeric",
        profile={"citizenship": "non_eu"},
        must=["six months|6 months"],
        ref="A licence from a non-EU/EEA country is valid for six months after you take up your normal residence in Germany (§ 29 (1) FeV). After that you need a German licence; India is not on the list of countries whose licences convert without tests (Anlage 11 FeV), so expect a theory and a practical test.",
    ),
    q(
        "bur-031",
        "dev",
        "Do I need to take a driving test to swap my Japanese licence for a German one?",
        sources=[("fev#anlage11", True), ("fev#31", False)],
        domains=B,
        must=["Japan"],
        ref="Normally no. Japan is listed in Anlage 11 FeV for all classes with no theory and no practical test, so the licence is converted without tests (§ 31 (1) FeV). Only if facts suggest you no longer have the necessary knowledge and skills can the office order a test (§ 31 (1a) FeV). Apply at your local driving licence office (Fahrerlaubnisbehörde).",
        notes="Answerable only from the Anlage 11 table (law_xml include_annexes). Reference extended with § 31 (1a) after the 2026-11-23 run: an answer naming that exception is correct.",
    ),
    q(
        "bur-032",
        "holdout",
        "I'm only in Germany for a 10-month project. Do I have to convert my US licence?",
        sources=[("fev#29", True), ("bmv-fuehrerschein-en", False)],
        domains=B,
        must=["12 months|twelve months"],
        ref="Probably not. The licence is valid for six months after you take up residence, and the driving licence office can extend this by up to six more months on application if you show that you will not live in Germany for longer than 12 months (§ 29 (1) FeV). Apply for the extension before the six months run out.",
    ),
    # ---- Tax ID and tax classes
    q(
        "tax-001",
        "dev",
        "I registered my address two weeks ago. How do I get my tax ID?",
        sources=[("bzst-steuer-id", True), ("ao#139a", False)],
        domains=X,
        must=["three months|3 months"],
        ref="You don't apply for it: the Federal Central Tax Office (BZSt) sends your tax identification number (Steuer-ID) by post as soon as the registration office has passed on your data. If nothing has arrived after three months, send the BZSt your personal data and it will contact the registration office.",
    ),
    q(
        "tax-002",
        "dev",
        "We just got married. Which tax classes do we get, and should we pick III/V?",
        sources=[("estg#39e", True), ("estg#38b", True), ("fa-nrw-steuerklassen", False)],
        domains=X,
        profile={"family_status": "married", "employment": "employee"},
        must=["IV|class 4|Steuerklasse 4"],
        ref="On marriage both spouses automatically get tax class IV (§ 39e (3) EStG). On a joint application you can choose III/V instead (§ 38b EStG): it lowers the monthly wage tax of the higher earner and suits couples with very different incomes. IV/IV with a factor (Faktorverfahren, § 39f EStG) is the alternative.",
    ),
    q(
        "tax-003",
        "holdout",
        "Was ist das Faktorverfahren bei den Steuerklassen?",
        sources=[("estg#39f", True), ("fa-nrw-steuerklassen", False)],
        domains=X,
        lang="de",
        must=["IV|class 4|Steuerklasse 4"],
        ref="Ehegatten können statt III/V die Steuerklassen IV/IV mit Faktor wählen (§ 39f EStG): Das Finanzamt berechnet einen Faktor kleiner als 1, mit dem die Lohnsteuer jedes Ehegatten so gemindert wird, dass sie der voraussichtlichen gemeinsamen Jahressteuer nahekommt. Dafür ist ein gemeinsamer Antrag beim Finanzamt nötig.",
    ),
]

if __name__ == "__main__":
    existing = {json.loads(line)["id"] for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()}
    new = [e for e in NEW if e["id"] not in existing]
    with GOLDEN.open("a", encoding="utf-8", newline="\n") as f:  # LF on Windows too
        for example in new:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    print(f"appended {len(new)} of {len(NEW)} examples to {GOLDEN.name}")
