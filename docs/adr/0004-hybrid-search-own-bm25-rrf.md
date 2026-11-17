# ADR-0004: Hybrid search with our own BM25 + Reciprocal Rank Fusion

- **Status:** Proposed
- **Context:** Queries mix vague natural language ("how long before I can move out") with exact identifiers ("§ 573c", "Anlage N", "Steuerklasse III", "§ 18g AufenthG"). Embeddings handle the first kind and miss exact tokens. Verified 2026-11-17: Chroma's built-in sparse/BM25 + RRF Search API is **Chroma Cloud only**. `BM25Retriever` lives in `langchain_community`, which was **sunset in May 2026**.

## Options
1. Vector-only.
2. Chroma Cloud hybrid Search API.
3. Local BM25 via `langchain_community.BM25Retriever` + `EnsembleRetriever`.
4. **Our own BM25 (`bm25s` + German Snowball stemmer) behind a langchain-core `BaseRetriever`, plus our own RRF.**
5. A different vector DB with native hybrid search (Qdrant, Weaviate, pgvector + tsvector).

## Decision
Option 4.

## Rationale
- Stays with local, free Chroma (no cloud account or cost) and avoids an unmaintained package.
- German needs stemming ("Kündigungsfrist"/"Kündigungsfristen"). `bm25s` + PyStemmer supports it.
- Our fusion spans **query variants × retrievers × sub-questions**, which `EnsembleRetriever` doesn't model. RRF is ~15 lines, unit-testable, and independent of score scale (BM25 and cosine scores aren't comparable).
- Option 5 is valid too, and pgvector is familiar from PostgreSQL work. It was rejected for this sprint because Chroma fits the course stack and is faster to set up. It is the production path.

## Consequences
- The BM25 index must be rebuilt after ingestion (seconds at this scale) and loaded at API startup.
- Filters are applied to BM25 results after retrieval (metadata is kept alongside the index).
- Known limitation: German compound words (Mietpreisbremse). Decompounding is a stretch goal.

## How we'll know
Compare R4 with R3 in the ablation, sliced by `category=legal_lookup`. The expected largest gain is on §-referencing questions.
