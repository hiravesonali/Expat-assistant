"""Chooses between the real pipeline (Live) and the scripted one (Demo).

The UI only ever calls `run_pipeline(...)` and `get_retrieval_backend(...)`, so swapping the backend
never touches page code. Expected real API (written in parallel in `expat.rag.pipeline`):

    build_default_pipeline() -> Pipeline
    Pipeline.run(question: str, history: list[dict[str, str]], profile: UserProfile | None)
        -> Iterator[PipelineEvent]
    # optional, used by the Retrieval Debugger:
    Pipeline.analyze(question: str, history: list[dict[str, str]]) -> RetrievalPlan
    Pipeline.retriever: Retriever   (expat.schemas.Retriever protocol)

`history` items are {"role": "user" | "assistant", "content": str}.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

import i18n
import streamlit as st
from demo_pipeline import DemoRetriever, demo_analyze, demo_run

from expat.schemas import ErrorEvent, PipelineEvent, RetrievalPlan, Retriever, UserProfile

DEMO, LIVE = "Demo", "Live"


def _secret(name: str) -> str | None:
    """Read a secret from st.secrets without crashing when no secrets.toml exists (local dev)."""
    try:
        value = st.secrets.get(name)
    except Exception:  # StreamlitSecretNotFoundError / FileNotFoundError when there is no secrets file
        return None
    return str(value) if value else None


def sync_secrets_to_env() -> None:
    """Copy known secrets into os.environ, because `expat.config.Settings` reads environment variables.

    (Community Cloud may already export root-level secrets as env vars; doing it explicitly is harmless.)
    """
    for name in ("OPENROUTER_API_KEY", "LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT",
                 "LANGSMITH_ENDPOINT", "MODEL_ANALYSIS", "MODEL_ANSWER", "EMBEDDING_MODEL",
                 "INDEX_REPO", "INDEX_REVISION", "HF_TOKEN",
                 "MAX_QUESTION_CHARS", "QUESTIONS_PER_HOUR", "DAILY_QUESTION_CAP"):  # fmt: skip
        if not os.environ.get(name) and (value := _secret(name)):
            os.environ[name] = value


def has_api_key() -> bool:
    if os.environ.get("OPENROUTER_API_KEY") or _secret("OPENROUTER_API_KEY"):
        return True
    try:  # .env is read by pydantic-settings, not by os.environ
        from expat.config import get_settings

        return get_settings().openrouter_api_key is not None
    except Exception:
        return False


@st.cache_resource(show_spinner=False)
def _import_builder() -> tuple[Callable[[], Any] | None, str]:
    """Lazy import: the real pipeline may not exist yet (or may fail to import). Cached per process."""
    try:
        from expat.rag.pipeline import build_default_pipeline  # type: ignore[import-not-found]
    except Exception as exc:  # ImportError, or any error raised while importing its dependencies
        return None, f"Real pipeline not available yet ({type(exc).__name__}: {exc})."
    return build_default_pipeline, ""


def live_status() -> tuple[bool, str]:
    """(available, reason-if-not). Cheap: does not build the pipeline."""
    if not has_api_key():
        return False, "Set OPENROUTER_API_KEY in .env or in the Streamlit secrets to enable Live mode."
    builder, reason = _import_builder()
    return builder is not None, reason


@st.cache_resource(show_spinner="Loading the retrieval index and models…")
def get_live_pipeline() -> Any:
    """Built ONCE per server process and shared by all sessions (Chroma client, BM25 index, LLM clients).

    `st.cache_resource` is like a module-level singleton that survives Streamlit's reruns. Without it, every
    click would reload the index.
    """
    sync_secrets_to_env()
    builder, reason = _import_builder()
    if builder is None:
        raise RuntimeError(reason)
    from expat.config import get_settings
    from expat.store.bundle import ensure_index

    get_settings.cache_clear()  # secrets were just copied into os.environ
    ensure_index()  # Community Cloud starts empty: download the index bundle once (ADR-0010)
    return builder()


def run_pipeline(
    mode: str, question: str, history: list[dict[str, str]], profile: UserProfile | None
) -> Iterator[PipelineEvent]:
    """Yield pipeline events. Live failures are converted into an ErrorEvent, never an exception."""
    if mode != LIVE:
        yield from demo_run(question, history, profile)
        return
    try:
        pipeline = get_live_pipeline()
        runner = pipeline.run if hasattr(pipeline, "run") else pipeline
        for event in runner(question=question, history=history, profile=profile):
            yield friendly_error(event) if isinstance(event, ErrorEvent) else event
    except Exception as exc:  # the UI must survive any backend failure
        yield friendly_error(ErrorEvent(code=type(exc).__name__, message=str(exc) or "Unknown error", retryable=True))


# Provider messages that mean "the API key has no budget left" (OpenRouter 402/403). Visitors can't fix that,
# and the raw text links to the key's management page, so it is replaced by an actionable message.
_BUDGET_ERRORS = ("key limit exceeded", "requires more credits", "insufficient credits", "payment required")
BUDGET_MESSAGE = i18n.STRINGS["en"]["budget"]


def friendly_error(event: ErrorEvent) -> ErrorEvent:
    if any(marker in event.message.lower() for marker in _BUDGET_ERRORS):
        return ErrorEvent(code="budget_exhausted", message=i18n.t("budget"), retryable=False)
    return event


def get_retrieval_backend(mode: str) -> tuple[Callable[[str], RetrievalPlan], Retriever, str]:
    """(analyze, retriever, label) for the Retrieval Debugger. Falls back to demo data when needed."""
    if mode == LIVE:
        try:
            pipeline = get_live_pipeline()
            retriever = getattr(pipeline, "retriever", None)
            if retriever is not None:
                analyze_fn = getattr(pipeline, "analyze", None)

                def analyze(q: str) -> RetrievalPlan:
                    return analyze_fn(q, []) if analyze_fn else RetrievalPlan.from_raw(q)

                return analyze, retriever, "Live index"
        except Exception as exc:
            st.toast(f"Live retriever unavailable, using demo data: {exc}", icon=":material/warning:")
    return demo_analyze, DemoRetriever(), "Demo corpus (8 chunks)"
