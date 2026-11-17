from datetime import date

import pytest

from expat.rag.filters import (
    BOOST_AUDIENCE,
    BOOST_LEGAL_REFERENCE,
    BOOST_SECTION_KIND,
    BOOST_SOFT_DOMAIN,
    PENALTY_AUDIENCE,
    audience_filter,
    build_where,
    legal_reference_matches,
    profile_audiences,
    soft_boost,
)
from expat.schemas import Audience, Domain, RetrievalConfig, SectionKind, SubQuery, UserProfile
from expat.schemas.profile import Citizenship, Employment, ResidenceStatus
from expat.store.synthetic import synthetic_chunks
from expat.store.vectorstore import days_since_epoch, to_chroma_metadata
from expat.store.where import matches_where

TODAY = date(2026, 11, 17)
TODAY_TS = days_since_epoch(TODAY)


def test_no_filters_when_disabled() -> None:
    sq = SubQuery(text="q", domain=Domain.TENANCY, domain_confidence=0.99)
    assert build_where(UserProfile(), sq, RetrievalConfig.baseline(), today=TODAY) is None


def test_hard_filters_with_confident_domain() -> None:
    sq = SubQuery(text="q", domain=Domain.TENANCY, domain_confidence=0.7)
    where = build_where(UserProfile(city="Munich", state="by"), sq, RetrievalConfig(), today=TODAY)
    assert where == {
        "$and": [
            {"valid_until_ts": {"$gte": TODAY_TS}},
            {"city": {"$in": ["munich", ""]}},
            {"state": {"$in": ["BY", ""]}},
            {"domain": "tenancy"},
        ]
    }


def test_unsure_domain_is_not_a_hard_filter_and_no_profile_means_validity_only() -> None:
    sq = SubQuery(text="q", domain=Domain.TENANCY, domain_confidence=0.69)
    assert build_where(None, sq, RetrievalConfig(), today=TODAY) == {"valid_until_ts": {"$gte": TODAY_TS}}


def test_where_semantics_on_synthetic_corpus() -> None:
    """Berlin and the expired regulation drop out; federal + Munich + open-ended chunks stay."""
    where = build_where(UserProfile(), SubQuery(text="q"), RetrievalConfig(), today=TODAY)
    kept = {c.metadata.doc_key for c in synthetic_chunks() if matches_where(to_chroma_metadata(c.metadata), where)}
    assert "ber-anmeldung#documents" not in kept
    assert "by-mieterschutzv#1" not in kept
    assert {"bgb#573c", "muc-anmeldung#documents", "fp-kindergeld#faq-hoehe"} <= kept


def test_audience_filter_representation() -> None:
    assert audience_filter([]) == {"applies_to": {"$contains": "all"}}
    assert audience_filter([Audience.NON_EU]) == {
        "$or": [{"applies_to": {"$contains": "all"}}, {"applies_to": {"$contains": "non_eu"}}]
    }


def test_profile_audiences_blue_card_family() -> None:
    profile = UserProfile(
        citizenship=Citizenship.NON_EU,
        residence_status=ResidenceStatus.BLUE_CARD,
        employment=Employment.EMPLOYEE,
        children_count=2,
    )
    assert profile_audiences(profile) == {Audience.NON_EU, Audience.BLUE_CARD, Audience.EMPLOYEE, Audience.FAMILY}
    assert profile_audiences(UserProfile()) == set()


@pytest.mark.parametrize(
    ("wanted", "have", "ok"),
    [
        ("§ 573c BGB", "§ 573c Abs. 1 BGB", True),
        ("§573c", "§ 573c Abs. 2 BGB", True),
        ("§ 573 BGB", "§ 573c Abs. 1 BGB", False),
        ("§ 18g AufenthG", "§ 18g Abs. 1 AufenthG", True),
        ("§ 17 BMG", "§ 17 Abs. 1 AufenthG", False),
    ],
)
def test_legal_reference_matches(wanted: str, have: str, ok: bool) -> None:
    assert legal_reference_matches(wanted, have) is ok


def _meta(doc_key: str):
    return next(c.metadata for c in synthetic_chunks() if c.metadata.doc_key == doc_key)


def test_soft_boost_components() -> None:
    family = UserProfile(children_count=1)
    eu_single = UserProfile(citizenship=Citizenship.EU)
    sq = SubQuery(
        text="q",
        legal_references=["§ 573c BGB"],
        section_kinds=[SectionKind.DOCUMENTS],
        domain=Domain.FAMILY,
        domain_confidence=0.5,
    )
    assert soft_boost(_meta("bgb#573c"), None, sq) == BOOST_LEGAL_REFERENCE
    assert soft_boost(_meta("muc-anmeldung#documents"), None, sq) == BOOST_SECTION_KIND
    assert soft_boost(_meta("fp-kindergeld#faq-hoehe"), family, sq) == pytest.approx(BOOST_AUDIENCE + BOOST_SOFT_DOMAIN)
    assert soft_boost(_meta("fp-kindergeld#faq-hoehe"), eu_single, sq) == pytest.approx(
        PENALTY_AUDIENCE + BOOST_SOFT_DOMAIN
    )
    assert soft_boost(_meta("bgb#573"), family, SubQuery(text="q")) == 0.0
