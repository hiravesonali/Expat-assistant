"""The real sources.yaml must always load: a typo there should fail CI, not a crawl."""

import pytest

from expat.ingestion.sources import ParagraphRange, load_sources, paragraph_sort_key
from expat.schemas import Domain


def test_sources_yaml_loads_and_ids_are_unique():
    registry = load_sources()
    ids = [s.id for s in registry.sources]
    assert len(ids) == len(set(ids))
    assert {"bgb", "aufenthg", "bmg", "beeg", "estg", "muc-anmeldung", "fp-kindergeld"} <= set(ids)


def test_paragraph_sort_key_orders_suffixes_numerically():
    # Plain string order would put "5730" before "573c" ('0' < 'c'); numerically it comes after.
    assert paragraph_sort_key("5730") > paragraph_sort_key("573c")
    assert paragraph_sort_key("58") < paragraph_sort_key("573c")
    assert paragraph_sort_key("573c") > paragraph_sort_key("573")


@pytest.mark.parametrize(
    ("spec", "paragraph", "expected"),
    [
        ("535-580a", "573c", True),
        ("535-580a", "580a", True),
        ("535-580a", "581", False),
        ("535-580a", "534", False),
        ("17", "17", True),
        ("17", "17a", False),
        ("4-9c", "9a", True),
    ],
)
def test_paragraph_range(spec, paragraph, expected):
    assert ParagraphRange.parse(spec).contains(paragraph) is expected


def test_domain_map_overrides_default_domain():
    bgb = load_sources().get("bgb")
    assert bgb.includes_paragraph("573c")
    assert not bgb.includes_paragraph("1")
    assert bgb.domain_for("193") == (Domain.TENANCY, "deadlines")


def test_manual_sources_declare_a_path():
    for source in load_sources().sources:
        if source.fetch_method == "manual":
            assert source.manual_path and source.manual_path.startswith("data/manual/")
