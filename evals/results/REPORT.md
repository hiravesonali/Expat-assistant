# Evaluation report

Generated 2026-11-19 09:59 UTC from `evals/results/*.json` (latest run per variant).

## Split: dev

### Retrieval ablation

| Variant | What | n | hit@5 | Δ hit@5 vs R0 | recall@10 | MRR@10 | p50 ms | p95 ms | errors |
|---|---|---|---|---|---|---|---|---|---|
| R0 | Vector only, raw query, no filters (baseline) | 25 | 0.96 | +0.00 | 0.93 | 0.77 | 682 | 2185 | 0 |
| R1 | R0 + German rewrite (EN+DE, RRF) | 25 | 1.00 | +0.04 | 0.93 | 0.84 | 1251 | 2570 | 0 |
| R2 | R1 + multi-query + step-back (RAG-Fusion) | 25 | 1.00 | +0.04 | 0.93 | 0.89 | 2035 | 4657 | 0 |
| R3 | R2 + decomposition (multi-domain) | 25 | 1.00 | +0.04 | 0.94 | 0.92 | 1627 | 4226 | 0 |
| R4 | R3 + BM25 hybrid | 25 | 0.96 | +0.00 | 0.94 | 0.81 | 1419 | 4761 | 0 |
| R5 | R4 + profile/metadata filters | 25 | 1.00 | +0.04 | 0.93 | 0.92 | 965 | 2887 | 0 |

### hit@5 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 |
| tenancy | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| family | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 3 | 0.67 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:legal_lookup | 7 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:multi_domain | 3 | 0.67 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:numeric | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:single_domain | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:tool | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 |
| lang:de | 5 | 0.80 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| lang:en | 20 | 1.00 | 1.00 | 1.00 | 1.00 | 0.95 | 1.00 |
| tool | 9 | 1.00 | 1.00 | 1.00 | 1.00 | 0.89 | 1.00 |

### recall@10 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| tenancy | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| family | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 3 | 0.44 | 0.39 | 0.39 | 0.50 | 0.50 | 0.39 |
| category:legal_lookup | 7 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:multi_domain | 3 | 0.44 | 0.39 | 0.39 | 0.50 | 0.50 | 0.39 |
| category:numeric | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:single_domain | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:tool | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| lang:de | 5 | 0.80 | 0.87 | 0.87 | 0.93 | 0.93 | 0.87 |
| lang:en | 20 | 0.97 | 0.94 | 0.94 | 0.94 | 0.94 | 0.94 |
| tool | 9 | 1.00 | 0.94 | 0.94 | 0.94 | 0.94 | 0.94 |
