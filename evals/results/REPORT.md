# Evaluation report

Generated 2026-11-23 10:46 UTC from `evals/results/*.json` (latest run per variant).

## Split: dev

### Retrieval ablation

| Variant | What | n | hit@5 | Δ hit@5 vs R0 | recall@10 | MRR@10 | leak@10 | p50 ms | p95 ms | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| R0 | Vector only, raw query, no filters (baseline) | 48 | 0.96 | +0.00 | 0.92 | 0.72 | 0.56 | 1201 | 8231 | 0 |
| R1 | R0 + German rewrite (EN+DE, RRF) | 48 | 0.90 | -0.06 | 0.87 | 0.68 | 0.58 | 4774 | 10695 | 0 |
| R2 | R1 + multi-query + step-back (RAG-Fusion) | 48 | 0.94 | -0.02 | 0.90 | 0.72 | 0.58 | 9792 | 15341 | 0 |
| R3 | R2 + decomposition (multi-domain) | 48 | 0.94 | -0.02 | 0.92 | 0.78 | 0.65 | 8563 | 17194 | 0 |
| R4 | R3 + BM25 hybrid | 48 | 0.88 | -0.08 | 0.85 | 0.76 | 0.58 | 6277 | 12621 | 0 |
| R5 | R4 + profile/metadata filters | 48 | 0.94 | -0.02 | 0.89 | 0.80 | 0.00 | 4332 | 17384 | 0 |

### hit@5 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 19 | 0.95 | 0.84 | 0.89 | 0.89 | 0.74 | 0.89 |
| tenancy | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| family | 9 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| health | 2 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |
| taxes | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 4 | 0.75 | 0.75 | 0.75 | 0.75 | 0.75 | 0.75 |
| category:legal_lookup | 11 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:multi_domain | 3 | 0.67 | 0.67 | 0.67 | 0.67 | 0.67 | 0.67 |
| category:numeric | 8 | 1.00 | 0.62 | 0.88 | 0.88 | 0.75 | 1.00 |
| category:single_domain | 18 | 0.94 | 0.94 | 0.94 | 0.94 | 0.89 | 0.89 |
| category:tool | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 |
| lang:de | 7 | 0.86 | 0.86 | 0.86 | 0.86 | 0.86 | 0.86 |
| lang:en | 41 | 0.98 | 0.90 | 0.95 | 0.95 | 0.88 | 0.95 |
| tool | 9 | 1.00 | 1.00 | 1.00 | 1.00 | 0.89 | 1.00 |

### recall@10 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 19 | 0.92 | 0.87 | 0.92 | 0.95 | 0.76 | 0.89 |
| tenancy | 12 | 1.00 | 0.96 | 0.96 | 0.96 | 1.00 | 1.00 |
| family | 9 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.94 |
| health | 2 | 1.00 | 0.50 | 0.75 | 0.75 | 0.75 | 0.75 |
| taxes | 2 | 0.75 | 0.75 | 0.75 | 0.75 | 0.75 | 0.75 |
| multi_domain | 4 | 0.58 | 0.54 | 0.54 | 0.62 | 0.54 | 0.54 |
| category:legal_lookup | 11 | 0.95 | 0.95 | 0.91 | 0.95 | 0.95 | 1.00 |
| category:multi_domain | 3 | 0.44 | 0.39 | 0.39 | 0.50 | 0.39 | 0.39 |
| category:numeric | 8 | 1.00 | 0.75 | 0.94 | 0.94 | 0.75 | 0.88 |
| category:single_domain | 18 | 0.92 | 0.89 | 0.92 | 0.92 | 0.83 | 0.86 |
| category:tool | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| lang:de | 7 | 0.86 | 0.86 | 0.86 | 0.95 | 0.90 | 0.90 |
| lang:en | 41 | 0.93 | 0.87 | 0.91 | 0.91 | 0.84 | 0.89 |
| tool | 9 | 1.00 | 0.94 | 0.94 | 0.94 | 0.94 | 0.94 |

### Answer quality

| Variant | n | Faithful | Correct | Cit. valid | Cit. correct | Must-incl. | Tool sel. | Refusal acc. | Asks city ok | p50 ms | cost/answer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 53 | 0.83 | 0.85 | 0.92 | 0.68 | 0.85 | 0.86 | 0.98 | 1.00 | 11074 | – |
| R5 | 53 | 0.97 | 0.85 | 0.98 | 0.77 | 0.88 | 0.88 | 1.00 | 0.98 | 13504 | – |

### Correctness per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 20 | 0.89 | 0.89 |
| tenancy | 13 | 0.83 | 0.83 |
| family | 9 | 0.78 | 0.89 |
| health | 2 | 1.00 | 1.00 |
| taxes | 2 | 1.00 | 1.00 |
| multi_domain | 4 | 0.75 | 0.50 |
| out_of_scope | 3 | – | – |
| category:legal_lookup | 11 | 0.82 | 0.82 |
| category:multi_domain | 3 | 0.67 | 0.33 |
| category:numeric | 8 | 0.88 | 1.00 |
| category:out_of_scope | 1 | – | – |
| category:sensitive | 2 | – | – |
| category:single_domain | 20 | 0.94 | 0.94 |
| category:tool | 8 | 0.75 | 0.75 |
| lang:de | 7 | 1.00 | 0.71 |
| lang:en | 46 | 0.83 | 0.88 |
| tool | 9 | 0.67 | 0.67 |

### Refusal accuracy per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 20 | 0.95 | 1.00 |
| tenancy | 13 | 1.00 | 1.00 |
| family | 9 | 1.00 | 1.00 |
| health | 2 | 1.00 | 1.00 |
| taxes | 2 | 1.00 | 1.00 |
| multi_domain | 4 | 1.00 | 1.00 |
| out_of_scope | 3 | 1.00 | 1.00 |
| category:legal_lookup | 11 | 1.00 | 1.00 |
| category:multi_domain | 3 | 1.00 | 1.00 |
| category:numeric | 8 | 0.88 | 1.00 |
| category:out_of_scope | 1 | 1.00 | 1.00 |
| category:sensitive | 2 | 1.00 | 1.00 |
| category:single_domain | 20 | 1.00 | 1.00 |
| category:tool | 8 | 1.00 | 1.00 |
| lang:de | 7 | 1.00 | 1.00 |
| lang:en | 46 | 0.98 | 1.00 |
| tool | 9 | 1.00 | 1.00 |

## Split: holdout

### Retrieval ablation

| Variant | What | n | hit@5 | Δ hit@5 vs R0 | recall@10 | MRR@10 | leak@10 | p50 ms | p95 ms | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| R0 | Vector only, raw query, no filters (baseline) | 28 | 0.96 | +0.00 | 0.95 | 0.86 | 0.54 | 1885 | 10056 | 0 |
| R1 | R0 + German rewrite (EN+DE, RRF) | 28 | 0.96 | +0.00 | 0.96 | 0.79 | 0.57 | 5670 | 11160 | 0 |
| R2 | R1 + multi-query + step-back (RAG-Fusion) | 28 | 0.96 | +0.00 | 0.95 | 0.81 | 0.54 | 5164 | 10582 | 0 |
| R3 | R2 + decomposition (multi-domain) | 28 | 0.96 | +0.00 | 0.96 | 0.81 | 0.64 | 5126 | 11153 | 0 |
| R4 | R3 + BM25 hybrid | 28 | 0.89 | -0.07 | 0.91 | 0.71 | 0.50 | 5651 | 11971 | 0 |
| R5 | R4 + profile/metadata filters | 28 | 0.96 | +0.00 | 0.95 | 0.77 | 0.00 | 5826 | 11056 | 0 |

### hit@5 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 11 | 0.91 | 0.91 | 0.91 | 0.91 | 0.73 | 0.91 |
| tenancy | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| family | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| health | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| taxes | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:legal_lookup | 7 | 1.00 | 1.00 | 1.00 | 1.00 | 0.86 | 1.00 |
| category:multi_domain | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:numeric | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:single_domain | 10 | 0.90 | 0.90 | 0.90 | 0.90 | 0.80 | 0.90 |
| category:tool | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| lang:de | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| lang:en | 23 | 0.96 | 0.96 | 0.96 | 0.96 | 0.87 | 0.96 |
| tool | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

### recall@10 per slice

| Slice | n | R0 | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|---|---|
| bureaucracy | 11 | 0.91 | 0.91 | 0.91 | 0.91 | 0.86 | 0.91 |
| tenancy | 6 | 1.00 | 1.00 | 0.92 | 1.00 | 0.92 | 1.00 |
| family | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| health | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| taxes | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi_domain | 2 | 0.75 | 1.00 | 1.00 | 1.00 | 0.75 | 0.75 |
| category:legal_lookup | 7 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| category:multi_domain | 1 | 0.50 | 1.00 | 1.00 | 1.00 | 0.50 | 0.50 |
| category:numeric | 8 | 1.00 | 1.00 | 0.94 | 1.00 | 0.94 | 1.00 |
| category:single_domain | 10 | 0.90 | 0.90 | 0.90 | 0.90 | 0.90 | 0.90 |
| category:tool | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |
| lang:de | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 0.90 | 1.00 |
| lang:en | 23 | 0.93 | 0.96 | 0.93 | 0.96 | 0.91 | 0.93 |
| tool | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |

### Answer quality

| Variant | n | Faithful | Correct | Cit. valid | Cit. correct | Must-incl. | Tool sel. | Refusal acc. | Asks city ok | p50 ms | cost/answer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 32 | 0.90 | 0.86 | 1.00 | 0.68 | 0.82 | 0.90 | 1.00 | 1.00 | 12659 | – |
| R5 | 32 | 0.92 | 0.96 | 1.00 | 0.73 | 0.79 | 1.00 | 1.00 | 1.00 | 12785 | – |

### Correctness per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 12 | 0.82 | 1.00 |
| tenancy | 6 | 1.00 | 1.00 |
| family | 7 | 0.67 | 0.83 |
| health | 2 | 1.00 | 1.00 |
| taxes | 1 | 1.00 | 1.00 |
| multi_domain | 2 | 1.00 | 1.00 |
| out_of_scope | 2 | – | – |
| category:legal_lookup | 7 | 1.00 | 1.00 |
| category:multi_domain | 1 | 1.00 | 1.00 |
| category:numeric | 8 | 0.75 | 0.88 |
| category:out_of_scope | 1 | – | – |
| category:sensitive | 1 | – | – |
| category:single_domain | 12 | 1.00 | 1.00 |
| category:tool | 2 | 0.00 | 1.00 |
| lang:de | 6 | 0.60 | 1.00 |
| lang:en | 26 | 0.91 | 0.96 |
| tool | 2 | 0.00 | 1.00 |

### Refusal accuracy per slice

| Slice | n | R0 | R5 |
|---|---|---|---|
| bureaucracy | 12 | 1.00 | 1.00 |
| tenancy | 6 | 1.00 | 1.00 |
| family | 7 | 1.00 | 1.00 |
| health | 2 | 1.00 | 1.00 |
| taxes | 1 | 1.00 | 1.00 |
| multi_domain | 2 | 1.00 | 1.00 |
| out_of_scope | 2 | 1.00 | 1.00 |
| category:legal_lookup | 7 | 1.00 | 1.00 |
| category:multi_domain | 1 | 1.00 | 1.00 |
| category:numeric | 8 | 1.00 | 1.00 |
| category:out_of_scope | 1 | 1.00 | 1.00 |
| category:sensitive | 1 | 1.00 | 1.00 |
| category:single_domain | 12 | 1.00 | 1.00 |
| category:tool | 2 | 1.00 | 1.00 |
| lang:de | 6 | 1.00 | 1.00 |
| lang:en | 26 | 1.00 | 1.00 |
| tool | 2 | 1.00 | 1.00 |
