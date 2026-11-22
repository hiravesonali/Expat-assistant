from datetime import date

import pytest
from pydantic import ValidationError

from expat.config import Settings
from expat.schemas import ChunkMetadata, RetrievalConfig, UserProfile


def _meta(**overrides):
    base = dict(
        chunk_id="c1",
        parent_id="bgb#573c",
        doc_id="d1",
        doc_key="bgb#573c",
        doc_version="v1",
        content_hash="h1",
        domain="tenancy",
        source_type="law",
        source_id="bgb",
        source_name="Gesetze im Internet",
        source_url="https://www.gesetze-im-internet.de/bgb/__573c.html",
        title="Kündigungsfristen",
        language="de",
        jurisdiction="federal",
        last_verified=date(2026, 11, 18),
    )
    base.update(overrides)
    return ChunkMetadata(**base)


def test_chunk_metadata_defaults():
    m = _meta()
    assert m.applies_to == ["all"]
    assert m.section_kind == "other"


def test_chunk_metadata_rejects_unknown_language():
    with pytest.raises(ValidationError):
        _meta(language="fr")


def test_collection_name_encodes_model_and_schema():
    s = Settings(embedding_model="qwen/qwen3-embedding-8b", schema_version=1)
    assert s.collection_name == "expat__qwen3-embedding-8b__s1"


def test_profile_summary_mentions_key_facts():
    p = UserProfile(
        city="munich", citizenship="non_eu", residence_status="blue_card", children_count=2, youngest_child_age=3
    )
    s = p.summary()
    assert "NON-EU" in s and "blue card" in s and "2 children" in s and "Munich" in s


def test_baseline_config_disables_everything():
    c = RetrievalConfig.baseline()
    assert not (c.use_bm25 or c.use_filters or c.use_german_rewrite or c.use_multi_query)


def test_doc_key_matching_rule():
    from expat.schemas import doc_key_matches

    assert doc_key_matches("muc-anmeldung#documents", "muc-anmeldung")
    assert doc_key_matches("bgb#573c", "bgb#573c")
    assert not doc_key_matches("bgb#573", "bgb#573c")
    assert not doc_key_matches("bgb#573c", "bgb#573")


def test_plan_from_raw_has_one_subquery():
    from expat.schemas import RetrievalPlan

    plan = RetrievalPlan.from_raw("How do I register in Munich?")
    assert len(plan.sub_queries) == 1 and plan.sub_queries[0].text == plan.standalone_question
