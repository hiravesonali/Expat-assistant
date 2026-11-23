# Plan: from Munich to Germany-wide (branch `feature/germany-wide`)

> Status: phases 1, 2 and 4 done and merged (2026-11-22). Phase 3 (more nationwide topics) built on branch
> `feat/nationwide-topics` (2026-11-23): 13 sources ingested, 14 golden questions (`hea-`, `tax-`, `bur-026`–`032`).
> Pending (needs OpenRouter credit): rebuild + publish the index, rerun retrieval and answer evals, then merge.
> Phase 3 notes: the 3-year citizenship fast track was abolished on 30.10.2025, so BAMF's stale English
> naturalisation page is excluded. `law_xml` now reads requested Anlagen (`include_annexes`, FeV Anlage 11
> country list) and drops EStG sentence numbers.
> Results: docs/evaluation-plan.md, "Germany-wide evaluation". Started 2026-11-22. Decided with the product owner: cities **Berlin, Hamburg,
> Frankfurt am Main, Köln, Stuttgart** (+ Munich), tagline **"Your guide to settling in Germany"**, and a
> **follow-up question when the city matters but is unknown**. Merged to `main` only after the evals show
> no regression; the review submission stays on `main` until then.

## Why this is mostly additive
87% of the corpus (814 / 941 chunks, 2026-11-22) is federal law or federal portals and already valid
everywhere. Chunks already carry `jurisdiction` / `state` / `city`, retrieval already hard-filters
`city ∈ {user city, ""}` and `state ∈ {user state, ""}` (ADR-0001), and the deadline tools already take a
state for public holidays. What is missing: local sources for the new cities, a way to know the user's
location per question, and tests that a Berlin question never gets Munich rules.

## Phases
| # | What | Done when |
|---|---|---|
| 1 | **Location-aware core.** `expat/places.py` (6 supported cities, 16 states, aliases like Köln/Cologne, "Frankfurt (Oder)" is not Frankfurt am Main). Location per question: places named in the question > profile > unknown. Unknown → **federal + nationwide sources only** (no Munich leakage). Query analysis flags `location_dependent`; if the location is unknown, the assistant asks "Which city do you live in?" with one-click city buttons, then answers the original question. Profile: city/state pickers (supported cities + "other city"), no Munich default. Copy: "settling in Germany". | unit + app tests, golden dev retrieval unchanged |
| 2 | **Local sources for 5 cities + their states.** Per city: Anmeldung, foreign office / Blue Card, Kita, Mietspiegel; per state (BE, HH, HE, NW, BW): rent-cap regulation. Discovery and verification by a research pass (`docs/research/`), then site profiles, ingestion, indexing. Check whether verwaltung.bund.de serves local descriptions (one parser for many cities). | ingestion report, sources verified |
| 3 | **More nationwide topics** (health insurance, citizenship 2024 law, driving licence, tax ID / tax class). | sources ingested |
| 4 | **Evaluation.** ~30 new golden questions (per city + cross-city leakage + "which city?" behaviour), fresh holdout, rerun retrieval ablation + answer evals, update README numbers. | no regression on old holdout, leakage = 0 |

## Location rules (phase 1)
- City named in the question (also German forms: München, Köln) → filter to that city/state + nationwide.
  Several cities ("moving from Berlin to Munich") → all of them.
- Unsupported city ("Leipzig") → its state if known, federal sources, and an honest "I have no
  city-specific sources for Leipzig; check your local Bürgeramt".
- Nothing named → profile city/state; if unset and the question is location-dependent → ask.
- Not location-dependent (e.g. Kindergeld amount, BGB notice periods) → answer from federal sources, no question.

## Review angle
This shows the evaluation criteria directly: structured retrieval (jurisdiction metadata as hard filters),
a conversational clarification step, a knowledge base designed to scale, and measured no-regression.
