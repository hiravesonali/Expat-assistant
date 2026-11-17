# Repo Structure

## Decision: one monorepo, **one** Python project, one Node project

| Option | Pros | Cons |
|---|---|---|
| Separate Python projects per app (`backend/`, `ingestion/`, `evals/`, `apps/admin/`), each with its own `pyproject.toml` (or a uv workspace) | Clean boundaries. Mirrors microservices. | Shared code (schemas, retrievers, config) needs a shared package and workspace wiring. Much overhead for a 10-day sprint and someone new to Python packaging. |
| **One uv project, `backend/`, with one importable package `expat`, plus several entry points** ✅ | The API, ingestion CLI, Streamlit admin and evals all import *the same* retrieval code, so the debugger shows exactly what production does. One lockfile and one venv. | The package is larger and boundaries are enforced by folder discipline rather than packaging. |
| uv **workspace** (`backend/packages/core`, `backend/apps/api`, …) | Real package boundaries. Good stepping stone to Sprint 3. | Worth it later, not now. |

**Recommendation:** use one uv project. Split into a workspace in Sprint 3 if the agent work needs it. The important property for the review is that the **eval harness, the admin debugger and the API all call the same `retrieve()` function**, so the numbers you report describe the system users actually hit.

## Layout

```
expat-assistant/
├── README.md                  # pitch, demo GIF, eval results table, how to run
├── docs/                      # this planning set + ADRs
├── sources.yaml               # source registry (URLs, type, domain, cadence), the ingestion input
├── rules/
│   └── 2026.yaml              # versioned amounts/thresholds for tools (Kindergeld, fees…) with source + last_verified
├── data/                      # gitignored (except data/golden/)
│   ├── raw/                   # fetched snapshots: {source}/{url_hash}/{fetched_at}.html|xml|pdf
│   ├── processed/             # normalised JSONL documents (post-parse, pre-chunk)
│   ├── chroma/                # persistent Chroma directory
│   └── docstore.sqlite        # parents + ingestion manifest
├── backend/
│   ├── pyproject.toml         # uv-managed; Python 3.12; ruff + mypy + pytest configured
│   ├── uv.lock
│   ├── .env.example           # OPENROUTER_API_KEY, LANGSMITH_*, MODEL_* slugs, EMBEDDING_MODEL
│   ├── src/expat/
│   │   ├── config.py          # pydantic-settings Settings (env-driven model slugs, k values, flags)
│   │   ├── llm.py             # model factory (OpenRouter chat models, embeddings): one place to swap providers
│   │   ├── schemas/           # Pydantic: ChunkMetadata, UserProfile, QueryAnalysis, Citation, SSE events, tool I/O
│   │   ├── ingestion/
│   │   │   ├── cli.py         # `uv run expat-ingest --source bgb --since …`
│   │   │   ├── fetch.py       # polite fetcher (robots, rate limit, ETag/If-Modified-Since, snapshots)
│   │   │   ├── parsers/       # law_xml.py, guide_html.py, faq_html.py, pdf.py
│   │   │   ├── chunkers/      # per source_type
│   │   │   ├── enrich.py      # metadata, language detection, contextual headers, (stretch) EN summaries
│   │   │   └── pipeline.py    # idempotent upsert, orphan cleanup, manifest
│   │   ├── store/
│   │   │   ├── vectorstore.py # Chroma collection factory (name includes embedding model + schema version)
│   │   │   ├── docstore.py    # parent store (SQLite)
│   │   │   └── bm25.py        # BM25 index build/load (German analyser)
│   │   ├── rag/
│   │   │   ├── query_analysis.py  # one structured-output call: route, rewrite EN/DE, decompose, step-back, filters
│   │   │   ├── filters.py         # profile + analysis → Chroma `where` filter
│   │   │   ├── retrieve.py        # hybrid retrieval per query, RRF fusion, parent expansion, (rerank)
│   │   │   ├── generate.py        # answer agent: context + tools → cited answer
│   │   │   ├── prompts.py         # all prompts in one place (versioned, also pushed to the LangSmith prompt hub, stretch)
│   │   │   └── pipeline.py        # orchestration; emits typed events (used by the API *and* the debugger)
│   │   ├── tools/             # one module per tool, pure functions + LangChain @tool wrappers
│   │   ├── api/
│   │   │   ├── main.py        # FastAPI app factory, CORS, lifespan (load BM25, warm Chroma)
│   │   │   ├── routes.py
│   │   │   └── sse.py         # event model → SSE serialisation
│   │   └── safety.py          # out-of-scope / sensitive-topic policies, disclaimer levels
│   ├── admin/                 # Streamlit console: `uv run streamlit run admin/Home.py`
│   │   ├── Home.py            # ingestion status per source (reads manifest)
│   │   └── pages/  1_Collection_Browser.py  2_Retrieval_Debugger.py  3_Evals.py
│   ├── evals/
│   │   ├── golden/            # golden_v1.jsonl (committed)
│   │   ├── upload_dataset.py  # JSONL → LangSmith dataset (versioned)
│   │   ├── evaluators.py      # hit@k, MRR, citation checks, LLM-judge wrappers
│   │   ├── run_retrieval_eval.py   # ablation matrix → LangSmith experiments
│   │   ├── run_answer_eval.py
│   │   └── report.py          # pulls experiment results → markdown table for README
│   └── tests/                 # pytest: tools (pure functions!), chunkers, filter builder, SSE serialisation
└── apps/
    └── web/                   # Next.js (App Router, TS, Tailwind, shadcn/ui)
        ├── app/(chat)/page.tsx, app/(chat)/c/[id]/page.tsx, app/onboarding/page.tsx
        ├── app/api/chat/route.ts   # same-origin proxy → FastAPI (stream passthrough)
        ├── components/chat/        # MessageList, Composer, Markdown (+ citation remark plugin), StepsTimeline, ToolCard
        ├── components/sources/     # CitationChip, SourcePanel (sheet)
        ├── lib/sse.ts              # fetch + ReadableStream SSE parser → typed events
        ├── lib/store.ts            # conversations + profile in IndexedDB/localStorage
        └── types/events.ts         # generated from backend JSON Schema
```

## Conventions (Python tips for a TS developer)
- **Pydantic models play the role of TypeScript interfaces + zod.** Every boundary (SSE event, tool I/O, metadata, profile) is a Pydantic model.
- `uv add <pkg>`, `uv run pytest`, `uv run ruff check --fix`, `uv run mypy src`. Scripts are declared in `[project.scripts]`, the equivalent of `package.json` `bin`.
- Use the `src/` layout, so tests import the installed package rather than relative paths (avoids the classic "works from one folder only" bug).
- Keep tools as **pure functions** with typed inputs, plus a thin `@tool` wrapper. Unit tests need no LLM.
- Configuration comes only from `Settings` (pydantic-settings). No `os.getenv` scattered around the code.
