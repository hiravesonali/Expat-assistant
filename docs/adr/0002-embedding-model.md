# ADR-0002: Embedding model chosen by a bake-off

- **Status:** Proposed. To be decided on Day 3 with numbers.
- **Context:** Users ask in English (sometimes German). Most authoritative content is German, so retrieval must be cross-lingual. All candidates are available through the same OpenRouter `/api/v1/embeddings` endpoint, so switching costs one config value.

## Options (prices verified 2026-11-17 on OpenRouter, per 1M tokens)
| Model | Dims | MMTEB | Price | Self-hostable |
|---|---|---|---|---|
| qwen/qwen3-embedding-8b | 4096 | 70.6 | $0.01 | Yes (Apache-2.0, GPU) |
| baai/bge-m3 | 1024 | 59.6 | $0.01 | Yes (MIT, CPU OK) |
| openai/text-embedding-3-small | 1536 | lower | $0.02 | No |

## Decision (provisional)
Hypothesis: **Qwen3-Embedding-8B**, which has the highest multilingual benchmark score and the lowest price. The final choice is the winner of the Day 3 bake-off on our golden set (hit@5, MRR@10, cross-lingual gap, latency). If it's a tie, pick the simpler/cheaper model.

## Rationale
- Embedding the whole corpus costs about $0.01 per model, so **quality on our data** decides, not price.
- Public benchmarks are a prior, not proof. Legal and administrative German vocabulary is niche.
- An open-weights winner (Qwen3, bge-m3) keeps a local/self-hosted path open (privacy, offline).

## Consequences
- We need an `EmbeddingAdapter` for model-specific prefixes (Qwen3 query instruction, E5 `query:`/`passage:`).
- 4096-dim vectors are ~16 KB each, so ~50 MB for 3k chunks. Fine locally.
- Each query embedding is an API round-trip (~100–300 ms), measured in the bake-off.

## Result
_To fill in on Day 3: a table of model × hit@5 × MRR × cross-lingual gap × p50 latency._
