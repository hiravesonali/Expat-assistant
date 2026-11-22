"""Model factories: the ONLY module that imports provider classes (ADR-0006).

Every other module asks for "the analysis model" or "the embeddings", never for a vendor class.
Swapping a model is then a `.env` change (MODEL_ANALYSIS=..., EMBEDDING_MODEL=...) plus an eval run.

Two things live here:

* `get_chat_model(role)` -> `ChatOpenRouter` configured from Settings.
* `get_embeddings()` -> an `EmbeddingAdapter` around an OpenRouter-backed `Embeddings`.
  The adapter exists because embedding models disagree on how queries and documents must be
  formatted (Qwen3 wants an instruction on the query side only, E5 wants `query:` / `passage:`).
  Getting this wrong silently costs recall, so we make it explicit and unit-tested.
"""

from __future__ import annotations

import re
from typing import Any, Literal

import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from expat.config import Settings, get_settings

Role = Literal["analysis", "answer", "judge"]
EmbeddingBackend = Literal["openai", "httpx"]

APP_TITLE = "Expat Germany Assistant"

QWEN3_QUERY_INSTRUCTION = (
    "Instruct: Given a question, retrieve German administrative or legal passages that answer it\nQuery: "
)


class MissingApiKeyError(RuntimeError):
    """Raised when a model is requested but OPENROUTER_API_KEY is not configured."""


def _require_key(settings: Settings) -> SecretStr:
    if settings.openrouter_api_key is None:
        raise MissingApiKeyError("OPENROUTER_API_KEY is not set (put it in .env). Offline tests use fake embeddings.")
    return settings.openrouter_api_key


# --------------------------------------------------------------------------------------------- chat


# Output caps per role, well above real outputs (analysis JSON ~0.5-1k tokens, answers ~0.3-0.8k, verdicts ~0.2k).
# Without a cap OpenRouter reserves credit for the model's FULL output limit on every call (32k for gpt-4.1-mini,
# 64k for Haiku 4.5) and rejects requests with "402 payment required" once the key's remaining limit is lower,
# long before the money is actually used up (seen in the eval run of 2026-11-22).
MAX_OUTPUT_TOKENS: dict[Role, int] = {"analysis": 3000, "answer": 2500, "judge": 1024}


def model_slug_for(role: Role, settings: Settings | None = None) -> str:
    """Map a role to the configured OpenRouter model slug (kept separate so it is testable without a key)."""
    s = settings or get_settings()
    return {"analysis": s.model_analysis, "answer": s.model_answer, "judge": s.model_judge}[role]


def get_chat_model(role: Role, settings: Settings | None = None, **kwargs: Any) -> BaseChatModel:
    """Create a `ChatOpenRouter` for one of the three roles.

    `temperature=0` is the default because every role here (structured analysis, grounded answers,
    judging) wants reproducibility over creativity; callers can override it via `**kwargs`
    (any `ChatOpenRouter` field, e.g. `max_tokens`, `openrouter_provider={"require_parameters": True}`).
    """
    # Imported lazily so `import expat.llm` stays cheap for modules that only need embeddings.
    from langchain_openrouter import ChatOpenRouter

    s = settings or get_settings()
    params: dict[str, Any] = {
        "model": model_slug_for(role, s),
        "api_key": _require_key(s),
        "base_url": s.openrouter_base_url,
        "app_title": APP_TITLE,
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS[role],
    }
    params.update(kwargs)
    return ChatOpenRouter(**params)


# ---------------------------------------------------------------------------------------- embeddings


class OpenRouterEmbeddings(Embeddings):
    """Minimal client for OpenRouter's OpenAI-compatible `POST /embeddings` endpoint.

    Why it exists: `langchain-openrouter` has no embeddings class, and `OpenAIEmbeddings` pointed at
    OpenRouter is the documented route but could not be verified without an API key. This ~30-line
    fallback has no tokenizer assumptions, no base64 decoding, and is fully testable offline via
    `httpx.MockTransport`.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        batch_size: int = 64,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.batch_size = batch_size
        self._client = client or httpx.Client(timeout=60.0)
        self._url = base_url.rstrip("/") + "/embeddings"
        self._headers = {"Authorization": f"Bearer {api_key}", "X-Title": APP_TITLE}

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            resp = self._client.post(
                self._url,
                headers=self._headers,
                json={"model": self.model, "input": batch, "encoding_format": "float"},
            )
            resp.raise_for_status()
            # The API may return items out of order; `index` is the source of truth.
            data = sorted(resp.json()["data"], key=lambda item: item["index"])
            vectors.extend(item["embedding"] for item in data)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


class EmbeddingAdapter(Embeddings):
    """Wraps any `Embeddings` and applies the model-specific query/document prefixes.

    It also carries `model_name`, which the vector store writes into the collection metadata and
    asserts at query time: querying a Qwen3 index with bge-m3 vectors "works" but returns garbage.
    """

    def __init__(self, inner: Embeddings, model_name: str) -> None:
        self.inner = inner
        self.model_name = model_name
        self.query_prefix, self.document_prefix = prefixes_for(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents([self.document_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(self.query_prefix + text)


def prefixes_for(model_name: str) -> tuple[str, str]:
    """Return `(query_prefix, document_prefix)` for an embedding model slug.

    * Qwen3-Embedding: instruction on queries only (model card); documents are embedded raw.
    * (multilingual-)E5: trained with `query: ` / `passage: `; without them quality drops noticeably.
    * Everything else (bge-m3, OpenAI): no prefixes.
    """
    name = model_name.lower()
    if "qwen3-embedding" in name:
        return QWEN3_QUERY_INSTRUCTION, ""
    if re.search(r"(^|[-_/])e5([-_]|$)", name):
        return "query: ", "passage: "
    return "", ""


def get_embeddings(
    settings: Settings | None = None,
    model: str | None = None,
    backend: EmbeddingBackend = "openai",
) -> EmbeddingAdapter:
    """Create the embedder for `model` (default: `settings.embedding_model`) via OpenRouter.

    backend="openai" (default) uses `langchain_openai.OpenAIEmbeddings` with
    `check_embedding_ctx_length=False` (send raw text, not tiktoken ids, which non-OpenAI models
    don't understand) and `encoding_format="float"` (avoid the client's base64 default).
    backend="httpx" uses our own `OpenRouterEmbeddings` if the first one misbehaves.
    """
    s = settings or get_settings()
    slug = model or s.embedding_model
    key = _require_key(s)
    inner: Embeddings
    if backend == "openai":
        from langchain_openai import OpenAIEmbeddings

        inner = OpenAIEmbeddings(
            model=slug,
            openai_api_base=s.openrouter_base_url,  # field names (not the aliases) keep mypy happy
            openai_api_key=key,
            check_embedding_ctx_length=False,
            model_kwargs={"encoding_format": "float"},
            default_headers={"X-Title": APP_TITLE},
        )
    else:
        inner = OpenRouterEmbeddings(model=slug, api_key=key.get_secret_value(), base_url=s.openrouter_base_url)
    return EmbeddingAdapter(inner, model_name=slug)
