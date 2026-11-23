"""Chunk / parent data contracts shared by ingestion, store, retrieval and evals.

See docs/vector-db-design.md §4 for the rationale of every field.

doc_key convention (stable, human-readable, used by the golden dataset):
    law / regulation:  "<law_abbrev_lower>#<paragraph_lower>"     e.g. "bgb#573c", "aufenthg#18g", "bmg#17"
    web pages:         "<source_id>" or "<source_id>#<section_slug>" e.g. "muc-anmeldung#documents",
                       "familienportal-elterngeld#hoehe"
    section_slug = slugified heading or section_kind (lowercase ascii, '-' separated).
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class Domain(StrEnum):
    BUREAUCRACY = "bureaucracy"
    TENANCY = "tenancy"
    FAMILY = "family"
    HEALTH = "health"  # health insurance (Krankenversicherung)
    TAXES = "taxes"  # tax ID, tax classes
    FINANCE = "finance"  # stretch
    TRAVEL = "travel"  # stretch
    LAW = "law"  # stretch / general


class SourceType(StrEnum):
    LAW = "law"
    GUIDE = "guide"
    PROCEDURE = "procedure"
    FAQ = "faq"
    CHECKLIST = "checklist"
    TABLE = "table"
    REGULATION = "regulation"


class SectionKind(StrEnum):
    OVERVIEW = "overview"
    REQUIREMENTS = "requirements"
    DOCUMENTS = "documents"
    DEADLINES = "deadlines"
    FEES = "fees"
    STEPS = "steps"
    LEGAL_BASIS = "legal_basis"
    CONTACT = "contact"
    OTHER = "other"


class Jurisdiction(StrEnum):
    FEDERAL = "federal"
    STATE = "state"
    CITY = "city"


class Audience(StrEnum):
    ALL = "all"
    EU = "eu"
    NON_EU = "non_eu"
    STUDENT = "student"
    EMPLOYEE = "employee"
    FREELANCER = "freelancer"
    FAMILY = "family"
    BLUE_CARD = "blue_card"


class ChunkMetadata(BaseModel):
    """Metadata stored with every child chunk in Chroma (scalars + one list, see ADR-0001)."""

    chunk_id: str
    parent_id: str
    doc_id: str
    doc_key: str
    doc_version: str
    content_hash: str

    domain: Domain
    subtopic: str = ""
    source_type: SourceType
    section_kind: SectionKind = SectionKind.OTHER

    source_id: str  # id from sources.yaml
    source_name: str
    source_url: str
    title: str
    heading_path: str = ""
    legal_reference: str = ""  # e.g. "§ 573c Abs. 1 BGB"

    language: str = Field(pattern=r"^(de|en)$")
    alt_lang_url: str = ""
    is_machine_translated: bool = False

    jurisdiction: Jurisdiction
    state: str = ""  # "BY" or "" for federal
    city: str = ""  # "munich" or "" if not city-level
    applies_to: list[Audience] = Field(default_factory=lambda: [Audience.ALL], min_length=1)

    last_verified: date
    valid_from: date | None = None
    valid_until: date | None = None

    token_count: int = 0
    # The contextual header (`[BGB › § 573c …] [tenancy] [keywords]`) that was prepended for embedding/BM25.
    # Stored so the exact embedded/BM25 text can be reconstructed from the vector DB alone (debugging, admin).
    context_header: str = ""
    embedding_model: str = ""
    schema_version: int = 1


class ChunkRecord(BaseModel):
    """What ingestion emits (data/processed/chunks.jsonl) and the indexer consumes.

    `text` is the raw chunk; `embed_text` = contextual header + text (used for embeddings AND BM25).
    """

    text: str
    embed_text: str
    metadata: ChunkMetadata


class ParentRecord(BaseModel):
    """Larger context unit (a §, an H2 section, a procedure page) returned to the LLM.

    Emitted to data/processed/parents.jsonl; stored in the SQLite docstore by the indexer.
    """

    parent_id: str
    doc_key: str
    text: str
    title: str
    heading_path: str = ""
    source_url: str
    source_name: str
    legal_reference: str = ""
    language: str
    last_verified: date
    token_count: int = 0
