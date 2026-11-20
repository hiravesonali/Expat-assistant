# Evaluation report

Generated 2026-11-20 11:42 UTC from `evals/results/*.json` (latest run per variant).

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

### Answer quality

| Variant | n | Faithful | Correct | Cit. valid | Cit. correct | Must-incl. | Tool sel. | Refusal acc. | p50 ms | cost/answer |
|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 28 | 0.84 | 0.76 | 0.96 | 0.68 | 0.80 | 0.82 | 1.00 | 22730 | $0.0047 |
| R5 | 28 | 0.88 | 0.92 | 1.00 | 0.74 | 0.90 | 0.82 | 0.96 | 10646 | $0.0048 |

### Correctness per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 8 | 0.88 | 1.00 |
| tenancy | 8 | 0.75 | 1.00 |
| family | 6 | 0.83 | 0.83 |
| multi_domain | 3 | 0.33 | 0.67 |
| out_of_scope | 3 | – | – |
| category:legal_lookup | 7 | 0.86 | 1.00 |
| category:multi_domain | 3 | 0.33 | 0.67 |
| category:numeric | 3 | 1.00 | 1.00 |
| category:out_of_scope | 1 | – | – |
| category:sensitive | 2 | – | – |
| category:single_domain | 4 | 1.00 | 1.00 |
| category:tool | 8 | 0.62 | 0.88 |
| lang:de | 5 | 0.80 | 1.00 |
| lang:en | 23 | 0.75 | 0.90 |
| tool | 9 | 0.56 | 0.78 |

### Refusal accuracy per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 8 | 1.00 | 1.00 |
| tenancy | 8 | 1.00 | 0.88 |
| family | 6 | 1.00 | 1.00 |
| multi_domain | 3 | 1.00 | 1.00 |
| out_of_scope | 3 | 1.00 | 1.00 |
| category:legal_lookup | 7 | 1.00 | 1.00 |
| category:multi_domain | 3 | 1.00 | 1.00 |
| category:numeric | 3 | 1.00 | 1.00 |
| category:out_of_scope | 1 | 1.00 | 1.00 |
| category:sensitive | 2 | 1.00 | 1.00 |
| category:single_domain | 4 | 1.00 | 1.00 |
| category:tool | 8 | 1.00 | 0.88 |
| lang:de | 5 | 1.00 | 0.80 |
| lang:en | 23 | 1.00 | 1.00 |
| tool | 9 | 1.00 | 0.89 |

## Split: holdout

### Answer quality

| Variant | n | Faithful | Correct | Cit. valid | Cit. correct | Must-incl. | Tool sel. | Refusal acc. | p50 ms | cost/answer |
|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 12 | 0.90 | 0.70 | 1.00 | 0.80 | 0.60 | 0.92 | 1.00 | 7237 | $0.0045 |
| R5 | 12 | 1.00 | 0.90 | 1.00 | 0.76 | 0.60 | 0.92 | 0.92 | 20060 | $0.0048 |

### Correctness per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 3 | 0.67 | 1.00 |
| tenancy | 3 | 1.00 | 1.00 |
| family | 3 | 0.67 | 0.67 |
| multi_domain | 1 | 0.00 | 1.00 |
| out_of_scope | 2 | – | – |
| category:legal_lookup | 5 | 0.80 | 1.00 |
| category:multi_domain | 1 | 0.00 | 1.00 |
| category:numeric | 2 | 1.00 | 0.50 |
| category:out_of_scope | 1 | – | – |
| category:sensitive | 1 | – | – |
| category:tool | 2 | 0.50 | 1.00 |
| lang:de | 3 | 0.50 | 1.00 |
| lang:en | 9 | 0.75 | 0.88 |
| tool | 2 | 0.50 | 1.00 |

### Refusal accuracy per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 3 | 1.00 | 1.00 |
| tenancy | 3 | 1.00 | 1.00 |
| family | 3 | 1.00 | 1.00 |
| multi_domain | 1 | 1.00 | 1.00 |
| out_of_scope | 2 | 1.00 | 0.50 |
| category:legal_lookup | 5 | 1.00 | 1.00 |
| category:multi_domain | 1 | 1.00 | 1.00 |
| category:numeric | 2 | 1.00 | 1.00 |
| category:out_of_scope | 1 | 1.00 | 0.00 |
| category:sensitive | 1 | 1.00 | 1.00 |
| category:tool | 2 | 1.00 | 1.00 |
| lang:de | 3 | 1.00 | 1.00 |
| lang:en | 9 | 1.00 | 0.89 |
| tool | 2 | 1.00 | 1.00 |
