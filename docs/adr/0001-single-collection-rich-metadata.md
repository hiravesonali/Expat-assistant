# ADR-0001: One Chroma collection with rich metadata + separate parent store

- **Status:** Proposed (2026-11-17)
- **Context:** The corpus spans 3 MVP domains (7 eventually) and 7 document types, in German and English, at federal/state/city level. Questions are often multi-domain ("moving to Munich with kids on a Blue Card"). We need routing, profile-based filtering and reproducible evals.

## Options
1. **One collection + rich metadata.** Routing and filtering via `where`.
2. One collection per domain. The router picks collections.
3. Collections per document type (laws vs guides), possibly with different embedders.

## Decision
Option 1: a single collection of **child chunks**, named `expat__<embedding-model>__s<schema>`. Parents live in a SQLite key-value store, and the BM25 index is built from the same chunks.

## Rationale
- Multi-domain questions need one query, not N queries + merge.
- A routing mistake degrades gracefully (drop the filter or use soft boosts). With per-domain collections it's a hard recall failure.
- Content overlaps domains (Kindergeld = family + tax), and one collection avoids duplication.
- One index to evaluate. Ablations simply toggle filters.
- Encoding the embedding model in the collection name enables side-by-side bake-offs and safe migrations.

## Consequences
- The metadata schema must be disciplined: Pydantic-validated, with a `schema_version` field.
- Chroma metadata is scalar or (since 1.5) typed arrays; local array support must be verified (Day 2 spike, fallback = boolean flags).
- Over-filtering risk → hard filters only for city/state/validity. Audience and section are soft boosts.

## How we'll know
R5 (filters) vs R4 in the ablation: filters must not reduce hit@5 on the dev set, and filter precision should rise.
