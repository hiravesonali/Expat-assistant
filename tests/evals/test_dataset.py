"""Validates the committed golden set (golden_v1.jsonl) and the loader / upload logic. Fully offline."""

import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from expat.config import REPO_ROOT
from expat.evals.dataset import (
    DEFAULT_GOLDEN_PATH,
    GoldenDatasetError,
    GoldenExample,
    load_golden,
    upload_dataset,
)

LAW_SOURCES = {"bgb", "aufenthg", "bmg", "beeg", "estg"}
LAW_KEY = re.compile(r"^(bgb|aufenthg|bmg|beeg|estg)#\d+[a-z]?$")


def _conventions_source_ids() -> tuple[set[str], set[str]]:
    """Parse the source_id table in docs/conventions.md: exact ids and `<prefix>-<slug>` families."""
    text = (REPO_ROOT / "docs" / "conventions.md").read_text(encoding="utf-8")
    exact: set[str] = set()
    prefixes: set[str] = set()
    for match in re.finditer(r"^\| `([a-z0-9<>-]+)` \|", text, flags=re.MULTILINE):
        source_id = match.group(1)
        if source_id.endswith("<slug>"):
            prefixes.add(source_id.removesuffix("<slug>"))
        else:
            exact.add(source_id)
    return exact, prefixes


@pytest.fixture(scope="module")
def golden() -> list[GoldenExample]:
    return load_golden(DEFAULT_GOLDEN_PATH)


def test_golden_size_and_unique_ids(golden: list[GoldenExample]) -> None:
    assert len(golden) == 71  # 40 Munich-era + 31 Germany-wide (evals/golden/add_germany_v1.py)
    assert len({e.id for e in golden}) == 71


def test_golden_slice_counts(golden: list[GoldenExample]) -> None:
    counts = Counter(e.slice for e in golden)
    assert counts == {"bureaucracy": 25, "tenancy": 19, "family": 16, "multi_domain": 6, "out_of_scope": 5}


def test_golden_split_is_stratified(golden: list[GoldenExample]) -> None:
    splits = Counter(e.split for e in golden)
    assert splits == {"dev": 45, "holdout": 26}
    for slice_name in {e.slice for e in golden}:
        in_slice = [e for e in golden if e.slice == slice_name]
        assert any(e.split == "holdout" for e in in_slice), slice_name
        assert any(e.split == "dev" for e in in_slice), slice_name


def test_golden_cross_cutting_coverage(golden: list[GoldenExample]) -> None:
    german = [e for e in golden if e.language == "de"]
    assert len(german) >= 6
    assert len({e.slice for e in german}) >= 4, "German questions should be spread across slices"
    assert sum(e.expected_tool is not None for e in golden) >= 6
    assert sum(e.should_refuse for e in golden) == 5


def test_golden_profiles_vary(golden: list[GoldenExample]) -> None:
    citizenships = {e.profile.citizenship for e in golden}
    employments = {e.profile.employment for e in golden}
    assert {"eu", "non_eu"} <= citizenships
    assert {"student", "freelancer", "employee"} <= employments


def test_every_expected_source_exists_in_conventions(golden: list[GoldenExample]) -> None:
    exact, prefixes = _conventions_source_ids()
    assert "muc-anmeldung" in exact and "bamf-" in prefixes  # the parser itself works
    for example in golden:
        for source in example.expected_sources:
            if source.source_id in LAW_SOURCES:
                assert LAW_KEY.match(source.doc_key), f"{example.id}: bad law key {source.doc_key}"
            else:
                known = source.source_id in exact or any(source.source_id.startswith(p) for p in prefixes)
                assert known, f"{example.id}: unknown source_id {source.source_id}"


def test_expected_tools_are_documented(golden: list[GoldenExample]) -> None:
    documented = (REPO_ROOT / "docs" / "tools.md").read_text(encoding="utf-8")
    for example in golden:
        if example.expected_tool:
            assert f"`{example.expected_tool.name}`" in documented, example.id


def test_must_include_alternatives_appear_in_reference_answer(golden: list[GoldenExample]) -> None:
    """Sanity check of our own ground truth: the reference answer must pass its own must_include check."""
    from expat.evals.metrics import must_include_score

    for example in golden:
        assert must_include_score(example.reference_answer, example.must_include) == 1.0, example.id


def test_split_filter(golden: list[GoldenExample]) -> None:
    dev = load_golden(DEFAULT_GOLDEN_PATH, split="dev")
    assert len(dev) == 45 and all(e.split == "dev" for e in dev)


# --- loader error handling -------------------------------------------------------------------------------------


def _write(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "golden.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "ten-001",
        "split": "dev",
        "question": "How much notice?",
        "language": "en",
        "profile": {"city": "munich"},
        "domains": ["tenancy"],
        "category": "legal_lookup",
        "expected_sources": [{"doc_key": "bgb#573c", "required": True}],
        "reference_answer": "Three months for tenants.",
    }
    row.update(overrides)
    return row


def test_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    with pytest.raises(GoldenDatasetError, match="duplicate id"):
        load_golden(_write(tmp_path, [_row(), _row()]))


def test_loader_reports_line_number_on_typo(tmp_path: Path) -> None:
    bad = _row(id="ten-002")
    bad["expected_source"] = bad.pop("expected_sources")  # typo must not silently mean "no sources"
    with pytest.raises(GoldenDatasetError, match=r"golden.jsonl:2"):
        load_golden(_write(tmp_path, [_row(), bad]))


def test_answerable_example_needs_required_source(tmp_path: Path) -> None:
    with pytest.raises(GoldenDatasetError, match="required expected source"):
        load_golden(_write(tmp_path, [_row(expected_sources=[{"doc_key": "bgb#573c", "required": False}])]))


def test_refusal_flag_must_match_category(tmp_path: Path) -> None:
    with pytest.raises(GoldenDatasetError, match="should_refuse"):
        load_golden(_write(tmp_path, [_row(should_refuse=True)]))


def test_to_langsmith_example_shape() -> None:
    example = GoldenExample.model_validate(_row())
    payload = example.to_langsmith_example()
    assert payload["inputs"]["question"] == "How much notice?"
    assert payload["reference_outputs"]["expected_sources"][0]["doc_key"] == "bgb#573c"
    assert payload["split"] == "dev"
    assert payload["metadata"]["slice"] == "tenancy"


# --- upload with a fake client ----------------------------------------------------------------------------------


class FakeClient:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.created: list[dict[str, Any]] = []

    def has_dataset(self, *, dataset_name: str) -> bool:
        return dataset_name in self.existing

    def create_dataset(self, dataset_name: str, *, description: str | None = None, metadata: dict | None = None) -> Any:
        return SimpleNamespace(id="ds-1", name=dataset_name)

    def create_examples(self, *, dataset_id: Any, examples: list[dict[str, Any]]) -> Any:
        self.created.extend(examples)
        return {"count": len(examples)}


def test_upload_dataset_creates_all_examples() -> None:
    client = FakeClient()
    assert upload_dataset("expat-test", DEFAULT_GOLDEN_PATH, client=client) == "ds-1"
    assert len(client.created) == 71
    assert {e["split"] for e in client.created} == {"dev", "holdout"}


def test_upload_dataset_refuses_to_overwrite() -> None:
    with pytest.raises(GoldenDatasetError, match="already exists"):
        upload_dataset("expat-test", DEFAULT_GOLDEN_PATH, client=FakeClient(existing={"expat-test"}))
