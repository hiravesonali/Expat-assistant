# Milestone Plan (10 working days)

> Assumes the review/submission is around **Tue 1 Dec 2026**. Shift the dates if your deadline differs, but keep the order.
> Fits your daily structure: morning = course content, **13:00–15:30 = build**, 15:30–16:30 = push + learning log. Evenings/weekend = buffer only (don't plan on them).
>
> **Rule of the sprint:** a vertical slice works end to end by **Day 5**. Everything after that improves something that already runs.

| Day | Date | Focus | Tasks | ✅ Done when… |
|---|---|---|---|---|
| 0 | Tue 17 Nov | Planning | This docs set. Create the GitHub repo. Get API keys (OpenRouter, LangSmith). | `docs/` committed. Keys in `.env`. |
| 1 | Wed 18 Nov | Skeleton + first data | `uv init` backend, FastAPI `/api/health`, `create-next-app` web. `Settings` + `llm.py` (OpenRouter chat). LangSmith tracing env vars. `sources.yaml` with MVP sources. Fetcher with robots check + raw snapshots. Download BGB + AufenthG + BMG XML. | One traced LLM call visible in LangSmith. `data/raw/` holds BGB/AufenthG/BMG XML + ≥10 guide pages. |
| 2 | Thu 19 Nov | Parse, chunk, store | `ChunkMetadata` schema. Law XML parser (§/Absatz). Guide HTML parser (heading tree → markdown). FAQ parser. Chunkers. Parent docstore (SQLite). Idempotent upsert into Chroma. Unit tests for chunkers. | `expat-ingest --all` runs twice with identical chunk counts (idempotent). ~1–3k chunks. A quick script prints the chunks for "§ 573c". |
| 3 | Fri 20 Nov | Embedding experiment + golden set v0 | Write **30 golden questions** (EN + some DE) with expected sources. Upload to LangSmith. Retrieval eval script (hit@5, MRR@10). Run the **embedding bake-off** (2–3 models, see ADR-0002). Pick the winner and write ADR-0002's result. | A table: model × hit@5 × MRR × cost × latency. Embedding decision made **with numbers**. |
| 4 | Mon 23 Nov | Advanced retrieval | `QueryAnalysis` structured output (route, EN+DE rewrites, decomposition, step-back, filters). Profile → `where` filter. BM25 (German analyser) + vector, RRF fusion, parent expansion. Ablation runs v1. | Ablation table: baseline vs +DE rewrite vs +multi-query vs +hybrid. At least one row beats the baseline. |
| 5 | Tue 24 Nov | Generation + streaming API | Answer prompt with `[S#]` citations + fallback. `/api/chat` SSE with all event types. `curl -N` demo. **Vertical slice works.** | `curl` streams steps → tokens → citations → done for 3 demo questions. Traces readable in LangSmith. |
| 6 | Wed 25 Nov | Tools | `rules/2026.yaml`. Tools: notice period, deadline, family benefits, Schengen, document checklist. Pytest per tool. Bind tools to the answer agent. Tool-selection cases in the golden set. | Pytest green. "When can I move out if I give notice today?" calls `calculate_tenancy_notice` and cites § 573c. |
| 7 | Thu 26 Nov | Next.js chat | Layout (sidebar + chat), SSE client, streaming markdown, citation chips → source panel, onboarding form from `/api/profile/schema`, persistent disclaimer. | You can onboard as "Blue Card family in Munich" and get a streamed, cited answer in the browser. |
| 8 | Fri 27 Nov | Transparency UI + admin | "How I got this answer" step timeline + tool cards. Conversation history (IndexedDB). Streamlit: retrieval debugger + collection browser + eval results page. | Demo flow works in both apps. A screenshot of each goes into the README. |
| 9 | Mon 30 Nov | Evals + hardening | Grow the golden set to 40–50 questions. Full answer eval (faithfulness, citation correctness, refusal, tool selection). Fix the 3 worst failure clusters. Re-run. Out-of-scope/sensitive tests. | Final results table (before/after fixes) in the README. No P0 bugs. |
| 10 | Tue 1 Dec | Ship + rehearse | README (pitch, architecture diagram, results, limitations). 2–3 min demo video. Optional deploy. Rehearse `docs/review-prep.md` (do a mock review with Claude). | Repo public, README complete, demo recorded, you can answer all 10 reviewer questions out loud. |

## Cut lines (if you fall behind)
Cut in this order, from first to last:
1. Streamlit collection browser (keep the retrieval debugger, which is the valuable page).
2. Conversation history sidebar (single-session chat is fine).
3. Schengen tool (lowest relevance to the Munich family persona).
4. Step-back prompting (keep the rewrites + decomposition).
5. Golden set stays at 30 instead of 50.

**Never cut:** cross-lingual rewriting, hybrid search, citations, the ablation table, tool calling. Those *are* the course requirements and your CV numbers.

## Stretch goals (ordered by value per hour)
1. **Reranker** (cross-encoder, `bge-reranker-v2-m3`) as one more ablation row.
2. **Taxes domain** (Steuerklassen, ELSTER basics, Anlage N) for the Blue Card persona.
3. **Letter drafter**: tenancy termination (Kündigung) in German + English explanation, as structured output.
4. **English parent summaries** (multi-vector) for better cross-lingual recall, as an ablation row.
5. 👍/👎 feedback → LangSmith feedback.
6. **Office finder** (Munich KVR / Ausländerbehörde, static JSON).
7. Deployment (Fly.io/Railway for FastAPI + Chroma volume, Vercel for web).
8. Domains: Finance (GKV/PKV, Rente), Travel (Schengen/visas for visiting parents), net salary via the official BMF calculator interface.
