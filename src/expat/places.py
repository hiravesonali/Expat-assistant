"""Where in Germany: the supported cities, the 16 states, and finding places named in a question.

Retrieval hard-filters local chunks by `city` / `state` (ADR-0001), so the location must be known per
question. This module is deterministic (regex + tables) on purpose: city names are a closed, small set,
and a wrong city is worse than none (a Berlin user must never get Munich office rules).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The 16 states (Länder), ISO 3166-2:DE codes without the "DE-" prefix.
STATES: dict[str, str] = {
    "BW": "Baden-Württemberg",
    "BY": "Bavaria (Bayern)",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hesse (Hessen)",
    "MV": "Mecklenburg-Western Pomerania",
    "NI": "Lower Saxony (Niedersachsen)",
    "NW": "North Rhine-Westphalia (NRW)",
    "RP": "Rhineland-Palatinate",
    "SL": "Saarland",
    "SN": "Saxony (Sachsen)",
    "ST": "Saxony-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thuringia (Thüringen)",
}


@dataclass(frozen=True)
class City:
    slug: str  # the value stored in chunk metadata (`city`)
    name: str  # English display name
    name_de: str
    state: str  # state code


# Cities with city-specific sources in the knowledge base (docs/plan-germany-wide.md).
SUPPORTED_CITIES: dict[str, City] = {
    c.slug: c
    for c in (
        City("berlin", "Berlin", "Berlin", "BE"),
        City("hamburg", "Hamburg", "Hamburg", "HH"),
        City("munich", "Munich", "München", "BY"),
        City("cologne", "Cologne", "Köln", "NW"),
        City("frankfurt", "Frankfurt am Main", "Frankfurt am Main", "HE"),
        City("stuttgart", "Stuttgart", "Stuttgart", "BW"),
    )
}

# Spellings people actually type, incl. ASCII fallbacks. "Frankfurt" means Frankfurt am Main, except
# "Frankfurt (Oder)" / "Frankfurt an der Oder" in Brandenburg, which the negative lookahead excludes.
_ALIASES: dict[str, str] = {
    r"berlin": "berlin",
    r"hamburg": "hamburg",
    r"m(?:ü|ue|u)nchen|munich|munchen": "munich",
    r"k(?:ö|oe|o)ln|cologne": "cologne",
    r"frankfurt(?!\s*(?:\(\s*oder|an der oder|/\s*oder|\s+oder))(?:\s+am\s+main|\s*\(main\)|/main)?": "frankfurt",
    r"stuttgart": "stuttgart",
}
# Optional possessive "s" ("Hamburgs Bürgerämter", "Berlin's"), but not "Berliner Straße" or "Hamburger".
_CITY_RE = re.compile(r"\b(" + "|".join(f"(?:{p})" for p in _ALIASES) + r")(?:['’]?s)?\b", re.IGNORECASE)
_COMPILED = [(re.compile(rf"^(?:{p})$", re.IGNORECASE), slug) for p, slug in _ALIASES.items()]


def _slug_for(match: str) -> str:
    for pattern, slug in _COMPILED:
        if pattern.match(match):
            return slug
    raise ValueError(match)  # unreachable: the big regex is built from the same patterns


def find_cities(text: str) -> list[City]:
    """Supported cities named in `text`, in order of first mention, without duplicates."""
    seen: dict[str, City] = {}
    for match in _CITY_RE.finditer(text or ""):
        slug = _slug_for(match.group(1))
        seen.setdefault(slug, SUPPORTED_CITIES[slug])
    return list(seen.values())


def city_label(slug: str | None) -> str:
    """'cologne' -> 'Cologne'; unknown or other cities are title-cased; None -> ''."""
    if not slug:
        return ""
    return SUPPORTED_CITIES[slug].name if slug in SUPPORTED_CITIES else slug.replace("-", " ").title()


def state_for_city(slug: str | None) -> str | None:
    return SUPPORTED_CITIES[slug].state if slug in SUPPORTED_CITIES else None
