# Architecture Decision Records

Format: short [Nygard-style](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) ADRs (Context → Options → Decision → Consequences → How we'll know).
Status values: `Proposed` (planning), `Accepted` (validated by implementation/evals), `Superseded by ADR-xxxx`.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-single-collection-rich-metadata.md) | One Chroma collection with rich metadata + separate parent store | Proposed |
| [0002](0002-embedding-model.md) | Embedding model chosen by a bake-off: Qwen3-Embedding-8B | Accepted |
| [0003](0003-nextjs-plus-streamlit.md) | Next.js product UI + Streamlit internal admin | **Superseded by 0009** |
| [0004](0004-hybrid-search-own-bm25-rrf.md) | Hybrid search with own BM25 + RRF (local Chroma has no hybrid) | Proposed |
| [0005](0005-single-call-query-analysis.md) | Query translation as one structured-output call | Proposed |
| [0006](0006-openrouter-configurable-models.md) | OpenRouter with role-based, configurable models | Accepted |
| [0007](0007-stateless-backend-browser-profile.md) | Stateless backend; profile + history in the browser | Proposed |
| [0008](0008-deterministic-retrieval-agentic-tools.md) | Always-retrieve pipeline + agentic tool calling; numbers only from tools/sources | Proposed |
| [0009](0009-streamlit-primary-ui-and-deployment.md) | Streamlit as the primary UI; deployment mandatory (Streamlit Community Cloud) | Accepted |
| [0010](0010-deployed-index-bundle.md) | Deployed index: embedded Chroma + versioned bundle in a private HF dataset (Chroma Cloud shut down) | Accepted |
| [0011](0011-voice-cascade-stt-tts.md) | Voice as a cascade: speech-to-text → text pipeline → on-demand text-to-speech, via OpenRouter | Proposed |

Once a decision is validated, update its status and add a "Result" line with the actual numbers. That turns opinions into evidence.
