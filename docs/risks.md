# Risks and Open Questions

## Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **Scope creep** (7 domains, 2 UIs, 5 tools, evals in 10 days) | High | High | MVP = 3 domains. Vertical slice by Day 5. Cut lines in `milestones.md`. Streamlit kept to 1–2 pages. |
| 2 | **Python learning curve** (packaging, async, typing) slows the backend | Medium | Medium | One uv project, `src/` layout, Pydantic everywhere (familiar from zod). Ask for idiomatic-Python reviews. Async only in the API layer. |
| 3 | **Cross-lingual retrieval is weak** (EN query vs DE docs) | Medium | High | Day 3 embedding bake-off with numbers. German query rewrite. BM25 on German. Stretch: English parent summaries (multi-vector). |
| 4 | **Scraping is blocked or brittle** (bot protection on arbeitsagentur.de and make-it-in-germany.com; JS-rendered pages) | High | Medium | Prefer XML (gesetze-im-internet) and simple HTML portals (stadt.muenchen.de, familienportal, BayernPortal). Snapshot raw files to disk and never re-fetch during dev. Manually saved pages count as an acceptable fallback, documented in `sources.yaml` (`fetch_method: manual`). Respect robots.txt and rate-limit (1 req/s). |
| 5 | **Copyright/terms** of non-law content | Medium | Medium | Laws are public domain (§ 5 UrhG). For portal content: non-commercial educational use, store chunks with attribution + link, don't republish full pages, and the repo **does not commit** raw scraped content (`data/` gitignored). Prefer stadt.muenchen.de over muenchen.de (private-use-only terms). |
| 6 | **Hallucinated numbers / § references** | Medium | **Very high** (trust) | Numbers only from tools (rules YAML) or verbatim context. Citation validator. `must_include` evals. A post-generation check that every § in the answer appears in the cited chunks (stretch, cheap regex). |
| 7 | **Rules change** (Elterngeld reform, Rundfunkbeitrag 2027, Mietrechtsreform, Steuerklassen III/V) | High (over time) | Medium | `valid_from/until` + `last_verified` on every chunk and rule. Staleness banner (>90 days). A "known pending changes" note in `rules/2026.yaml` that the answer surfaces. |
| 8 | **OpenRouter model differences**: tool calling / structured output support varies by model and provider route | Medium | Medium | Choose models that list `tools` + `structured_outputs` support. Pin the provider order in OpenRouter settings. One `llm.py` factory makes swapping models a one-line change. Smoke test on Day 1. |
| 9 | **Latency** from multi-query fan-out (analysis → 4–8 retrievals → generation) | Medium | Medium | One combined analysis call. Retrievals run in parallel (`asyncio.gather` / `RunnableParallel`). Stream steps to the UI so the wait feels shorter. Measure p95 in the evals. |
| 10 | **LLM-judge unreliability** | Medium | Medium | A different, stronger judge model. Binary rubrics. Human-calibrate 15 samples and report agreement. |
| 11 | **Budget overrun** | Low | Low | Cheap model for analysis/judges where possible. Cache embeddings (content hash). LangSmith cost tracking. Ingestion re-embeds only changed chunks. |
| 12 | **Liability**: a user acts on a wrong answer | Low (demo) | High | Persistent disclaimer. Sensitive-topic redirects. Always link the official source + `last_verified`. "Check with the authority" fallback. |

## Open questions (decide by the given day)

| Question | Options | Decide by | Default if undecided |
|---|---|---|---|
| Exact review/submission date? | | Day 1 | 1 Dec 2026 |
| Which OpenRouter models for analysis / answer / judge? | See `PLAN.md` § Models | Day 1 (smoke test) | Cheap fast model for analysis, a mid-tier tool-calling model for answers, a stronger model as judge |
| Embedding model? | API (`text-embedding-3-small`/`-large`, Qwen3) vs local `bge-m3` | Day 3 (bake-off) | Winner of hit@5, ties go to API for simplicity |
| Does the course require deployment? | Yes / no / bonus | Day 1 (check the rubric) | Optional, Day 10 |
| Does the course mandate Streamlit specifically? | If yes, Streamlit becomes the primary UI | Day 1 (check the rubric) | Next.js primary, Streamlit admin |
| Answer language: always English, or mirror the user? | | Day 5 | Mirror the user's language (profile `answer_language` overrides) |
| Include **Taxes** in the MVP? | It is very relevant for Blue Card families (Steuerklassen III/V) | Day 6 checkpoint | Stretch #2 |
| Keep conversation history server-side? | Browser-only vs SQLite | Day 7 | Browser-only (privacy, simplicity) |
| Mietrechtsreform passes during the sprint? | | Ongoing | Keep current law + "pending reform" note |
