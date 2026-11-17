# ADR-0003: Next.js product UI + Streamlit internal admin

- **Status:** Proposed
- **Context:** The brief requires Streamlit *or* Next.js and a polished UI. The developer is a senior frontend/full-stack engineer (Vue/React/Next) who is new to Python. We also need internal tooling to debug retrieval and view eval results.

## Options
1. Next.js only.
2. Streamlit only.
3. **Next.js for users + Streamlit for internal tools.**

## Decision
Option 3, with a strict budget. Streamlit gets 2 MVP pages: the retrieval debugger and eval results. The collection browser and ingestion status are cuttable.

## Rationale
- The product UI is where polish matters: streaming, citation panels and the step timeline. That's Next.js, and it's the developer's differentiator.
- Internal tools need fast building and direct Python access. Streamlit **imports the same `expat.rag` package**, so the debugger shows exactly the production retrieval path with no extra API surface.
- This mirrors how real teams work: a customer product plus internal tools.

## Consequences
- Two UIs to maintain. Mitigation: Streamlit work starts only after the vertical slice (Day 8).
- Next.js needs a typed SSE client. Its types are generated from the Pydantic JSON Schema to prevent drift.
- Next.js proxies to FastAPI via a route handler (same origin, so no CORS in production).
