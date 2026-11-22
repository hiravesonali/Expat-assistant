"""Profile + question -> Chroma `where` (HARD filters) and post-fusion score boosts (SOFT signals).

Why the split (docs/vector-db-design.md §4, "Hard vs soft filters"): over-filtering kills recall.
Most federal guides apply to everyone and audience tags are imperfect, so only facts that make a
chunk *wrong* for this user are hard filters:
* another city or another state (`city in {profile.city, ""}`, `state in {profile.state, ""}`;
  "" = federal / not city-specific, so it always stays);
* expired rules (`valid_until_ts >= today`);
* a domain, but only when query analysis is confident (>= 0.7). A wrong hard domain filter means
  zero recall; a missing one only costs a little precision.
Audience, section kind and § references are soft boosts applied after RRF (`soft_boost`).

"Missing" validity and Chroma semantics: a Chroma comparison NEVER matches a document that lacks
the key, so `valid_until_ts >= today` would silently drop every chunk without an expiry date.
Instead of an `$or` with a non-existent "$exists" operator, the indexer always writes the key and
uses a far-future sentinel (`expat.store.vectorstore.OPEN_END_TS`) for open-ended chunks.

The same `where` dict is evaluated natively by Chroma and in Python for BM25 (`expat.store.where`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from expat.schemas import Audience, ChunkMetadata, Location, RankedHit, RetrievalConfig, SubQuery, UserProfile
from expat.schemas.profile import Citizenship, Employment, FamilyStatus, ResidenceStatus
from expat.store.vectorstore import days_since_epoch
from expat.store.where import Where

DOMAIN_HARD_THRESHOLD = 0.7

# Soft boost weights. The final score is `fused_score * (1 + soft_boost(...))`: multiplicative, so
# boosts re-order hits with similar fused scores without letting metadata beat strong retrieval.
BOOST_LEGAL_REFERENCE = 0.5  # the user named this exact § : strongest signal
BOOST_SECTION_KIND = 0.25  # "how much does it cost" -> fees section
BOOST_AUDIENCE = 0.15  # chunk explicitly targets one of the user's audiences
PENALTY_AUDIENCE = -0.15  # chunk targets only audiences the user does NOT belong to
BOOST_SOFT_DOMAIN = 0.1  # router was unsure (no hard filter), but the domain still matches


# ------------------------------------------------------------------------------------- audience


def profile_audiences(profile: UserProfile | None) -> set[Audience]:
    """Map the coarse profile enums onto the corpus' `Audience` tags. Unknown fields add nothing."""
    if profile is None:
        return set()
    audiences: set[Audience] = set()
    if profile.citizenship in (Citizenship.EU, Citizenship.GERMAN):
        audiences.add(Audience.EU)
    elif profile.citizenship == Citizenship.NON_EU:
        audiences.add(Audience.NON_EU)
    if profile.residence_status == ResidenceStatus.BLUE_CARD:
        audiences |= {Audience.BLUE_CARD, Audience.NON_EU, Audience.EMPLOYEE}
    if profile.residence_status == ResidenceStatus.STUDENT or profile.employment == Employment.STUDENT:
        audiences.add(Audience.STUDENT)
    if profile.employment == Employment.EMPLOYEE:
        audiences.add(Audience.EMPLOYEE)
    if profile.employment in (Employment.FREELANCER, Employment.SELF_EMPLOYED):
        audiences.add(Audience.FREELANCER)
    if profile.children_count > 0 or profile.family_status in (FamilyStatus.MARRIED, FamilyStatus.PARTNERSHIP):
        audiences.add(Audience.FAMILY)
    return audiences


def audience_filter(audiences: Iterable[Audience | str]) -> Where | None:
    """`where` clause: chunk applies to ANY of `audiences` or to "all".

    The ONLY place that knows how `applies_to` is stored. The Day-2 spike showed local chromadb
    supports list metadata + `$contains`; with the boolean-flag fallback only this body would change
    to `{"aud_<value>": True}`. Not used as a hard filter by default (audience is a soft signal), but
    available for ablations.
    """
    values = sorted({str(a) for a in audiences} | {Audience.ALL.value})
    clauses: list[Where] = [{"applies_to": {"$contains": v}} for v in values]
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}


# ----------------------------------------------------------------------------------- hard filter


def _and(clauses: list[Where]) -> Where | None:
    """Chroma rejects `$and` with fewer than two operands, so unwrap the trivial cases."""
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def location_from_profile(profile: UserProfile | None) -> Location:
    """The profile's city/state as a Location (unknown fields -> empty lists)."""
    if profile is None or not (profile.city or profile.state):
        return Location()
    return Location(
        cities=[profile.city] if profile.city else [],
        states=[profile.state] if profile.state else [],
        source="profile",
    )


def build_where(
    profile: UserProfile | None,
    subquery: SubQuery,
    config: RetrievalConfig,
    today: date | None = None,
    location: Location | None = None,
) -> Where | None:
    """Build the HARD `where` filter for one sub-query (None = no filtering at all).

    Location: the per-question `location` (pipeline: places named in the question > profile) or, if not
    given, the profile's. Local chunks must match one of its cities/states; nationwide chunks ("") always
    pass. An unknown location therefore means "nationwide sources only", never another city's rules.
    With neither a location nor a profile (bare eval/debug calls) no location filter is applied.
    """
    if not config.use_filters:
        return None
    clauses: list[Where] = [{"valid_until_ts": {"$gte": days_since_epoch(today or date.today())}}]
    if location is not None or profile is not None:
        loc = location if location is not None else location_from_profile(profile)
        clauses.append({"city": {"$in": [*loc.cities, ""]}})
        clauses.append({"state": {"$in": [*loc.states, ""]}})
    if subquery.domain is not None and subquery.domain_confidence >= DOMAIN_HARD_THRESHOLD:
        clauses.append({"domain": subquery.domain.value})
    return _and(clauses)


# ------------------------------------------------------------------------------------ soft boost

_PARAGRAPH_RE = re.compile(r"§+\s*(\d+[a-z]?)", re.IGNORECASE)
# Law abbreviations: BGB, or CamelCase ending in "G" (AufenthG, EStG, BEEG, BMG).
_LAW_RE = re.compile(r"\b(BGB|[A-Z][A-Za-z]*G)\b")


def _parse_reference(ref: str) -> tuple[str | None, str | None]:
    """'§ 573c Abs. 1 BGB' -> ('573c', 'bgb'). Law abbreviation is optional."""
    paragraph = _PARAGRAPH_RE.search(ref)
    law = _LAW_RE.search(ref)
    return (
        paragraph.group(1).lower() if paragraph else None,
        law.group(1).lower() if law else None,
    )


def legal_reference_matches(wanted: str, chunk_reference: str) -> bool:
    """Same § number, and the same law if BOTH name one ('§ 573c BGB' matches '§ 573c Abs. 1 BGB')."""
    want_par, want_law = _parse_reference(wanted)
    have_par, have_law = _parse_reference(chunk_reference)
    if want_par is None or want_par != have_par:
        return False
    return want_law is None or have_law is None or want_law == have_law


def soft_boost(hit: RankedHit | ChunkMetadata, profile: UserProfile | None, subquery: SubQuery) -> float:
    """Relative boost for one hit; apply as `fused_score * (1 + boost)`. 0.0 means neutral."""
    meta = hit.metadata if isinstance(hit, RankedHit) else hit
    boost = 0.0
    wanted_refs = subquery.legal_references
    if meta.legal_reference and any(legal_reference_matches(r, meta.legal_reference) for r in wanted_refs):
        boost += BOOST_LEGAL_REFERENCE
    if meta.section_kind in subquery.section_kinds:
        boost += BOOST_SECTION_KIND
    audiences = profile_audiences(profile)
    tagged = set(meta.applies_to) - {Audience.ALL}
    if audiences and tagged and Audience.ALL not in meta.applies_to:
        boost += BOOST_AUDIENCE if tagged & audiences else PENALTY_AUDIENCE
    if (
        subquery.domain is not None
        and subquery.domain_confidence < DOMAIN_HARD_THRESHOLD
        and meta.domain == subquery.domain
    ):
        boost += BOOST_SOFT_DOMAIN
    return boost
