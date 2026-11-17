# Architecture Decision Records

Format: short [Nygard-style](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) ADRs (Context → Options → Decision → Consequences → How we'll know).
Status values: `Proposed` (planning), `Accepted` (validated by implementation/evals), `Superseded by ADR-xxxx`.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-single-collection-rich-metadata.md) | One Chroma collection with rich metadata + separate parent store | Proposed |
| [0002](0002-embedding-model.md) | Embedding model chosen by a bake-off (hypothesis: Qwen3-Embedding-8B) | Proposed, decided Day 3 |
| [0003](0003-nextjs-plus-streamlit.md) | Next.js product UI + Streamlit internal admin | Proposed |
| [0004](0004-hybrid-search-own-bm25-rrf.md) | Hybrid search with own BM25 + RRF (local Chroma has no hybrid) | Proposed |
| [0005](0005-single-call-query-analysis.md) | Query translation as one structured-output call | Proposed |
| [0006](0006-openrouter-configurable-models.md) | OpenRouter with role-based, configurable models | Accepted |
| [0007](0007-stateless-backend-browser-profile.md) | Stateless backend; profile + history in the browser | Proposed |
| [0008](0008-deterministic-retrieval-agentic-tools.md) | Always-retrieve pipeline + agentic tool calling; numbers only from tools/sources | Proposed |

Once a decision is validated, update its status and add a "Result" line with the actual numbers. That turns opinions into evidence.
