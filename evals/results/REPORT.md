# Evaluation report

Generated 2026-11-22 03:26 UTC from `evals/results/*.json` (latest run per variant).

## Split: dev

### Retrieval ablation

| Variant | What | n | hit@5 | Δ hit@5 vs R0 | recall@10 | MRR@10 | leak@10 | p50 ms | p95 ms | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| R0 | Vector only, raw query, no filters (baseline) | 40 | 0.95 | +0.00 | 0.92 | 0.74 | 0.62 | 2508 | 10683 | 0 |
| R1 | R0 + German rewrite (EN+DE, RRF) | 40 | 0.93 | -0.02 | 0.88 | 0.79 | 0.62 | 3287 | 7016 | 0 |
| R2 | R1 + multi-query + step-back (RAG-Fusion) | 40 | 0.93 | -0.02 | 0.89 | 0.83 | 0.62 | 3737 | 6624 | 0 |
| R3 | R2 + decomposition (multi-domain) | 40 | 0.93 | -0.02 | 0.92 | 0.84 | 0.70 | 5216 | 9509 | 0 |
| R4 | R3 + BM25 hybrid | 40 | 0.90 | -0.05 | 0.88 | 0.77 | 0.62 | 5466 | 11403 | 0 |
| R5 | R4 + profile/metadata filters | 40 | 0.95 | +0.00 | 0.93 | 0.80 | 0.00 | 5366 | 9850 | 0 |

### hit@5 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 15 | 0.93 | 0.87 | 0.87 | 0.87 | 0.80 | 0.93 |
| tenancy | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| family | 9 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 4 | 0.75 | 0.75 | 0.75 | 0.75 | 0.75 | 0.75 |
| category:legal_lookup | 11 | 1.00 | 1.00 | 1.00 | 1.00 | 0.91 | 1.00 |
| category:multi_domain | 3 | 0.67 | 0.67 | 0.67 | 0.67 | 0.67 | 0.67 |
| category:numeric | 5 | 1.00 | 0.80 | 0.80 | 0.80 | 1.00 | 1.00 |
| category:single_domain | 13 | 0.92 | 0.92 | 0.92 | 0.92 | 0.92 | 0.92 |
| category:tool | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 |
| lang:de | 7 | 0.86 | 0.86 | 0.86 | 0.86 | 0.86 | 0.86 |
| lang:en | 33 | 0.97 | 0.94 | 0.94 | 0.94 | 0.91 | 0.97 |
| tool | 9 | 1.00 | 1.00 | 1.00 | 1.00 | 0.89 | 1.00 |

### recall@10 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 15 | 0.90 | 0.87 | 0.87 | 0.93 | 0.83 | 0.93 |
| tenancy | 12 | 1.00 | 0.96 | 0.96 | 0.96 | 0.96 | 1.00 |
| family | 9 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 4 | 0.58 | 0.46 | 0.54 | 0.54 | 0.54 | 0.54 |
| category:legal_lookup | 11 | 0.95 | 0.95 | 0.91 | 0.95 | 0.86 | 1.00 |
| category:multi_domain | 3 | 0.44 | 0.28 | 0.39 | 0.39 | 0.39 | 0.39 |
| category:numeric | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:single_domain | 13 | 0.92 | 0.85 | 0.88 | 0.92 | 0.88 | 0.92 |
| category:tool | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| lang:de | 7 | 0.86 | 0.86 | 0.86 | 0.90 | 0.90 | 0.90 |
| lang:en | 33 | 0.93 | 0.89 | 0.90 | 0.92 | 0.87 | 0.93 |
| tool | 9 | 1.00 | 0.94 | 0.94 | 0.94 | 0.94 | 0.94 |

### Answer quality

| Variant | n | Faithful | Correct | Cit. valid | Cit. correct | Must-incl. | Tool sel. | Refusal acc. | Asks city ok | p50 ms | cost/answer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 45 | 0.85 | 0.82 | 0.97 | 0.70 | 0.84 | 0.86 | 0.98 | 1.00 | 6845 | $0.0050 |
| R5 | 45 | 0.90 | 0.85 | 1.00 | 0.75 | 0.90 | 0.88 | 0.98 | 1.00 | 13265 | $0.0049 |

### Correctness per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 16 | 0.93 | 1.00 |
| tenancy | 13 | 0.75 | 0.75 |
| family | 9 | 0.78 | 0.89 |
| multi_domain | 4 | 0.75 | 0.50 |
| out_of_scope | 3 | – | – |
| category:legal_lookup | 11 | 0.82 | 0.82 |
| category:multi_domain | 3 | 0.67 | 0.33 |
| category:numeric | 5 | 1.00 | 1.00 |
| category:out_of_scope | 1 | – | – |
| category:sensitive | 2 | – | – |
| category:single_domain | 15 | 0.92 | 1.00 |
| category:tool | 8 | 0.62 | 0.75 |
| lang:de | 7 | 0.71 | 0.71 |
| lang:en | 38 | 0.85 | 0.88 |
| tool | 9 | 0.56 | 0.67 |

### Refusal accuracy per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 16 | 1.00 | 1.00 |
| tenancy | 13 | 0.92 | 0.92 |
| family | 9 | 1.00 | 1.00 |
| multi_domain | 4 | 1.00 | 1.00 |
| out_of_scope | 3 | 1.00 | 1.00 |
| category:legal_lookup | 11 | 0.91 | 1.00 |
| category:multi_domain | 3 | 1.00 | 1.00 |
| category:numeric | 5 | 1.00 | 1.00 |
| category:out_of_scope | 1 | 1.00 | 1.00 |
| category:sensitive | 2 | 1.00 | 1.00 |
| category:single_domain | 15 | 1.00 | 1.00 |
| category:tool | 8 | 1.00 | 0.88 |
| lang:de | 7 | 1.00 | 0.86 |
| lang:en | 38 | 0.97 | 1.00 |
| tool | 9 | 1.00 | 0.89 |

## Split: holdout

### Retrieval ablation

| Variant | What | n | hit@5 | Δ hit@5 vs R0 | recall@10 | MRR@10 | leak@10 | p50 ms | p95 ms | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| R0 | Vector only, raw query, no filters (baseline) | 22 | 0.95 | +0.00 | 0.95 | 0.84 | 0.68 | 1595 | 3665 | 0 |
| R1 | R0 + German rewrite (EN+DE, RRF) | 22 | 0.95 | +0.00 | 0.93 | 0.74 | 0.64 | 6103 | 9128 | 0 |
| R2 | R1 + multi-query + step-back (RAG-Fusion) | 22 | 0.95 | +0.00 | 0.93 | 0.70 | 0.64 | 5254 | 6352 | 0 |
| R3 | R2 + decomposition (multi-domain) | 22 | 0.95 | +0.00 | 0.93 | 0.77 | 0.73 | 3083 | 7674 | 0 |
| R4 | R3 + BM25 hybrid | 22 | 0.91 | -0.05 | 0.91 | 0.75 | 0.50 | 2515 | 37653 | 0 |
| R5 | R4 + profile/metadata filters | 22 | 1.00 | +0.05 | 0.98 | 0.88 | 0.00 | 3770 | 8225 | 0 |

### hit@5 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 8 | 0.88 | 0.88 | 0.88 | 0.88 | 0.75 | 1.00 |
| tenancy | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| family | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:legal_lookup | 7 | 1.00 | 1.00 | 1.00 | 1.00 | 0.86 | 1.00 |
| category:multi_domain | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:numeric | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:single_domain | 7 | 0.86 | 0.86 | 0.86 | 0.86 | 0.86 | 1.00 |
| category:tool | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| lang:de | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| lang:en | 19 | 0.95 | 0.95 | 0.95 | 0.95 | 0.89 | 1.00 |
| tool | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### recall@10 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 8 | 0.88 | 0.88 | 0.88 | 0.88 | 0.81 | 1.00 |
| tenancy | 6 | 1.00 | 1.00 | 0.92 | 0.92 | 0.92 | 1.00 |
| family | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 2 | 1.00 | 0.75 | 1.00 | 1.00 | 1.00 | 0.75 |
| category:legal_lookup | 7 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:multi_domain | 1 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 | 0.50 |
| category:numeric | 5 | 1.00 | 1.00 | 0.90 | 0.90 | 0.90 | 1.00 |
| category:single_domain | 7 | 0.86 | 0.86 | 0.86 | 0.86 | 0.86 | 1.00 |
| category:tool | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |
| lang:de | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 0.83 | 1.00 |
| lang:en | 19 | 0.95 | 0.92 | 0.92 | 0.92 | 0.92 | 0.97 |
| tool | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |

### Answer quality

| Variant | n | Faithful | Correct | Cit. valid | Cit. correct | Must-incl. | Tool sel. | Refusal acc. | Asks city ok | p50 ms | cost/answer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 26 | 0.77 | 0.86 | 1.00 | 0.63 | 0.77 | 0.96 | 0.96 | 1.00 | 6688 | $0.0047 |
| R5 | 26 | 0.89 | 1.00 | 1.00 | 0.68 | 0.55 | 0.88 | 0.83 | 1.00 | 7338 | $0.0045 |

### Correctness per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 9 | 0.88 | 1.00 |
| tenancy | 6 | 0.83 | 1.00 |
| family | 7 | 0.83 | 1.00 |
| multi_domain | 2 | 1.00 | – |
| out_of_scope | 2 | – | – |
| category:legal_lookup | 7 | 1.00 | 1.00 |
| category:multi_domain | 1 | 1.00 | – |
| category:numeric | 5 | 0.60 | – |
| category:out_of_scope | 1 | – | – |
| category:sensitive | 1 | – | – |
| category:single_domain | 9 | 1.00 | 1.00 |
| category:tool | 2 | 0.50 | 1.00 |
| lang:de | 4 | 0.67 | 1.00 |
| lang:en | 22 | 0.89 | 1.00 |
| tool | 2 | 0.50 | 1.00 |

### Refusal accuracy per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 9 | 1.00 | 0.83 |
| tenancy | 6 | 1.00 | 0.83 |
| family | 7 | 0.83 | 1.00 |
| multi_domain | 2 | 1.00 | 0.00 |
| out_of_scope | 2 | 1.00 | 1.00 |
| category:legal_lookup | 7 | 1.00 | 0.86 |
| category:multi_domain | 1 | 1.00 | – |
| category:numeric | 5 | 0.80 | 1.00 |
| category:out_of_scope | 1 | 1.00 | 1.00 |
| category:sensitive | 1 | 1.00 | 1.00 |
| category:single_domain | 9 | 1.00 | 0.60 |
| category:tool | 2 | 1.00 | 1.00 |
| lang:de | 4 | 1.00 | 1.00 |
| lang:en | 22 | 0.95 | 0.79 |
| tool | 2 | 1.00 | 1.00 |
