"""Sensitive / out-of-scope policy (rag-pipeline.md "Safety and trust").

Two layers decide that a question must NOT get a normal RAG answer:
1. `precheck()`: a cheap, deterministic keyword match that runs BEFORE any LLM call. It catches the
   clearest cases (asylum, deportation, Duldung, eviction lawsuits, violence, self-harm) even if
   the analysis model misclassifies them or is down, and it costs nothing.
2. The LLM intent from query analysis (`sensitive` / `out_of_scope` / `chitchat`), which catches
   paraphrases the keywords miss.

Either way the answer is a short, fixed template with referrals, never generated text: for these
topics a wrong answer can cause real harm, and a template is reviewable and testable.
"""

import re
from enum import StrEnum
from typing import Literal

Language = Literal["en", "de"]


class SafetyCategory(StrEnum):
    EMERGENCY = "emergency"  # violence or self-harm: emergency numbers first
    RESIDENCE_RISK = "residence_risk"  # asylum, deportation, Duldung, obligation to leave
    LEGAL_DISPUTE = "legal_dispute"  # court case with deadlines, e.g. eviction lawsuit
    SENSITIVE = "sensitive"  # flagged by the LLM intent without a more specific keyword
    OUT_OF_SCOPE = "out_of_scope"
    CHITCHAT = "chitchat"


# Order matters: the first matching category wins, so emergencies are checked first.
# Patterns are matched case-insensitively against the whole question. `\b` at the start only,
# so German compounds ("Abschiebungsandrohung", "Räumungsklagen") still match.
_KEYWORDS: list[tuple[SafetyCategory, re.Pattern[str]]] = [
    (
        SafetyCategory.EMERGENCY,
        re.compile(
            r"\b(violence|violent|abus(e|ive)|beats? me|hits? me|threatens? to (kill|hurt)|"
            r"gewalt|schlägt mich|misshandl|bedroht mich|"
            r"suicid|kill myself|selbstmord|suizid|umbringen)",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.RESIDENCE_RISK,
        re.compile(
            r"\b(asyl|asylum|refugee status|abschieb|deport|duldung|tolerated stay|"
            r"ausreisepflicht|obliged to leave germany|leave germany within)",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.LEGAL_DISPUTE,
        re.compile(
            r"\b(räumungsklage|zwangsräumung|eviction (lawsuit|suit|notice from (the )?court)|"
            r"court[- ]ordered eviction|bailiff|gerichtsvollzieher|sued me|verklagt)",
            re.IGNORECASE,
        ),
    ),
]


def precheck(question: str) -> SafetyCategory | None:
    """Return the first sensitive category whose keywords occur in the question, else None.

    Deliberately narrow: "eviction" alone is NOT matched, because ordinary notice-period
    questions about a landlord's termination are in scope; only court/lawsuit wording is.
    """
    for category, pattern in _KEYWORDS:
        if pattern.search(question):
            return category
    return None


_DISCLAIMER = {
    "en": "_General information, not legal advice._",
    "de": "_Allgemeine Information, keine Rechtsberatung._",
}

_EMERGENCY_LINES = {
    "en": (
        "- **In immediate danger:** call the police **110** or emergency services **112** (free, 24/7).\n"
        '- **Violence against women** helpline "Gewalt gegen Frauen": **116 016** (free, anonymous, 24/7, '
        "many languages) – https://www.hilfetelefon.de\n"
        "- **Crisis / suicidal thoughts:** TelefonSeelsorge **0800 111 0 111** or **0800 111 0 222** (free, 24/7)."
    ),
    "de": (
        "- **Bei akuter Gefahr:** Polizei **110** oder Notruf **112** (kostenlos, rund um die Uhr).\n"
        '- **Hilfetelefon "Gewalt gegen Frauen":** **116 016** (kostenlos, anonym, rund um die Uhr, '
        "viele Sprachen) – https://www.hilfetelefon.de\n"
        "- **In einer Krise / bei Suizidgedanken:** TelefonSeelsorge **0800 111 0 111** oder **0800 111 0 222**."
    ),
}

_MBE = {
    "en": "- **Migration counselling for adults (Migrationsberatung für Erwachsene, MBE)**: free and "
    "confidential; find an office near you with BAMF-NAvI – https://bamf-navi.bamf.de",
    "de": "- **Migrationsberatung für Erwachsene (MBE)**: kostenlos und vertraulich; Beratungsstellen "
    "in Ihrer Nähe über BAMF-NAvI – https://bamf-navi.bamf.de",
}
_LAWYER = {
    "en": "- **A lawyer (Rechtsanwalt)** specialised in the topic – search: https://anwaltauskunft.de "
    "(low-income? ask the local court about legal-aid vouchers, Beratungshilfe)",
    "de": "- **Eine Rechtsanwältin / ein Rechtsanwalt** mit passendem Fachgebiet – Suche: https://anwaltauskunft.de "
    "(geringes Einkommen? Beratungshilfeschein beim Amtsgericht)",
}
_MIETERVEREIN = {
    "en": "- **Mieterverein München** (tenants' association, legal advice for members) – https://www.mieterverein-muenchen.de",
    "de": "- **Mieterverein München** (Rechtsberatung für Mitglieder) – https://www.mieterverein-muenchen.de",
}
_REFUGEE_COUNCIL = {
    "en": "- **Bayerischer Flüchtlingsrat** (refugee council Bavaria) – https://www.fluechtlingsrat-bayern.de",
    "de": "- **Bayerischer Flüchtlingsrat** – https://www.fluechtlingsrat-bayern.de",
}

_INTRO = {
    SafetyCategory.EMERGENCY: {
        "en": "I'm sorry you're going through this. Your safety comes first, and these services can help right now:",
        "de": "Es tut mir leid, dass Sie das erleben. Ihre Sicherheit geht vor – hier bekommen Sie sofort Hilfe:",
    },
    SafetyCategory.RESIDENCE_RISK: {
        "en": "Questions about asylum, deportation or a Duldung depend on your individual case and often have "
        "short legal deadlines. I can't give reliable advice on this, but these free services can:",
        "de": "Fragen zu Asyl, Abschiebung oder Duldung hängen vom Einzelfall ab und haben oft kurze Fristen. "
        "Dazu kann ich nicht verlässlich beraten, aber diese kostenlosen Stellen können es:",
    },
    SafetyCategory.LEGAL_DISPUTE: {
        "en": "A court case (for example an eviction lawsuit, Räumungsklage) has strict deadlines, so please get "
        "professional help quickly. I can't advise on an ongoing dispute, but these can:",
        "de": "Ein Gerichtsverfahren (z. B. eine Räumungsklage) hat strenge Fristen – bitte holen Sie schnell "
        "professionelle Hilfe. Zu einem laufenden Streit kann ich nicht beraten, aber diese Stellen schon:",
    },
    SafetyCategory.SENSITIVE: {
        "en": "This sounds like a situation that needs individual, professional advice. I can't give reliable "
        "advice on it, but these services can help:",
        "de": "Das klingt nach einer Situation, die eine individuelle, professionelle Beratung braucht. Dazu kann "
        "ich nicht verlässlich beraten, aber diese Stellen helfen:",
    },
}

_REFERRALS = {
    SafetyCategory.EMERGENCY: [_EMERGENCY_LINES, _MBE],
    SafetyCategory.RESIDENCE_RISK: [_MBE, _REFUGEE_COUNCIL, _LAWYER],
    SafetyCategory.LEGAL_DISPUTE: [_MIETERVEREIN, _LAWYER, _MBE],
    SafetyCategory.SENSITIVE: [_MBE, _LAWYER, _MIETERVEREIN],
}

_OUT_OF_SCOPE = {
    "en": "Sorry, that's outside what I can help with. I answer questions about living in Germany as an expat, "
    "focused on Munich:\n\n"
    "- **Bureaucracy:** address registration (Anmeldung), residence permits and the EU Blue Card, "
    "broadcasting fee (Rundfunkbeitrag)\n"
    "- **Tenancy:** leases, notice periods (Kündigungsfrist), rent increases\n"
    "- **Family:** child benefit (Kindergeld), parental allowance (Elterngeld), daycare (Kita)",
    "de": "Dabei kann ich leider nicht helfen. Ich beantworte Fragen zum Leben in Deutschland als Expat, "
    "mit Fokus auf München:\n\n"
    "- **Behörden:** Wohnsitzanmeldung, Aufenthaltstitel und Blaue Karte EU, Rundfunkbeitrag\n"
    "- **Mieten:** Mietvertrag, Kündigungsfristen, Mieterhöhungen\n"
    "- **Familie:** Kindergeld, Elterngeld, Kita",
}

_CHITCHAT = {
    "en": "You're welcome! Ask me anything about registration, residence permits, renting or family benefits "
    "in Germany.",
    "de": "Gern geschehen! Fragen Sie mich gern zu Anmeldung, Aufenthaltstitel, Mieten oder Familienleistungen.",
}


def safety_response(category: SafetyCategory, language: str = "en") -> str:
    """The fixed Markdown reply for a category, in English or German (anything else -> English)."""
    lang: Language = "de" if language == "de" else "en"
    if category is SafetyCategory.OUT_OF_SCOPE:
        return _OUT_OF_SCOPE[lang]
    if category is SafetyCategory.CHITCHAT:
        return _CHITCHAT[lang]
    referrals = "\n".join(block[lang] for block in _REFERRALS[category])
    return f"{_INTRO[category][lang]}\n\n{referrals}\n\n{_DISCLAIMER[lang]}"


def category_for_intent(intent: str) -> SafetyCategory | None:
    """Map a QueryAnalysis intent to the policy category that short-circuits the pipeline."""
    return {
        "sensitive": SafetyCategory.SENSITIVE,
        "out_of_scope": SafetyCategory.OUT_OF_SCOPE,
        "chitchat": SafetyCategory.CHITCHAT,
    }.get(intent)
