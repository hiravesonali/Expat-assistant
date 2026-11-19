# ADR-0002: Embedding model chosen by a bake-off

- **Status:** Accepted (2026-11-19, decided by the bake-off below).
- **Context:** Users ask in English (sometimes German). Most authoritative content is German, so retrieval must be cross-lingual. All candidates are available through the same OpenRouter `/api/v1/embeddings` endpoint, so switching costs one config value.

## Options (prices verified 2026-11-17 on OpenRouter, per 1M tokens)
| Model | Dims | MMTEB | Price | Self-hostable |
|---|---|---|---|---|
| qwen/qwen3-embedding-8b | 4096 | 70.6 | $0.01 | Yes (Apache-2.0, GPU) |
| baai/bge-m3 | 1024 | 59.6 | $0.01 | Yes (MIT, CPU OK) |
| openai/text-embedding-3-small | 1536 | lower | $0.02 | No |

## Decision
**Qwen3-Embedding-8B** (confirmed by the bake-off below). Original hypothesis: Qwen3-Embedding-8B, which has the highest multilingual benchmark score and the lowest price. The final choice is the winner of the Day 3 bake-off on our golden set (hit@5, MRR@10, cross-lingual gap, latency). If it's a tie, pick the simpler/cheaper model.

## Rationale
- Embedding the whole corpus costs about $0.01 per model, so **quality on our data** decides, not price.
- Public benchmarks are a prior, not proof. Legal and administrative German vocabulary is niche.
- An open-weights winner (Qwen3, bge-m3) keeps a local/self-hosted path open (privacy, offline).

## Consequences
- We need an `EmbeddingAdapter` for model-specific prefixes (Qwen3 query instruction, E5 `query:`/`passage:`).
- 4096-dim vectors are ~16 KB each, so ~50 MB for 3k chunks. Fine locally.
- Each query embedding is an API round-trip (~100–300 ms), measured in the bake-off.

## Result (2026-11-19)
Same 941 chunks (with keyword headers), same cached query-analysis plans, `scripts/retrieval_bench.py`.
**R0** = raw question, vector only: the model on its own. **R5** = the full production pipeline.
Golden set: dev n = 25 (20 EN / 5 DE questions), holdout n = 10 answerable.

| Model | Dims | R0 dev hit@5 / MRR | R0 dev MRR EN / DE | R5 dev hit@5 / MRR | R5 holdout hit@5 / MRR | Query p50 / p90 | $ per 1M tok |
|---|---|---|---|---|---|---|---|
| **qwen/qwen3-embedding-8b** | 4096 | **0.96 / 0.79** | **0.81** / 0.70 | **1.00 / 0.88** | **1.00 / 0.81** | 697 / 2366 ms | 0.01 |
| openai/text-embedding-3-small | 1536 | 0.76 / 0.59 | 0.57 / 0.67 | 0.96 / 0.83 | 0.90 / 0.74 | 313 / 352 ms | 0.02 |
| openai/text-embedding-3-large | 3072 | 0.68 / 0.51 | 0.51 / 0.51 | 1.00 / 0.81 | 0.80 / 0.69 | 321 / 383 ms | 0.13 |

Not tested: `baai/bge-m3`, `intfloat/multilingual-e5-large` and `qwen/qwen3-embedding-4b` are blocked by the
OpenRouter workspace guardrail of this project's account (an allow-list). Re-run the bench if it is relaxed.

**Findings**
1. **Qwen3-8B wins clearly on raw cross-lingual retrieval**: R0 MRR 0.79 vs 0.59 / 0.51. Its English-question MRR
   (0.81) shows it maps English questions onto German legal text; the OpenAI models drop to 0.57 / 0.51 there.
2. **Query translation closes most of the gap for weaker models**: text-embedding-3-small goes from 0.59 (R0) to 0.83
   (R5), large from 0.51 to 0.81. The German rewrites are what make an English-centric embedder usable on a German
   corpus. This is the strongest argument for the query-translation layer: it makes the system robust to the
   embedding choice.
3. Bigger is not better here: 3-large scored below 3-small at R0 (small sample; do not over-read).
4. **Cost of the choice: latency.** Qwen3-8B is ~2x slower per query (p50 697 ms, long p90 tail). The pipeline embeds
   all query variants in parallel, so this is roughly one round-trip per question; acceptable for a chat UI, and the
   first thing to revisit if latency becomes a problem (fallback: text-embedding-3-small + full pipeline, R5 MRR 0.83).
5. Caveat: n = 25 / 10. Differences of 0.04 (dev) / 0.10 (holdout) hit@5 are one question.
