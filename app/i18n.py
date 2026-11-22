"""Interface language (English | Deutsch). English is the default; German falls back to English per key.

The switch at the top of the page sets `st.session_state.lang` and the profile's `answer_language`, so the
interface AND the answers follow the user's choice (docs: "Language" in README). Admin/debug pages stay English.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

LANGUAGES = {"en": "English", "de": "Deutsch"}
DEFAULT_LANGUAGE = "en"


def lang() -> str:
    value = st.session_state.get("lang", DEFAULT_LANGUAGE)
    return value if value in LANGUAGES else DEFAULT_LANGUAGE


def t(key: str, **kwargs: Any) -> str:
    """Translated string for the current language (English if the key has no German text)."""
    text = STRINGS[lang()].get(key) or STRINGS["en"][key]
    return text.format(**kwargs) if kwargs else text


def pick(table: dict[str, Any]) -> Any:
    """For structured content kept per language (examples, labels): the current language's entry."""
    return table.get(lang()) or table["en"]


STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "tagline": "Your guide to settling in Germany",
        "brand_sub": "Germany · official sources",
        "eyebrow": "📍 All of Germany · 6 cities in detail · English & Deutsch",
        "title_a": "Settle into Germany",
        "title_b": "with confidence",
        "lead": "Registration, residence permits, renting and family benefits, answered from official German "
        "sources with every claim cited. Local details for Berlin, Hamburg, Munich, Cologne, Frankfurt and "
        "Stuttgart.",
        "placeholder": "Ask about Anmeldung, renting, Blue Card, Kindergeld… in any German city",
        "disclaimer": "General information, not legal or tax advice. Official German texts are binding.",
        "footer": "Answers cite official German sources. {disclaimer}",
        "language": "Language",
        # sidebar
        "new_chat": "New chat",
        "recents": "Recents",
        "personalise": "Personalise answers",
        "your_profile": "Your profile",
        "export_chat": "Export chat",
        "settings": "Settings",
        "live_answers": "Live answers",
        "live_help": "On: real search over official sources + AI answer (OpenRouter). "
        "Off: demo mode with scripted answers, no API calls.",
        "dev_tools": "Developer tools",
        "privacy": "Your profile and chats live only in this browser tab.",
        "export_caption": "Includes sources, calculations and token costs. Nothing is stored on the server.",
        "demo_badge": "Demo mode · scripted answers",
        # profile form
        "your_situation": "Your situation",
        "situation_caption": "Optional. Lets me apply the rules that fit you. Kept only in this browser tab.",
        "prefer": "Prefer not to say",
        "city": "City",
        "city_help": "Local offices, appointments and rules differ by city. Six cities have detailed local sources.",
        "other_city_option": "Other city…",
        "other_city": "Other city (if not listed)",
        "state": "State (Bundesland)",
        "state_help": "Filled in automatically for the listed cities.",
        "children": "Children",
        "youngest_age": "Youngest child's age",
        "years": "{n} years",
        "youngest_help": "Only used when you have children (Kindergeld, Elterngeld, Kita).",
        "save_profile": "Save profile",
        "saved": "Saved. Answers now take your situation into account.",
        # chat
        "try_again": "Try again",
        "another_city": "Another city or region",
        "city_placeholder": "e.g. Leipzig",
        "use_place": "Use this place",
        "empty_question": "Please type a question.",
        "too_long": "That message is {n:,} characters long; please keep questions under {max:,}.",
        "rate_limited": "You've asked {n} questions in the last hour, the limit for this public demo. Please try "
        "again in about {minutes} min, or switch **Live answers** off in Settings to explore the demo answers.",
        "daily_cap": "The public demo has reached its daily limit of live answers. Please come back tomorrow, or "
        "switch **Live answers** off in Settings to explore the demo answers.",
        "thinking": "Thinking…",
        "done": "Done",
        # answer details
        "how_i_got": "How I got this answer · {n} steps",
        "insufficient": "I couldn't find enough in my official sources to answer this reliably. "
        "Please check with the responsible authority.",
        "stale": "Some sources were last verified a while ago ({sources}). Rules may have changed; check the "
        "official page.",
        "unverified": "Mentions not found in the cited sources: ",
        "went_wrong": "**Something went wrong** ({code}): {message}",
        "source_details": "Source details",
        "verified": "Verified",
        "type": "Type",
        "tool_result": "Tool result",
        "official_source": "Official source",
        "binding": "The official German text is binding. Translations and summaries are for orientation only.",
        "standalone": "Standalone question: *{q}*",
        "en_rewrites": "English rewrites",
        "de_rewrites": "German rewrites 🇩🇪",
        "step_back": "Step-back question: *{q}*",
        "legal_refs": "Legal references: ",
        "top_hits": "Top hits for: *{q}*",
        "no_hits": "No hits.",
        "waiting_tool": "Waiting for the tool…",
        "budget": "Live answers are paused: this public demo has used up its AI budget for now. "
        "Switch **Live answers** off in Settings to explore the demo answers, or try again later.",
    },
    "de": {
        "tagline": "Ihr Wegweiser fürs Ankommen in Deutschland",
        "brand_sub": "Deutschland · amtliche Quellen",
        "eyebrow": "📍 Ganz Deutschland · 6 Städte im Detail · English & Deutsch",
        "title_a": "In Deutschland ankommen",
        "title_b": "mit Sicherheit",
        "lead": "Anmeldung, Aufenthaltstitel, Mieten und Familienleistungen, beantwortet aus amtlichen deutschen "
        "Quellen, jede Aussage belegt. Lokale Details für Berlin, Hamburg, München, Köln, Frankfurt und Stuttgart.",
        "placeholder": "Fragen Sie zu Anmeldung, Miete, Blauer Karte, Kindergeld… in jeder deutschen Stadt",
        "disclaimer": "Allgemeine Information, keine Rechts- oder Steuerberatung. "
        "Verbindlich sind die amtlichen Texte.",
        "footer": "Antworten zitieren amtliche deutsche Quellen. {disclaimer}",
        "language": "Sprache",
        "new_chat": "Neuer Chat",
        "recents": "Verlauf",
        "personalise": "Antworten personalisieren",
        "your_profile": "Ihr Profil",
        "export_chat": "Chat exportieren",
        "settings": "Einstellungen",
        "live_answers": "Live-Antworten",
        "live_help": "An: echte Suche in amtlichen Quellen + KI-Antwort (OpenRouter). "
        "Aus: Demo-Modus mit vorbereiteten Antworten, ohne API-Aufrufe.",
        "dev_tools": "Entwickler-Werkzeuge",
        "privacy": "Ihr Profil und Ihre Chats bleiben nur in diesem Browser-Tab.",
        "export_caption": "Mit Quellen, Berechnungen und Token-Kosten. Auf dem Server wird nichts gespeichert.",
        "demo_badge": "Demo-Modus · vorbereitete Antworten",
        "your_situation": "Ihre Situation",
        "situation_caption": "Freiwillig. So kann ich die passenden Regeln anwenden. Nur in diesem Browser-Tab "
        "gespeichert.",
        "prefer": "Keine Angabe",
        "city": "Stadt",
        "city_help": "Ämter, Termine und Regeln unterscheiden sich je Stadt. Für sechs Städte gibt es lokale Quellen.",
        "other_city_option": "Andere Stadt…",
        "other_city": "Andere Stadt (falls nicht aufgeführt)",
        "state": "Bundesland",
        "state_help": "Wird für die aufgeführten Städte automatisch ausgefüllt.",
        "children": "Kinder",
        "youngest_age": "Alter des jüngsten Kindes",
        "years": "{n} Jahre",
        "youngest_help": "Nur relevant, wenn Sie Kinder haben (Kindergeld, Elterngeld, Kita).",
        "save_profile": "Profil speichern",
        "saved": "Gespeichert. Die Antworten berücksichtigen jetzt Ihre Situation.",
        "try_again": "Erneut versuchen",
        "another_city": "Andere Stadt oder Region",
        "city_placeholder": "z. B. Leipzig",
        "use_place": "Diesen Ort verwenden",
        "empty_question": "Bitte geben Sie eine Frage ein.",
        "too_long": "Die Nachricht hat {n:,} Zeichen; bitte halten Sie Fragen unter {max:,}.",
        "rate_limited": "Sie haben in der letzten Stunde {n} Fragen gestellt, das Limit dieser öffentlichen Demo. "
        "Bitte versuchen Sie es in etwa {minutes} Min. erneut oder schalten Sie **Live-Antworten** in den "
        "Einstellungen aus, um die Demo-Antworten anzusehen.",
        "daily_cap": "Die öffentliche Demo hat ihr Tageslimit für Live-Antworten erreicht. Bitte kommen Sie morgen "
        "wieder oder schalten Sie **Live-Antworten** in den Einstellungen aus.",
        "thinking": "Denke nach…",
        "done": "Fertig",
        "how_i_got": "So bin ich zur Antwort gekommen · {n} Schritte",
        "insufficient": "In meinen amtlichen Quellen habe ich nicht genug gefunden, um das verlässlich zu "
        "beantworten. Bitte fragen Sie bei der zuständigen Behörde nach.",
        "stale": "Einige Quellen wurden länger nicht geprüft ({sources}). Regeln können sich geändert haben; prüfen "
        "Sie die amtliche Seite.",
        "unverified": "In den zitierten Quellen nicht gefunden: ",
        "went_wrong": "**Etwas ist schiefgelaufen** ({code}): {message}",
        "source_details": "Quelle",
        "verified": "Geprüft",
        "type": "Art",
        "tool_result": "Werkzeug-Ergebnis",
        "official_source": "Amtliche Quelle",
        "binding": "Verbindlich ist der amtliche deutsche Text. Übersetzungen und Zusammenfassungen dienen nur "
        "der Orientierung.",
        "standalone": "Eigenständige Frage: *{q}*",
        "en_rewrites": "Englische Umformulierungen",
        "de_rewrites": "Deutsche Umformulierungen 🇩🇪",
        "step_back": "Übergeordnete Frage: *{q}*",
        "legal_refs": "Rechtsgrundlagen: ",
        "top_hits": "Beste Treffer für: *{q}*",
        "no_hits": "Keine Treffer.",
        "waiting_tool": "Warte auf das Werkzeug…",
        "budget": "Live-Antworten sind pausiert: Diese öffentliche Demo hat ihr KI-Budget vorerst aufgebraucht. "
        "Schalten Sie **Live-Antworten** in den Einstellungen aus, um die Demo-Antworten anzusehen, oder versuchen "
        "Sie es später erneut.",
    },
}

# (icon, title, one-line description, full prompt that is sent)
EXAMPLES = {
    "en": [
        (":material/how_to_reg:", "Anmeldung", "Register your new address",
         "I just moved to Berlin on a Blue Card. What do I need for the Anmeldung, and by when?"),
        (":material/key:", "End my lease", "Notice periods and end dates",
         "I rent a flat in Hamburg since 2021. If I give notice today, when does my tenancy end?"),
        (":material/child_care:", "Kindergeld & Elterngeld", "What your family can get",
         "We're expecting a baby in March. How much Kindergeld and Elterngeld can we get?"),
        (":material/verified_user:", "Permanent residence", "Settlement permit with a Blue Card",
         "When can I apply for a settlement permit (Niederlassungserlaubnis) with my Blue Card?"),
    ],
    "de": [
        (":material/how_to_reg:", "Anmeldung", "Neue Adresse anmelden",
         "Ich bin gerade mit einer Blauen Karte nach Berlin gezogen. Was brauche ich für die Anmeldung und bis wann?"),
        (":material/key:", "Wohnung kündigen", "Kündigungsfristen und Enddatum",
         "Ich miete seit 2021 eine Wohnung in Hamburg. Wenn ich heute kündige, wann endet mein Mietverhältnis?"),
        (":material/child_care:", "Kindergeld & Elterngeld", "Was Ihrer Familie zusteht",
         "Wir erwarten im März ein Baby. Wie viel Kindergeld und Elterngeld bekommen wir?"),
        (":material/verified_user:", "Niederlassungserlaubnis", "Daueraufenthalt mit der Blauen Karte",
         "Wann kann ich mit meiner Blauen Karte eine Niederlassungserlaubnis beantragen?"),
    ],
}  # fmt: skip

TRUST = {
    "en": [
        ("📚", "Cited official sources", "Laws and city pages, with dates"),
        ("🧮", "Calculated, not guessed", "Deadlines and amounts by tested tools"),
        ("🛡️", "Knows its limits", "Refers you to experts when needed"),
    ],
    "de": [
        ("📚", "Belegte amtliche Quellen", "Gesetze und Stadtseiten, mit Datum"),
        ("🧮", "Berechnet, nicht geraten", "Fristen und Beträge mit geprüften Werkzeugen"),
        ("🛡️", "Kennt seine Grenzen", "Verweist an Fachleute, wenn nötig"),
    ],
}

STEP_LABELS = {
    "en": {
        "query_analysis": "Understanding your question",
        "retrieval": "Searching official sources",
        "rerank": "Re-ranking the best passages",
        "tool_call": "Calculating with a tool",
        "generation": "Writing the answer",
        "safety": "Safety check",
        "clarification": "Asking a follow-up question",
    },
    "de": {
        "query_analysis": "Frage verstehen",
        "retrieval": "Amtliche Quellen durchsuchen",
        "rerank": "Beste Passagen neu ordnen",
        "tool_call": "Mit einem Werkzeug berechnen",
        "generation": "Antwort schreiben",
        "safety": "Sicherheitsprüfung",
        "clarification": "Rückfrage stellen",
    },
}

TOOL_LABELS = {
    "en": {
        "calculate_tenancy_notice": "Tenancy notice calculator",
        "calculate_deadline": "Deadline calculator",
        "estimate_family_benefits": "Family benefits estimator",
        "generate_document_checklist": "Document checklist",
        "schengen_days_calculator": "Schengen 90/180 checker",
    },
    "de": {
        "calculate_tenancy_notice": "Kündigungsfrist-Rechner",
        "calculate_deadline": "Fristen-Rechner",
        "estimate_family_benefits": "Familienleistungs-Schätzer",
        "generate_document_checklist": "Unterlagen-Checkliste",
        "schengen_days_calculator": "Schengen-90/180-Rechner",
    },
}

# Profile form: field label + enum value labels, per language (enum values are the StrEnum values).
PROFILE_LABELS = {
    "en": {
        "citizenship": ("Citizenship", {"eu": "EU / EEA / Swiss", "non_eu": "Non-EU", "german": "German"}),
        "residence_status": ("Residence status", {"blue_card": "EU Blue Card", "work_permit": "Work permit",
            "student": "Student visa", "family_reunion": "Family reunion", "settlement": "Settlement permit",
            "eu_freedom": "EU free movement", "other": "Other"}),
        "employment": ("Employment", {"employee": "Employee", "freelancer": "Freelancer",
            "self_employed": "Self-employed", "student": "Student", "unemployed": "Not working"}),
        "family_status": ("Family status", {"single": "Single", "married": "Married", "partnership": "Partnership"}),
        "housing": ("Housing", {"renting": "Renting", "owning": "Owning", "looking": "Looking for a flat"}),
    },
    "de": {
        "citizenship": ("Staatsangehörigkeit", {"eu": "EU / EWR / Schweiz", "non_eu": "Nicht-EU", "german": "Deutsch"}),
        "residence_status": ("Aufenthaltsstatus", {"blue_card": "Blaue Karte EU", "work_permit": "Arbeitserlaubnis",
            "student": "Studentenvisum", "family_reunion": "Familiennachzug", "settlement": "Niederlassungserlaubnis",
            "eu_freedom": "EU-Freizügigkeit", "other": "Sonstiges"}),
        "employment": ("Beschäftigung", {"employee": "Angestellt", "freelancer": "Freiberuflich",
            "self_employed": "Selbstständig", "student": "Studium", "unemployed": "Nicht berufstätig"}),
        "family_status": ("Familienstand", {"single": "Ledig", "married": "Verheiratet",
            "partnership": "Eingetragene Partnerschaft"}),
        "housing": ("Wohnen", {"renting": "Zur Miete", "owning": "Eigentum", "looking": "Auf Wohnungssuche"}),
    },
}  # fmt: skip
