# ADR-0008: Always-retrieve pipeline + agentic tool calling; numbers only from tools or sources

- **Status:** Proposed
- **Context:** The assistant must combine RAG and tools. Wrong amounts, deadlines or § references are the most harmful failure mode. LangChain 1.x offers `create_agent` with middleware.

## Options
1. A pure agent, where retrieval is just one tool the model may or may not call.
2. A fixed chain with no autonomy, where tools are triggered by intent classification.
3. **Hybrid:** retrieval always runs (deterministic and evaluated), followed by a `create_agent` answer step with tools bound and a capped loop.

## Decision
Option 3. A prompt rule plus automated checks ensure that no number, date or § appears in an answer unless it is in a cited source or a tool output. Tool constants come from the versioned `rules/2026.yaml`.

## Rationale
- Reproducible retrieval makes the ablations meaningful and keeps the step timeline consistent.
- The model keeps real autonomy where it adds value: deciding *whether and which* tool to call, and asking for missing inputs.
- Date arithmetic and benefit formulas live in unit-tested Python, not in a model.
- Middleware (`@dynamic_prompt`, call limits, retries) is the same abstraction Sprint 3 agents use, so the migration path is simply "retrieval becomes a tool".

## Consequences
- Every turn pays for retrieval, even a message like "thanks!". Mitigation: `intent=chitchat` short-circuits the pipeline (cheap).
- The § validator and the citation validator run after generation, and their results are logged as LangSmith feedback.
