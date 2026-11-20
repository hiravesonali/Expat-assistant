# 🇩🇪 Expat Germany Assistant

An English-language assistant that helps expats in **Munich** (MVP persona: a non-EU Blue Card family) deal with registration, residence permits, renting and family benefits. It answers **only from official German sources**, with clickable citations and "last verified" dates, and does date and benefit calculations with tested tools instead of guessing.

> **Live demo:** https://expat-assistant.streamlit.app/
>
> Turing College AI Engineering, Sprint 2: advanced RAG with query translation, structured retrieval and tool calling.
> ⚠️ General information only. **Not legal or tax advice.**

## Highlights
- **Cross-lingual RAG:** English questions → German official sources (EN↔DE query rewriting, multi-query + RAG-Fusion, decomposition, step-back)
- **Structured retrieval:** rich metadata (domain, section kind, jurisdiction, audience, validity) with filters from the question *and* the user profile; § / Absatz-aware chunking with parent expansion
- **Hybrid search:** Chroma dense vectors + German BM25, fused with Reciprocal Rank Fusion
- **Tool calling:** tenancy notice periods (§ 573c BGB), statutory deadlines, Kindergeld/Elterngeld estimates, document checklists, Schengen 90/180
- **Evaluated:** golden dataset + LangSmith experiments (ablation table below)

## Status
🚧 Sprint in progress. See [`docs/PLAN.md`](docs/PLAN.md) and [`docs/milestones.md`](docs/milestones.md).

## Quick start
```bash
uv sync                           # Python 3.12 + all deps
cp .env.example .env              # add OpenRouter + LangSmith keys
uv run pytest                     # offline unit tests
uv run expat-ingest               # fetch official sources -> data/processed/ (~3 min, polite crawl)
uv run expat-index                # embed + build Chroma, BM25 and the parent store
uv run streamlit run app/Home.py  # chat UI (toggle "Live mode" in the sidebar)
```
make-it-in-germany.com blocks scripted downloads: save its two pages by hand to
`data/manual/miig-blue-card.html` and `data/manual/miig-family-reunification.html`
(URLs in `sources.yaml`), then run `uv run expat-ingest --source miig-blue-card miig-family-reunification`.

## Docs
| | |
|---|---|
| Plan and architecture | [`docs/PLAN.md`](docs/PLAN.md) |
| Vector DB design | [`docs/vector-db-design.md`](docs/vector-db-design.md) |
| RAG pipeline | [`docs/rag-pipeline.md`](docs/rag-pipeline.md) |
| Tools | [`docs/tools.md`](docs/tools.md) |
| Evaluation | [`docs/evaluation-plan.md`](docs/evaluation-plan.md) |
| Decisions (ADRs) | [`docs/adr/`](docs/adr/) |

## Data and licensing
Statutes come from gesetze-im-internet.de (public domain, § 5 UrhG). Portal content is used for non-commercial educational purposes, with attribution and deep links. **Scraped content and the vector index are not committed.** Rebuild them locally with the ingestion CLI. See [`docs/data-sources.md`](docs/data-sources.md).
