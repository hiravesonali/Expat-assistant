# ADR-0009: Streamlit as the primary UI; deployment is mandatory

- **Status:** Accepted (2026-11-17, user decision). **Supersedes ADR-0003**, and amends ADR-0007 (storage moves from the browser to the Streamlit session).
- **Context:** The course rubric requires a **deployed** app. In 10 days, deploying Next.js (Vercel) + FastAPI (with a persistent Chroma volume) means two deployments, CORS/proxying and SSE plumbing. Streamlit is explicitly allowed by the brief and imports the Python pipeline directly.

## Options
1. Streamlit primary (chat + admin pages), FastAPI/Next.js dropped from the MVP.
2. Streamlit chat → deployed FastAPI over SSE.
3. Keep Next.js + FastAPI.

## Decision
Option 1. One Streamlit multipage app:
- `app/Home.py`: the chat (onboarding/profile in the sidebar, streamed answer via `st.write_stream`, a "How I got this answer" timeline via `st.status`/expanders, citation list with source dialogs, persistent disclaimer).
- `app/pages/`: Retrieval Debugger, Collection Browser, Evals, Ingestion Status.

The pipeline is a **generator of typed events** (`expat.schemas.events`). The UI renders the events. A later FastAPI layer would serialise the *same* events as SSE (`docs/api-contract.md` becomes the stretch-goal contract).

## Deployment
- **Target:** Streamlit Community Cloud (free, deploys from GitHub). Fallback: Hugging Face Spaces (Streamlit SDK). Secrets go in Streamlit secrets, not `.env`.
- **Sub-decision resolved by [ADR-0010](0010-deployed-index-bundle.md): embedded Chroma + index bundle downloaded at startup (Chroma Cloud is shutting down).** Original question: where the deployed index lives. The filesystem is ephemeral and we don't commit scraped content.
  - a. **Chroma Cloud** for the deployed index (same `langchain-chroma` API, config switch). *Recommended if the free tier fits.*
  - b. Build the index at first boot from `sources.yaml` (slow, depends on government sites being reachable from US servers).
  - c. Download a pre-built index artifact at startup (simple, but redistributes chunks).
- Admin pages are hidden behind a simple password from secrets in the deployed app.

## Consequences
- Lose: Next.js polish as a frontend showcase. It is now stretch goal #1 after submission (the event contract makes it a pure frontend task).
- Gain: one deployment, one language, faster iteration. The debugger and evals live next to the chat.
- Profile and history live in `st.session_state` (session only, never persisted). The privacy properties of ADR-0007 still hold.
- Streamlit reruns the script on every interaction, so heavy objects (Chroma client, BM25 index, models) must be cached with `st.cache_resource`.
