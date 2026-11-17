# ADR-0006: OpenRouter with role-based, configurable models

- **Status:** Accepted (2026-11-17, user decision)
- **Context:** Budget is $10–30. We want to compare models and avoid lock-in. LangChain now recommends `ChatOpenRouter` (`langchain-openrouter`) over `ChatOpenAI` with a custom `base_url`, because provider-specific fields would otherwise be dropped.

## Decision
- All LLM and embedding calls go through OpenRouter: chat via `ChatOpenRouter`, embeddings via the OpenAI-compatible `/api/v1/embeddings` endpoint.
- There are three roles, each configured by an env var:
  - `MODEL_ANALYSIS`: cheap, supports structured outputs.
  - `MODEL_ANSWER`: supports tool calling.
  - `MODEL_JUDGE`: from a different model family, used only in evals.
- A single `llm.py` factory creates the models. No other module imports provider classes.

## Consequences
- Structured-output and tool support varies by model and by provider endpoint. Filter models on `supported_parameters` and set `require_parameters: true`. On Day 1, smoke-test each chosen model with one tool call and one structured output.
- One key and one bill. Cost per run is visible in OpenRouter and LangSmith.
- Model choice becomes an eval question ("is the cheap model good enough?") rather than an opinion.
