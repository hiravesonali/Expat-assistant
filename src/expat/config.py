"""Central configuration. The only place that reads environment variables.

Usage:
    from expat.config import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OpenRouter (LLMs + embeddings), see ADR-0006 ---
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_analysis: str = "openai/gpt-4.1-mini"  # placeholder: pick on Day 1 (structured_outputs + tools)
    model_answer: str = "openai/gpt-4.1-mini"  # placeholder: pick on Day 1 (tools)
    model_judge: str = "anthropic/claude-sonnet-4.5"  # placeholder: different family than answer model
    embedding_model: str = "qwen/qwen3-embedding-8b"  # ADR-0002 hypothesis; bake-off decides

    # --- Storage ---
    data_dir: Path = REPO_ROOT / "data"
    schema_version: int = 1

    # --- Retrieval defaults (overridable per call via RetrievalConfig) ---
    k_dense: int = 20
    k_sparse: int = 20
    k_final: int = 8
    rrf_c: int = 60
    context_token_budget: int = 6000

    # --- App ---
    history_turns: int = Field(default=6, ge=0, le=20)
    staleness_days: int = 90

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def docstore_path(self) -> Path:
        return self.data_dir / "docstore.sqlite"

    @property
    def bm25_dir(self) -> Path:
        return self.data_dir / "bm25"

    @property
    def collection_name(self) -> str:
        """`expat__<embedding-model-slug>__s<schema>`, see ADR-0001."""
        slug = self.embedding_model.split("/")[-1].replace(".", "-").lower()
        return f"expat__{slug}__s{self.schema_version}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
