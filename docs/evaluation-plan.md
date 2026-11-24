# Evaluation Plan

> Goal: **numbers you can put in the review and on your CV**, e.g.
> *"Cross-lingual query rewriting + hybrid BM25/vector search raised hit@5 from 0.52 to 0.86 on a 50-question bilingual golden set; faithfulness 0.93 (LLM-judge); 100% refusal on out-of-scope questions."*
> (Illustrative numbers only. Yours will come from the runs.)

Course requirement mapping: evals are not listed explicitly in the Sprint 2 brief, but they are how you **prove** the "advanced RAG" claim. Treat them as **required for a strong review**.

## 1. Golden dataset

### Size and coverage (target: 50; minimum: 30)
| Slice | # | Why |
|---|---|---|
| Bureaucracy (Anmeldung, Blue Card, Ausländerbehörde Munich, Rundfunkbeitrag) | 12 | Core persona |
| Tenancy (notice, deposit, rent increase, Mietpreisbremse, Nebenkosten) | 12 | Law-heavy, tests § lookup + BM25 |
| Family (Kindergeld, Elterngeld, Kita Munich) | 10 | Amounts, tests numbers + tools |
| Multi-domain ("moving to Munich with 2 kids on a Blue Card") | 5 | Tests decomposition |
| German-language questions | 6 (across the domains above) | Tests the DE→DE path |
| Tool-required (calculations) | 6 (overlaps with the above) | Tests tool selection |
| Out-of-scope / sensitive (asylum case, criminal law, "write my tax return", medical) | 5 | Tests refusal/redirect |

Write questions **the way users actually ask them**: vague, with English approximations of German terms ("registration thing", "kinder money"). That is where query translation proves its worth.

### Format: `backend/evals/golden/golden_v1.jsonl`
```jsonc
{
  "id": "ten-007",
  "question": "I've rented my flat in Munich for 6 years. How much notice does my landlord have to give me?",
  "language": "en",
  "profile": {"city": "munich", "citizenship": "non_eu", "residence_status": "blue_card", "housing": "renting"},
  "domains": ["tenancy"],
  "category": "single_domain",          // single_domain | multi_domain | numeric | tool | legal_lookup | out_of_scope | sensitive
  "expected_sources": [                 // matched at SOURCE/SECTION level, not chunk_id (chunk ids change when chunking changes)
    {"doc_key": "bgb#573c", "required": true},
    {"doc_key": "bgb#573", "required": false}
  ],
  "expected_tool": {"name": "calculate_tenancy_notice", "args_subset": {"party": "landlord", "tenancy_years": 6}},
  "reference_answer": "Six months: the landlord's notice period extends from 3 to 6 months after 5 years of tenancy (§ 573c (1) BGB). The landlord also needs a legitimate interest (§ 573 BGB).",
  "must_include": ["6 months", "573c"],   // cheap deterministic checks
  "must_not_include": [],
  "should_refuse": false,
  "notes": "Tests the § lookup via BM25 + the tool"
}
```
`doc_key` is a stable, human-readable section key (`bgb#573c`, `muenchen:anmeldung`, `familienportal:elterngeld#hoehe`) that is also stored in the chunk metadata. This is the trick that keeps the eval stable across re-chunking experiments.

### Process
1. Draft the questions yourself (you know the expat pain points). Optionally use an LLM to propose paraphrases, but **you verify every expected source by hand**.
2. Store the JSONL in git (reviewable diffs). `upload_dataset.py` pushes it to a LangSmith dataset with a version tag. Splits: `dev` (35) / `holdout` (15). **Tune only on `dev`** and report the holdout numbers too. Reviewers love this, and it shows you understand overfitting.

## 2. Metrics

### Retrieval (deterministic, cheap, run often)
| Metric | Definition | Notes |
|---|---|---|
| **hit@k** (k=5) | ≥1 required `doc_key` among the top-k fused results | Headline metric |
| **recall@k** (k=10) | Fraction of required `doc_key`s found in the top-k | Matters for multi-domain questions |
| **MRR@10** | 1/rank of the first relevant result | Rewards ranking quality (reranker) |
| Filter precision | Share of retrieved chunks whose metadata is consistent with the profile (e.g. no EU-only chunks for a non-EU profile) | Shows structured retrieval works |
| Latency p50/p95 | Time for the retrieval stage | Cost of the multi-query fan-out |

### Answer (LLM-judge + deterministic)
| Metric | How | Type |
|---|---|---|
| **Faithfulness / groundedness** | LLM-judge: is every claim supported by the retrieved context or tool output? | LLM-judge (`openevals` RAG groundedness or a custom prompt) |
| **Correctness** | LLM-judge vs `reference_answer` | LLM-judge |
| **Citation validity** | Every `[S#]` maps to a retrieved chunk. ≥1 citation per factual paragraph. | Deterministic |
| **Citation correctness** | A cited chunk's `doc_key` ∈ expected sources | Deterministic |
| **Numeric accuracy** | `must_include` strings (amounts, periods, §) present | Deterministic |
| **Tool selection accuracy** | The expected tool was called with the expected arg subset, and no tool was called when none was expected | Deterministic (from the trace) |
| **Refusal accuracy** | `should_refuse` cases → redirect to an authority/lawyer, no specific legal advice. Non-refusal cases are not refused. | LLM-judge (binary) |
| Cost / answer, latency | From LangSmith run stats | Deterministic |

**Judge hygiene** (likely review question):
- The judge model is **different and stronger** than the answer model, which reduces self-preference bias.
- Use binary/3-point rubrics, not 1–10 scales. Give a reason first, then the score.
- **Calibrate the judge:** hand-label ~15 answers and report the judge/human agreement. Even "13/15 agreement" is a strong review talking point.

## 3. Experiments (the ablation matrix)

Each row is one LangSmith **experiment** on the same dataset version, with config captured as experiment metadata.

| # | Variant | What it isolates |
|---|---|---|
| R0 | Vector only, raw English query, no filters | Baseline |
| R1 | R0 + German rewrite (EN+DE queries, RRF) | **Cross-lingual rewriting** |
| R2 | R1 + multi-query (3 paraphrases) | RAG-Fusion |
| R3 | R2 + decomposition (multi-domain only) | Decomposition |
| R4 | R3 + BM25 hybrid | **Hybrid search** |
| R5 | R4 + profile/metadata filters | **Structured retrieval** |
| R6 | R5 + reranker *(stretch)* | Reranking |
| R7 | R5 + HyDE *(stretch)* | Whether HyDE helps here (hypothesis: no) |
| E-x | Embedding bake-off (Day 3), R0 config | Embedding choice |

Answer-level evals are run only on the **best retrieval config + R0** (the LLM-judge is the expensive part). That gives a "naive RAG vs advanced RAG" headline.

Report the results as a table in the README plus a bar chart (hit@5 per variant). Per-slice breakdowns (by domain, EN vs DE, multi-domain) show *where* each technique helps. For example, BM25 probably helps the `legal_lookup` slice most. That kind of insight impresses reviewers.

### BM25 investigation (2026-11-19)

**Symptom.** The first ablation on the real index (941 chunks, dev split, n = 25 answerable) showed BM25 *hurting*:
R3 → R4 dropped MRR@10 from 0.84 to 0.70, and the full pipeline R5 (hit@5 0.88) was below the plain-vector baseline R0 (0.96).

**Method.** `scripts/retrieval_bench.py` caches the query-analysis plans and query embeddings, so every row sees
*identical* plans and only the retrieval config changes (seconds per row instead of ~13 min). `--show <id>` prints
every ranked list of one question, which is how the cause was found.

**Diagnosis.** Two candidate causes were tested:
1. *BM25 sees English paraphrases against a mostly German corpus* → added `bm25_queries="german"`.
2. *BM25 gets an equal RRF vote and ignores the extracted § references* → added `bm25_weight` and `bm25_legal_refs`.

Both helped a little, but the ranked lists showed the real cause: a **vocabulary gap**. Users ask for
"Mietpreisbremse", "Kaution" or "Untervermietung"; the statute says "Zulässige Miethöhe bei Mietbeginn" (§ 556d),
"Mietsicherheit" (§ 551) and "Gebrauchsüberlassung an Dritte" (§ 553). BM25 could not match the law at all and instead
ranked long pages that repeat the query words (the Munich Mietspiegel pages, the make-it-in-germany Blue Card page).

**Fix (data, not retrieval).** `keywords` in `sources.yaml` (per source or per § range) attach everyday and English
terms to the contextual header, e.g. `[BGB › § 556d …] [tenancy] [Mietpreisbremse, rent cap, rent control]`. Dense
search and BM25 both see them; the citable chunk text stays the official wording. (This also fixed a latent bug:
`content_hash` now covers the embedded text, so a header change triggers re-embedding.)

**Result** (bench, same cached plans; hit@5 / recall@10 / MRR@10):

| Split | Row | Before keywords | After keywords |
|---|---|---|---|
| dev (n=25) | R0 baseline | 0.96 / 0.91 / 0.76 | 0.96 / 0.93 / 0.79 |
| dev | R4 + BM25 | 0.88 / 0.79 / 0.67 | 0.92 / 0.87 / 0.85 |
| dev | **R5 full pipeline** | 0.88 / 0.92 / 0.73 | **1.00 / 0.91 / 0.88** |
| holdout (n=10) | R4 + BM25 | 0.90 / 0.80 / 0.73 | 0.90 / 0.95 / 0.80 |
| holdout | **R5 full pipeline** | 0.90 / 0.80 / 0.65 | **1.00 / 0.90 / 0.81** |

The holdout questions were not looked at while diagnosing, so the improvement generalises.

**Official ablation after the fix** (`expat-eval retrieval --split dev`, fresh query analysis, n = 25):

| Row | hit@5 | recall@10 | MRR@10 |
|---|---|---|---|
| R0 baseline | 0.96 | 0.93 | 0.77 |
| R1 + German rewrite | 1.00 | 0.93 | 0.84 |
| R2 + multi-query + step-back | 1.00 | 0.93 | 0.89 |
| R3 + decomposition | 1.00 | 0.94 | 0.92 |
| R4 + BM25 | 0.96 | 0.94 | 0.81 |
| **R5 + filters (production)** | **1.00** | **0.93** | **0.92** |

(Before the fix, R5 was 0.88 / 0.89 / 0.70.) Every query-translation step adds MRR; BM25 alone still costs ranking
(R3 → R4) and the profile filters recover it, so the R4 → R5 delta measures both.

**Decision.** Keep the defaults (`bm25_queries="all"`, `bm25_weight=1.0`, no ref query): after the keyword fix, all BM25
settings are within ±1 question of each other on dev, so there is no evidence to justify extra knobs. The settings stay
available for future experiments.

**Honest caveats.** (1) With n = 25 / 10, one question moves hit@5 by 0.04 / 0.10. (2) On holdout, R3 (no BM25) still
ranks best (MRR 0.95 vs 0.81 for R5): these questions are easy for the embedding model alone. BM25's value is mostly
insurance for exact identifiers and rare German terms, which the golden set under-represents. Next step: add harder
`legal_lookup` and German questions before claiming more.

### Answer evaluation (2026-11-20)

Full pipeline (query analysis → retrieval → answer agent with tools → citation check), naive retrieval **R0** vs the
production config **R5**. Answer model `openai/gpt-4.1-mini`; judge `anthropic/claude-haiku-4.5` (different family;
the planned Sonnet 4.5 is blocked by the OpenRouter workspace guardrail, see below). Binary judges, reasoning first.
Commands: `uv run python -m expat.evals answers --split dev|holdout --mode langsmith`; LangSmith experiments are
named in each `evals/results/answers-*.json`.

**Headline (holdout, n = 12, never used for tuning):**

| Variant | Faithful | Correct | Cit. valid | Cit. correct | Tool sel. | Refusal acc. | cost/answer |
|---|---|---|---|---|---|---|---|
| R0 naive | 0.90 | 0.70 | 1.00 | 0.80 | 0.92 | 1.00 | $0.0045 |
| **R5 advanced** | **1.00** | **0.90** | 1.00 | 0.76 | 0.92 | 0.92 | $0.0048 |

**Dev (n = 28), before and after fixing what run 1 revealed:**

| Run | Variant | Faithful | Correct | Cit. valid | Must-incl. | Tool sel. | Refusal acc. |
|---|---|---|---|---|---|---|---|
| 1 | R0 | 0.64 | 0.72 | 0.96 | 0.76 | 0.82 | 0.86 |
| 1 | R5 | 0.68 | 0.84 | 1.00 | 0.80 | 0.75 | 0.93 |
| 2 | R0 | 0.84 | 0.76 | 0.96 | 0.80 | 0.82 | 1.00 |
| 2 | **R5** | **0.88** | **0.92** | **1.00** | **0.90** | 0.82 | 0.96 |

Run 1 failures, read one by one, and what changed for run 2:
1. **Judge unfairness (eval bug).** The groundedness judge saw only the sources, so "Assuming you are a Blue Card
   holder in Munich…" (taken from the user profile) was scored as invented in ≥ 4 answers. The judge now also gets
   the question and profile. This, not a better model, explains most of the faithfulness jump (0.68 → 0.88).
2. **Wrong legal answer.** "My landlord gave me notice after 10 years" → 6 months (correct: 9). The model passed
   `party="tenant"` (who the user *is*) instead of `"landlord"` (who *gives* notice). Fixed in the tool schema
   and description; now 9 months, ending 31.08.2027 for notice received 20.11.2026.
3. **Police letter** ("caught without a ticket… will this kill my Blue Card?") got legal guesses → new
   `CRIMINAL` safety category (keyword pre-check) redirecting to a criminal/migration lawyer and MBE.
4. **Medical question** ("fever 39.5, which medicine?") got the generic out-of-scope text → new `MEDICAL`
   category: paediatrician, 116117, 112.

Because 2–4 were fixed after looking at dev failures, **dev run 2 is optimistic; quote the holdout numbers.**

**Known issues (open):**
- **Tax-form help (holdout `oos-002`).** "Fill out my Anlage N, I made 85k" was partly answered instead of
  redirected. **Fixed 2026-11-22** with a narrow `TAX_ADVICE` safety category (form filling / "what do I enter"
  → Steuerberater, Lohnsteuerhilfeverein, ELSTER; tax *information* stays in scope, with tests for both). The
  holdout numbers above are from before this fix; since `oos-002` is now "seen", validate on new questions.
- **Judge false negative (dev `ten-007`).** The refusal judge failed a correct, well-sourced answer as "too
  specific legal advice" although `should_refuse = false`. Calibration (2026-11-22):
  `scripts/judge_calibration.py export` wrote 15 answers with the judge verdict hidden (all judge fails + random
  passes). They were labelled by **Claude Opus 5.5, an LLM** (a second-model check); items 2-4 (`fam-006`,
  `bur-006`, `ten-005`) were then **reviewed and confirmed by a human** (recorded in `evals/calibration/RESULT.md`). Agreement with the Haiku correctness judge: **12/15 (80%), Cohen's kappa
  0.44** (moderate). The judge was too lenient on `fam-004` (an answer that wrongly denies the 6-month Kindergeld
  back-payment) and `bur-004` (misses marriage/birth certificates), and too strict on `fam-006` (correct
  income-cap answer). Takeaway: judge correctness is a trend signal; failures are read by hand. The `fam-006` disagreement (judge too strict) is human-confirmed. Open: human
  review of the other 2 disagreements (`labels_v1.md` notes give the reasoning). Product fix to consider: `fam-004`
  shows the model miscomputing the Kindergeld back-pay window, a candidate for a small tool.
- **Tool selection 0.82:** the checklist and family-benefit tools are sometimes skipped when retrieved sources
  already contain the information (answers still correct). Multi-domain questions remain the weakest slice
  (correct 0.67, n = 3).
- **Citation style varies between runs (seen 2026-11-22).** For the same tenancy question, one run wrote law
  references as plain text ("[§ 573c Abs. 1 BGB]") instead of `[S1]` markers, so no source chip appeared, and
  repeated the generic "end of the second following month" rule next to the correct tool date. Next steps:
  a citation-format check that maps bracketed § references to the matching `[S#]`, and a prompt rule to
  quote the tool's period instead of restating the base rule.
- **Latency:** p50 10–20 s per answer on 2026-11-20, dominated by slow OpenRouter embedding calls that day
  (single calls 8–48 s vs 0.7 s in the bake-off), not by the pipeline. Re-measure before quoting.

**Guardrail note.** The OpenRouter workspace guardrail allows only a short model list (e.g. `gpt-4.1-mini`,
`claude-haiku-4.5`, `gemini-2.5-flash`); `claude-sonnet-4.5`, `gemini-2.5-pro`, `gpt-4.1` are blocked. The eval CLI
now pings the judge once before a paid run and fails fast, and a failing judge only empties its own metric.

### Germany-wide evaluation (2026-11-22)

After adding 5 cities (+264 local chunks, docs/plan-germany-wide.md) the golden set grew to **71 questions**
(45 dev / 26 holdout): per-city Anmeldung, Blue Card, Kita and rent cap / rent index, cross-city questions,
4 "should ask *which city?*" cases, federal questions with an empty profile and an unsupported city (Leipzig).
LangSmith dataset `expat-golden-v2`. Two new metrics: **leak@10** (share of questions with another place's
local chunk in the top 10; unknown location counts every local chunk) and **clarification** (asked for the city
exactly when expected).

**Retrieval (complete):**

| Split | Variant | hit@5 | MRR@10 | leak@10 |
|---|---|---|---|---|
| dev (n = 40) | R0 naive | 0.95 | 0.74 | **0.62** |
| dev | R5 production | 0.95 | 0.80 | **0.00** |
| holdout (n = 22) | R0 naive | 0.95 | 0.84 | **0.68** |
| holdout | R5 production | **1.00** | **0.88** | **0.00** |

Without location filters, two out of three questions pull another city's or state's rules into the context;
with the per-question location (question > profile > nationwide only) it is zero on both splits. Original 40
questions: R5 hit@5 0.96 / 1.00 (dev / holdout), unchanged.

**Answers:** dev complete (R0 / R5): faithful 0.85 / 0.90, correct 0.82 / 0.85, citations valid 0.97 / 1.00,
must-include 0.84 / 0.90, clarification 1.00 / 1.00. New city questions (dev, R5): faithful 0.93, must-include
1.00. Holdout R0 complete (faithful 0.77, correct 0.86); **holdout R5 incomplete**: the OpenRouter key hit its
total limit mid-run (19 of 22 questions answered, judge scores for 10: correct 1.00, faithful 0.89). Rerun when
credit is available: `MODEL_JUDGE=anthropic/claude-haiku-4.5 uv run python -m expat.evals answers --split holdout
--variants R5 --mode langsmith --dataset expat-golden-v2`.

**What the run found and what changed:**
- **Regression (dev `ten-002`):** "How much notice do I give to move out?" -> the model asked for the tenancy start
  date and claimed the tenant's period depends on tenancy length (it is always 3 months). Cause: `tenancy_start`
  was required and the tool description stressed the landlord's 3/6/9 tiers. Fix: the date is only required when
  the landlord gives notice (unit tests); *not yet re-verified with the live model* (key limit).
- **Credit reservation bug:** no model call had an output cap, so OpenRouter reserved credit for the full output
  limit (32k / 64k tokens) per call and rejected calls with 402 while real spend was tiny. All roles now have
  caps (analysis 3000, answer 2500, judge 1024). The per-metric judge isolation kept the run alive and the
  pre-flight ping stopped the retry before spending anything.
- **Unsupported city:** "I live in Leipzig" no longer triggers a pointless "Which city?" (analysis reports
  `mentioned_city`; known-but-unsupported -> nationwide sources only).

### Nationwide topics evaluation (2026-11-23)

Phase 3 added health insurance, citizenship, foreign driving licences and tax ID / tax classes (13 sources,
1531 chunks in total) and **14 golden questions** (`hea-`, `tax-`, `bur-026`–`032`): the set is now **85**
(53 dev / 32 holdout), LangSmith `expat-golden-v3` (retrieval) and `expat-golden-v4` (answers; `bur-031`
reference extended, see below).

**Retrieval (complete, R5 production):**

| Split | Questions | hit@5 | MRR@10 | leak@10 |
|---|---|---|---|---|
| dev | 40 old (unchanged ids) | 0.95 (was 0.95) | 0.84 (was 0.80) | 0.00 |
| dev | 8 new | 0.88 | 0.58 | 0.00 |
| holdout | 22 old | 1.00 (was 1.00) | 0.83 (was 0.88) | 0.00 |
| holdout | 6 new | 0.83 | 0.58 | 0.00 |

No old question got worse at hit@5 on either split. Naive R0 leaks another place's rules into 56% (dev) / 54%
(holdout) of the questions. The two new-question misses: `bur-031` (Japanese licence; the FeV Anlage 11 table
ranks 2nd in a fresh run, so the eval miss came from one query analysis, not from the index) and `bur-032` (10-month
stay; § 29 FeV not in the top 5, but the BMV page with the same 6 + 6 month rule was).

**Answers:** holdout is **complete for the first time** (all 32 answered and judged), R0 / R5: faithful
0.90 / 0.92, **correct 0.86 / 0.96**, citations valid 1.00 / 1.00, tool selection 0.90 / 1.00, refusal accuracy
1.00 / 1.00, clarification 1.00 / 1.00. New holdout questions (R5): correct 1.00. Dev (R5, before the location
prompt fix, `expat-golden-v3`): old questions correct 0.85 (was 0.85), faithful 0.97 (was 0.90); new questions
correct 0.88, faithful 1.00. The R5 dev rerun on v4 hit the OpenRouter key limit (20 failed answers) and is kept
out of the report (`evals/results/_failed/`).

**What the run found and what changed:**
- **Fixed and confirmed:** `ten-002` (tenant notice period, the 2026-11-22 regression) and `fam-004` (late
  Kindergeld application: the deadline tool now returns from which month a late application is still paid,
  § 70 Abs. 1 Satz 2 EStG) both answer correctly.
- **Over-asking for the city (dev `bur-031`):** "Do I need a driving test to swap my Japanese licence?" got
  "Which city do you live in?" because a local office handles it. The `location_dependent` rule now says a
  federal rule stays city-independent unless the user asks about the office itself. Rechecked on 10 dev questions
  (`_partial/`): `bur-031` answers; `bur-001` / `bur-012` (city questions) still resolve the city.
- **Reference gap, not a model error:** the `bur-031` answer named the § 31 Abs. 1a FeV exception (the office may
  still order a test) and was judged wrong; the reference now includes it (dataset v4).
- **Known issue (holdout `bur-032`, not tuned):** for a 10-month stay the answer said a US licence "is valid for
  the duration of the stay"; it is valid for 6 months and the extension must be applied for (§ 29 Abs. 1 FeV).
  The judge's groundedness 0 is right. Candidate fix: a deadline-tool procedure for the licence extension.
- **Budget:** today's answer evals cost about $4.80, mostly judge calls; the estimate in §5 was too low for the
  85-question set (≈ $1.30 per split with both variants).

### Ragas cross-check (2026-11-24)
**Why:** our judges are calibrated on only 15 answers. [Ragas](https://docs.ragas.io) (the best-known RAG eval
library) gives a second, independent opinion on the same answers, and adds what our ID-based hit@k can't see: does
the retrieved *text* actually contain what the reference answer needs?

**Metrics** (`ragas.metrics.collections`, Ragas 0.4.4, LLM = the cheap judge `MODEL_JUDGE`):

| Ragas metric | What it asks | Evidence | Compared with |
|---|---|---|---|
| faithfulness | which share of the answer's statements is supported? (2 LLM calls) | question + profile + sources + tool results, exactly what our groundedness judge sees | our groundedness (binary; "grounded" = faithfulness ≥ 0.8) |
| context precision (with reference) | are the sources that help the reference answer ranked high? (1 call per source) | retrieved sources | hit@5 / MRR |
| context recall | how much of the reference answer do the sources cover? (1 call) | retrieved sources | our correctness: are wrong answers explained by missing sources? |

**Design decisions:**
- **Same answers for both sides.** `answers --samples` writes each answer with the exact sources and tool results
  it was generated from (`evals/results/samples/*.jsonl`) plus our judges' verdicts. Ragas scores that file; it never
  re-runs the pipeline, because a new run gives different answers and "do they agree?" would mean nothing.
- **Own environment.** Ragas needs `instructor`, which pins `jiter<0.15` and so forces an older `openai` than the
  app uses. Added to the project, it would downgrade the deployed app. `scripts/ragas_eval.py` declares its
  dependencies inline (PEP 723) and runs with `uv run --script`, isolated from the app.
- **Refusals, city questions and pipeline errors are skipped:** there is no RAG answer to score.
- **Budget:** the same spend guard as `answers` (estimate from the real sample texts and live prices, × 1.25 vs
  the key's credit; `--dry-run`, `--limit`). Ragas makes ~13 calls per answer (10 sources), ≈ $0.004 per answer
  with Gemini 2.5 Flash-Lite; the measured cost from OpenRouter's `usage` is saved with the results.
- **Cache per model** (`evals/.ragas_cache/<model>/`): Ragas' cache key is the prompt only, not the model, so
  one shared folder would silently reuse another model's verdicts.
- **No telemetry:** Ragas sends usage analytics by default; the script sets `RAGAS_DO_NOT_TRACK=true`.
- **`max_tokens=4096`:** Ragas' default of 1024 cut off the statement list of a long answer (bur-010,
  `IncompleteOutputException`). Output is billed per token used, so the higher cap costs nothing extra.
- **Not committed:** the samples files contain scraped source text (see README, Data and licensing); the score
  files in `evals/results/ragas/` hold ids and numbers only.

**Run** (holdout R5: ≈ $0.10 pipeline + our judges, ≈ $0.10 Ragas):
```bash
uv run python -m expat.evals answers --split holdout --variants R5 --mode langsmith --dataset expat-golden-v4 --samples
uv run --script scripts/ragas_eval.py --dry-run     # estimate only
uv run --script scripts/ragas_eval.py --limit 3     # smoke run, check a few verdicts by hand
uv run --script scripts/ragas_eval.py               # all scorable answers -> evals/results/ragas/*.json + .md
```

**Results (2026-11-24, holdout R5, 28 answers; 4 skipped: refusals and city questions).** Input: a new R5 run
judged by Gemini 2.5 Flash-Lite (correctness 0.93, groundedness 0.96; kept in `evals/results/_crosscheck/`, out
of the headline report, which stays Haiku vs Haiku). Full table: `evals/results/ragas/`.

| Ragas metric | Mean | Reading |
|---|---|---|
| faithfulness | 0.89 | most answers fully supported; the lower ones add advice the sources don't state |
| context precision | 0.74 | the helpful sources are often not ranked first among the ~8–10 handed to the model |
| context recall | 0.93 | the sources almost always cover the reference answer |

**Agreement with our judges:**
- **Groundedness: 24 of 28 answers agree (86%).** Mean faithfulness is 0.90 where our judge said grounded and
  0.69 where it said not grounded (fam-006, which recommends the Familienkasse for Elterngeld: a real error).
- **Both wrong answers (fam-006, ten-013) have context recall 1.00:** the right sources were retrieved, so those
  errors come from generation, not retrieval.

**The 4 disagreements, checked by hand** (Ragas keeps every statement verdict in its cache):
- **ten-015, Ragas right, our judge wrong:** "Stuttgart is on the list of municipalities" is true, but none of
  the 8 retrieved sources names Stuttgart (context recall 0.00 agrees). The list is a separate document that is
  not in the index. Haiku 4.5 caught this on 2026-11-23 (groundedness 0 for the same claim); the cheap Gemini
  judge missed it. **Two real finds:** a data gap (candidate fix: ingest the Baden-Württemberg municipality list),
  and a reminder that the cheap judge can miss an unsupported claim that a stronger judge catches. Ragas as a
  second opinion covers part of that gap.
- **bur-010, bur-007, a difference in strictness:** Ragas rejects practical advice that is not in the legal text
  ("contact the registration office", "you may need the confirmation for other formalities"). Our judge accepts
  general next steps.
- **mul-005, Ragas wrong:** it rejected "you don't deregister separately when you move within Germany", although
  [S3] says the new registration office informs the old one.

**Lessons:**
- **Give Ragas the same evidence as our judge.** The first run did not include the question. Ragas then rejected
  statements that restate it ("the family's income is about 190,000 euros") and agreed on 82%. With the question
  it agreed on 86%.
- **Single faithfulness scores from a cheap model are noisy.** Re-scoring the same answers changed several
  answers by ±0.2 (bur-007 1.00 → 0.78, ten-008 0.60 → 0.80, fam-009 0.78 → 1.00), enough to cross the 0.8
  threshold. Read the means and the rejected statements, not single numbers.
- **Mixed languages were not a problem in practice:** the English prompts handled German sources and questions.
  The wrong verdicts came from reasoning slips (a date rule in fam-006), not from language.
- **Cost:** Ragas $0.10 over two full scorings (most calls were cached the second time), plus $0.11 for the
  pipeline run and our judges. About $0.004 per answer for the three metrics.

## 4. Tooling (APIs verified 2026-11-17: `langsmith` 0.14.x, `openevals` 0.2.x)
- **Datasets:** `Client().create_dataset(dataset_name="expat-golden-v1")` + `create_examples(...)` from the JSONL. Put the `dev`/`holdout` split in example metadata (or use LangSmith dataset splits).
- **Experiments:** `Client().evaluate(target, data="expat-golden-v1", evaluators=[...], experiment_prefix="R4-hybrid", metadata={...config...}, max_concurrency=4)`, or `aevaluate` for the async pipeline. Evaluators are plain functions `(inputs, outputs, reference_outputs) -> bool | dict`. The deterministic metrics are simply Python.
- **LLM-judge:** `openevals.llm.create_llm_as_judge(prompt=RAG_GROUNDEDNESS_PROMPT | CORRECTNESS_PROMPT | custom, judge=<ChatOpenRouter judge model>, feedback_key=...)`.
- **Tracing:** `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com` (EU region). Newer "agent-based workspaces" may use `LANGSMITH_AGENT_ID` instead of the project. Check your workspace type on Day 1.
- **Free tier:** 5k traces/month, **14-day retention**. `report.py` exports every experiment's metrics to `evals/results/*.json` + markdown, so your review numbers don't expire.

## 5. Budget (measured 2026-11-23)

**What one day of evals cost with Claude Haiku 4.5 as judge** (LangSmith token counts × OpenRouter prices):
judges $4.06 (groundedness $2.52: 6.65k input + 790 output tokens per call, because it reads the whole context
and wrote a claim-by-claim essay; correctness $0.81; refusal $0.62), answer pipeline (GPT-4.1-mini) $0.83,
retrieval evals ≈ $0.10. The old estimate here ("≈ $1–4 per cycle") was written for 50 questions and a short
judge output; the 85-question set with Haiku cost ≈ $4.30 per full cycle and hit the key limit mid-run.

**Changes (cost per full cycle, both splits, R0 + R5: ≈ $4.30 → ≈ $0.96):**
1. **Judge model `google/gemini-2.5-flash-lite`** ($0.10 / $0.40 per M tokens vs $1 / $5): a different family than
   the answer model, structured output, no hidden reasoning tokens. Before its numbers replace Haiku's, it is
   re-scored on the 15 labelled calibration answers: `uv run python scripts/judge_calibration.py rejudge`
   (≈ $0.001) -> `evals/calibration/RESULT_<model>.md`. **Done 2026-11-24: 14/15 agreement (93%), Cohen's
   kappa 0.81, vs Haiku 4.5's 12/15 (kappa 0.44)** on the same 15 answers and labels. It also gets fam-006
   right, one of the three human-confirmed labels, where Haiku was too strict; its one miss is fam-005 (too
   lenient). 15 answers is a small sample, but the cheap judge is at least as good as the old one.
2. **Groundedness only for R5** (default; `--groundedness-all` for every variant): the naive-vs-system
   headline uses correctness; groundedness was ~60% of the judge cost.
3. **Short reasoning** (`judges-v2` prompts): at most 60 words, only the claims that fail.
4. **Verdict cache** (`evals/.judge_cache.jsonl`, git-ignored): an identical judge call is never paid twice
   (resumed runs, re-scoring, fixed replies). Prompt version and model are part of the key.
5. **Spend guard:** every `answers` run first prints an estimate from live prices and the key's remaining
   credit, and stops before spending if estimate × 1.25 doesn't fit (`--force` overrides). `--dry-run` prints the
   estimate only.

| Run (85 questions) | Estimate |
|---|---|
| dev, R0 + R5 | ≈ $0.60 (answers $0.53, judges $0.07) |
| holdout, R0 + R5 | ≈ $0.36 |
| a targeted recheck (`--ids`, 10 questions, R5) | ≈ $0.06 |
| retrieval ablation, both splits (R0–R5) | ≈ $0.15 |

The answer pipeline is now the main cost (~$0.005 per answer). Rerun only what a change can affect
(`--variants R5`, `--ids`), and run dev and holdout one after the other, not in parallel, so the guard sees the
real remaining credit.

## 6. Online/production signals (stretch)
- 👍/👎 → LangSmith feedback on the `run_id`.
- An "insufficient context" rate (`answer_meta.confidence`) as a coverage-gap signal, which also tells you which sources to add next.
