# ADR-0005: Query translation as one structured-output call

- **Status:** Proposed
- **Context:** We want several query-translation techniques: condensing with history, EN→DE rewriting, multi-query, decomposition, step-back, routing, and filter extraction. Done naively, each is its own LLM call or chain (e.g. `MultiQueryRetriever` and `SelfQueryRetriever` in `langchain_classic`).

## Options
1. A chain of specialised calls, one per technique.
2. **One `with_structured_output(QueryAnalysis)` call** that returns all of them.
3. An agent that decides which techniques to apply.

## Decision
Option 2.

## Rationale
- Latency and cost: 1 call instead of 5–6, on a cheap model.
- Consistency: decomposition, rewrites and filters are produced together, so they agree with each other.
- Debuggability: one typed object to show in the UI timeline, the Streamlit debugger and LangSmith.
- Evaluability: each field can be switched off in ablations. For example, ignoring `queries_de` measures the effect of cross-lingual rewriting.
- It generalises `SelfQueryRetriever` (filters from the question) and adds merging with the user profile.

## Consequences
- A large schema needs a model with reliable structured outputs. Use `method="json_schema", strict=True` and OpenRouter's `require_parameters: true`. If validation fails, fall back to the raw query only (graceful degradation).
- Prompt quality matters. Include 4–6 few-shot examples: one multi-domain, one legal/step-back, one out-of-scope.
