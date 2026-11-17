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
