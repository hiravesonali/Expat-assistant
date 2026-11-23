"""Central configuration. The only place that reads environment variables.

Usage:
    from expat.config import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# pydantic-settings reads .env into `Settings` only. Libraries that read os.environ themselves (LangSmith:
# LANGSMITH_API_KEY/ENDPOINT/TRACING/PROJECT) would not see it, so export it once at import time.
# override=False: real environment variables (Streamlit secrets, CI, tests/conftest.py) always win.
load_dotenv(REPO_ROOT / ".env", override=False)


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

    # --- Voice (expat/speech.py, ADR-0011): OpenRouter audio endpoints, same key ---
    voice_enabled: bool = True  # kill switch for the microphone and the "Listen" button (Live mode only)
    model_stt: str = "openai/whisper-large-v3-turbo"  # alternative: openai/gpt-4o-mini-transcribe
    model_tts: str = "google/gemini-3.8-flash-lite-tts"  # fallback: mistralai/voxtral-mini-tts-3-0
    tts_voice: str = "Kore"  # must be one of the model's supported_voices
    tts_pcm_sample_rate: int = 24000  # for models that return raw PCM (Gemini TTS: 24 kHz, 16-bit, mono)
    voice_max_seconds: int = Field(default=45, ge=5, le=300)  # longest spoken question
    tts_max_chars: int = Field(default=1200, ge=100)  # text-to-speech is priced per character
    listens_per_hour: int = Field(default=10, ge=1)  # "Listen" clicks per browser session
    daily_listen_cap: int = Field(default=100, ge=1)  # "Listen" clicks per day for the whole app

    # --- Storage ---
    data_dir: Path = REPO_ROOT / "data"
    schema_version: int = 1
    # Deployed index (ADR-0010): a private Hugging Face dataset repo holding data/chroma, data/bm25 and
    # docstore.sqlite. The app downloads it at startup when the files are missing (Community Cloud).
    index_repo: str | None = None  # e.g. "your-hf-name/expat-index"
    index_revision: str | None = None  # pin a commit/tag; None = latest
    hf_token: SecretStr | None = None

    # --- Retrieval defaults (overridable per call via RetrievalConfig) ---
    k_dense: int = 20
    k_sparse: int = 20
    k_final: int = 8
    rrf_c: int = 60
    context_token_budget: int = 6000

    # --- App ---
    history_turns: int = Field(default=6, ge=0, le=20)
    # Public-app guards (expat/guards.py). Override via env / Streamlit secrets, e.g. QUESTIONS_PER_HOUR=10.
    max_question_chars: int = Field(default=1000, ge=50)
    questions_per_hour: int = Field(default=20, ge=1)  # per browser session, Live mode only
    daily_question_cap: int = Field(default=300, ge=1)  # whole app per day, Live mode only
    # Prices of MODEL_ANALYSIS / MODEL_ANSWER (both gpt-4.1-mini) in USD per 1M tokens, for the cost estimate.
    price_in_per_mtok: float = 0.40
    price_out_per_mtok: float = 1.60
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
