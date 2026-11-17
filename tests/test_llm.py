"""Offline tests for the model factories (no network: fake key, mocked HTTP)."""

import json

import httpx
import pytest
from langchain_core.embeddings import Embeddings

from expat.config import Settings
from expat.llm import (
    QWEN3_QUERY_INSTRUCTION,
    EmbeddingAdapter,
    MissingApiKeyError,
    OpenRouterEmbeddings,
    get_chat_model,
    get_embeddings,
    prefixes_for,
)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="sk-test", **kw)


class RecordingEmbeddings(Embeddings):
    def __init__(self) -> None:
        self.seen: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.seen.extend(texts)
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        self.seen.append(text)
        return [0.0]


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("qwen/qwen3-embedding-8b", (QWEN3_QUERY_INSTRUCTION, "")),
        ("intfloat/multilingual-e5-large", ("query: ", "passage: ")),
        ("baai/bge-m3", ("", "")),
        ("openai/text-embedding-3-small", ("", "")),
    ],
)
def test_prefixes_for(slug: str, expected: tuple[str, str]) -> None:
    assert prefixes_for(slug) == expected


def test_adapter_prefixes_queries_but_not_qwen_documents() -> None:
    inner = RecordingEmbeddings()
    adapter = EmbeddingAdapter(inner, "qwen/qwen3-embedding-8b")
    adapter.embed_query("notice period")
    adapter.embed_documents(["§ 573c BGB"])
    assert inner.seen == [QWEN3_QUERY_INSTRUCTION + "notice period", "§ 573c BGB"]


def test_chat_model_uses_role_slug() -> None:
    model = get_chat_model("judge", settings=_settings(model_judge="anthropic/claude-x"))
    assert model.model_name == "anthropic/claude-x"  # type: ignore[attr-defined]
    assert model.temperature == 0  # type: ignore[attr-defined]


def test_chat_model_kwargs_override() -> None:
    model = get_chat_model("answer", settings=_settings(), temperature=0.3, max_tokens=50)
    assert model.temperature == 0.3  # type: ignore[attr-defined]
    assert model.max_tokens == 50  # type: ignore[attr-defined]


def test_missing_key_raises() -> None:
    with pytest.raises(MissingApiKeyError):
        get_chat_model("analysis", settings=Settings(_env_file=None, openrouter_api_key=None))


def test_get_embeddings_openai_backend_constructs_offline() -> None:
    emb = get_embeddings(settings=_settings(), model="baai/bge-m3")
    assert emb.model_name == "baai/bge-m3"
    assert emb.inner.check_embedding_ctx_length is False  # type: ignore[attr-defined]


def test_httpx_backend_posts_openai_compatible_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/v1/embeddings"
        assert request.headers["authorization"] == "Bearer sk-test"
        # Return out of order to prove we sort by `index`.
        data = [{"index": i, "embedding": [float(i)]} for i in range(len(body["input"]))][::-1]
        return httpx.Response(200, json={"data": data})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    emb = OpenRouterEmbeddings("baai/bge-m3", "sk-test", batch_size=2, client=client)
    assert emb.embed_documents(["a", "b", "c"]) == [[0.0], [1.0], [0.0]]
    assert emb.embed_query("q") == [0.0]
