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
- **Tax-form help (holdout `oos-002`).** "Fill out my Anlage N, I made 85k" is partly answered instead of redirected
  to a Steuerberater / Lohnsteuerhilfeverein. Planned fix: a `TAX_ADVICE` safety category; to be validated on
  new questions, since this holdout item is now "seen".
- **Judge false negative (dev `ten-007`).** The refusal judge failed a correct, well-sourced answer as "too
  specific legal advice" although `should_refuse = false`. Next step: hand-label ~15 answers and report
  judge/human agreement (§2) before tightening the rubric.
- **Tool selection 0.82:** the checklist and family-benefit tools are sometimes skipped when retrieved sources
  already contain the information (answers still correct). Multi-domain questions remain the weakest slice
  (correct 0.67, n = 3).
- **Latency:** p50 10–20 s per answer on 2026-11-20, dominated by slow OpenRouter embedding calls that day
  (single calls 8–48 s vs 0.7 s in the bake-off), not by the pipeline. Re-measure before quoting.

**Guardrail note.** The OpenRouter workspace guardrail allows only a short model list (e.g. `gpt-4.1-mini`,
`claude-haiku-4.5`, `gemini-2.5-flash`); `claude-sonnet-4.5`, `gemini-2.5-pro`, `gpt-4.1` are blocked. The eval CLI
now pings the judge once before a paid run and fails fast, and a failing judge only empties its own metric.

## 4. Tooling (APIs verified 2026-11-17: `langsmith` 0.14.x, `openevals` 0.2.x)
- **Datasets:** `Client().create_dataset(dataset_name="expat-golden-v1")` + `create_examples(...)` from the JSONL. Put the `dev`/`holdout` split in example metadata (or use LangSmith dataset splits).
- **Experiments:** `Client().evaluate(target, data="expat-golden-v1", evaluators=[...], experiment_prefix="R4-hybrid", metadata={...config...}, max_concurrency=4)`, or `aevaluate` for the async pipeline. Evaluators are plain functions `(inputs, outputs, reference_outputs) -> bool | dict`. The deterministic metrics are simply Python.
- **LLM-judge:** `openevals.llm.create_llm_as_judge(prompt=RAG_GROUNDEDNESS_PROMPT | CORRECTNESS_PROMPT | custom, judge=<ChatOpenRouter judge model>, feedback_key=...)`.
- **Tracing:** `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com` (EU region). Newer "agent-based workspaces" may use `LANGSMITH_AGENT_ID` instead of the project. Check your workspace type on Day 1.
- **Free tier:** 5k traces/month, **14-day retention**. `report.py` exports every experiment's metrics to `evals/results/*.json` + markdown, so your review numbers don't expire.

## 5. Budget estimate
- Retrieval evals: query analysis ≈ 1 cheap LLM call/question → 50 × 8 variants ≈ 400 calls → **< $0.50**.
- Answer evals: 50 × 2 configs × (answer + 3 judge calls) ≈ 400 calls → **≈ $1–4** depending on the judge model.
- Re-run freely. The sprint budget ($10–30) holds even with ~5 full cycles.

## 6. Online/production signals (stretch)
- 👍/👎 → LangSmith feedback on the `run_id`.
- An "insufficient context" rate (`answer_meta.confidence`) as a coverage-gap signal, which also tells you which sources to add next.
