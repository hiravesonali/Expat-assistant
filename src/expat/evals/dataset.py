"""Golden dataset: the Pydantic model for one example, the JSONL loader and the LangSmith upload.

Why a Pydantic model for a JSONL file? The golden set is hand-written, and a typo in a field name
("expected_source") would otherwise silently turn into "no expected sources" and inflate the metrics.
`extra="forbid"` + enums make every such mistake a loud error at load time (zod-style, for the TS reader).
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from expat.config import REPO_ROOT
from expat.schemas import Domain, UserProfile

GOLDEN_DIR = REPO_ROOT / "evals" / "golden"
DEFAULT_GOLDEN_PATH = GOLDEN_DIR / "golden_v1.jsonl"
DEFAULT_DATASET_NAME = "expat-golden-v1"

Split = Literal["dev", "holdout"]
Category = Literal["single_domain", "multi_domain", "numeric", "tool", "legal_lookup", "out_of_scope", "sensitive"]

# Maps the id prefix to the "primary slice" used in per-slice tables.
SLICE_BY_PREFIX: dict[str, str] = {
    "bur": "bureaucracy",
    "ten": "tenancy",
    "fam": "family",
    "hea": "health",
    "tax": "taxes",
    "mul": "multi_domain",
    "oos": "out_of_scope",
}


class ExpectedSource(BaseModel):
    """A source the retriever should find, at doc_key level (stable across re-chunking)."""

    model_config = ConfigDict(extra="forbid")

    # Lowercase, no spaces: "bgb#573c", "muc-anmeldung", "fp-elterngeld#hoehe".
    doc_key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*(#[a-z0-9][a-z0-9-]*)?$")
    required: bool = True

    @property
    def source_id(self) -> str:
        """The part before '#', i.e. the id in docs/conventions.md / sources.yaml."""
        return self.doc_key.split("#", 1)[0]


class ExpectedTool(BaseModel):
    """The tool the answer agent should call, with the arguments we can know from the question alone."""

    model_config = ConfigDict(extra="forbid")

    name: str
    args_subset: dict[str, Any] = Field(default_factory=dict)


class GoldenExample(BaseModel):
    """One golden question. Field semantics: evals/golden/README.md and docs/evaluation-plan.md §1."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^(bur|ten|fam|hea|tax|mul|oos)-\d{3}$")
    split: Split
    question: str = Field(min_length=5)
    language: Literal["en", "de"]
    profile: UserProfile
    domains: list[Domain] = Field(min_length=1)
    category: Category
    expected_sources: list[ExpectedSource] = Field(default_factory=list)
    expected_tool: ExpectedTool | None = None
    reference_answer: str = Field(min_length=10)
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    should_refuse: bool = False
    # The right response is the follow-up "Which city do you live in?" (location-dependent question, no city in
    # the question or profile). No expected sources; scored only on asking (docs/plan-germany-wide.md).
    expect_clarification: bool = False
    notes: str = ""

    @model_validator(mode="after")
    def _check_consistency(self) -> "GoldenExample":
        """Cross-field rules that a JSON schema alone can't express."""
        refusal_category = self.category in ("out_of_scope", "sensitive")
        if self.should_refuse != refusal_category:
            raise ValueError(f"{self.id}: should_refuse must be true exactly for out_of_scope/sensitive categories")
        if self.should_refuse and (self.expected_sources or self.expected_tool):
            raise ValueError(f"{self.id}: refusal examples must not expect sources or tools")
        if self.expect_clarification and (self.should_refuse or self.expected_sources or self.profile.city):
            raise ValueError(f"{self.id}: clarification examples: no refusal, no expected sources, no profile city")
        if not self.should_refuse and not self.expect_clarification and not self.required_doc_keys:
            # Without a required key, hit@k is undefined and the example would silently drop out of retrieval evals.
            raise ValueError(f"{self.id}: answerable examples need at least one required expected source")
        if self.category == "tool" and self.expected_tool is None:
            raise ValueError(f"{self.id}: category 'tool' needs an expected_tool")
        if self.slice == "out_of_scope" and not self.should_refuse:
            raise ValueError(f"{self.id}: 'oos-' ids are reserved for refusal examples")
        return self

    @property
    def slice(self) -> str:
        """Primary slice (one per example), derived from the id prefix so it can't drift from the file layout."""
        return SLICE_BY_PREFIX[self.id.split("-", 1)[0]]

    @property
    def required_doc_keys(self) -> list[str]:
        return [s.doc_key for s in self.expected_sources if s.required]

    @property
    def all_doc_keys(self) -> list[str]:
        return [s.doc_key for s in self.expected_sources]

    def tags(self) -> list[str]:
        """All slices this example belongs to, for per-slice breakdowns.

        One primary slice plus cross-cutting tags (language, category, tool). This is what lets the report say
        e.g. "BM25 helps legal_lookup most" or "German rewriting matters for lang:en".
        """
        tags = [self.slice, f"lang:{self.language}", f"category:{self.category}"]
        if self.expected_tool is not None:
            tags.append("tool")
        return tags

    def to_langsmith_example(self) -> dict[str, Any]:
        """Shape expected by `Client.create_examples(examples=[...])` (langsmith 0.14 ExampleCreate).

        inputs  = what the target sees (question + profile);
        reference_outputs = everything evaluators need;
        metadata/split = for filtering and per-slice analysis in the LangSmith UI.
        """
        reference = self.model_dump(
            mode="json",
            include={
                "expected_sources",
                "expected_tool",
                "reference_answer",
                "must_include",
                "must_not_include",
                "should_refuse",
            },
        )
        return {
            "inputs": {"question": self.question, "profile": self.profile.model_dump(mode="json")},
            "reference_outputs": {"id": self.id, **reference},
            "metadata": {
                "id": self.id,
                "slice": self.slice,
                "language": self.language,
                "category": self.category,
                "domains": [d.value for d in self.domains],
                "tags": self.tags(),
            },
            "split": self.split,
        }


class GoldenDatasetError(ValueError):
    """Raised with file + line number, so a broken golden line is easy to find."""


def load_golden(path: Path = DEFAULT_GOLDEN_PATH, split: Split | None = None) -> list[GoldenExample]:
    """Load and validate a golden JSONL file. Optionally filter to one split.

    Validation happens on the WHOLE file before filtering, so a broken holdout line fails a dev run too.
    """
    examples: list[GoldenExample] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                example = GoldenExample.model_validate_json(line)
            except ValidationError as exc:
                raise GoldenDatasetError(f"{path.name}:{line_no}: {exc}") from exc
            if example.id in seen:
                raise GoldenDatasetError(f"{path.name}:{line_no}: duplicate id {example.id}")
            seen.add(example.id)
            examples.append(example)
    if split is None:
        return examples
    return [e for e in examples if e.split == split]


class _DatasetClient(Protocol):
    """The subset of `langsmith.Client` we use. A Protocol lets tests pass a fake without a network."""

    def has_dataset(self, *, dataset_name: str) -> bool: ...

    def create_dataset(
        self, dataset_name: str, *, description: str | None = ..., metadata: dict | None = ...
    ) -> Any: ...

    def create_examples(self, *, dataset_id: Any, examples: list[dict[str, Any]]) -> Any: ...


def upload_dataset(
    name: str = DEFAULT_DATASET_NAME,
    path: Path = DEFAULT_GOLDEN_PATH,
    client: _DatasetClient | None = None,
) -> str:
    """Create a LangSmith dataset from the golden JSONL and return its id.

    We refuse to overwrite an existing dataset: experiments are only comparable on the same dataset version,
    so a changed golden set gets a new name (expat-golden-v2) instead of being silently mutated.
    """
    examples = load_golden(path)
    if client is None:
        from langsmith import Client  # imported lazily so offline code paths don't need LangSmith config

        client = Client()
    if client.has_dataset(dataset_name=name):
        raise GoldenDatasetError(f"LangSmith dataset {name!r} already exists; bump the version instead of overwriting")
    dataset = client.create_dataset(
        name,
        description=f"Expat Germany Assistant golden set ({path.name}, {len(examples)} examples)",
        metadata={"source_file": path.name, "n_examples": len(examples)},
    )
    client.create_examples(dataset_id=dataset.id, examples=[e.to_langsmith_example() for e in examples])
    return str(dataset.id)


def by_id(examples: Iterable[GoldenExample]) -> dict[str, GoldenExample]:
    return {e.id: e for e in examples}
