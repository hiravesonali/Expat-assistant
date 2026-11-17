"""Reciprocal Rank Fusion (Cormack et al., 2009), see ADR-0004.

    score(d) = sum over lists L containing d of 1 / (c + rank_L(d))      (rank is 1-based)

Why RRF and not a weighted sum of scores: BM25 scores (unbounded, corpus-dependent) and cosine
distances live on different scales, so adding them is meaningless. RRF only uses *positions*,
so any number of lists (query variants x retrievers) can be merged without calibration.
`c=60` damps the influence of the very top ranks; it is the value from the paper and the one
LangChain's `EnsembleRetriever` uses.
"""

from __future__ import annotations

FusedItem = tuple[str, float, dict[str, int]]


def reciprocal_rank_fusion(ranked_lists: dict[str, list[str]], c: int = 60) -> list[FusedItem]:
    """Fuse named rankings into one list of `(id, fused_score, {list_name: rank})`.

    `ranked_lists` maps a list label (e.g. "dense:de:0", "bm25:en:1") to ids in rank order.
    The per-list ranks are returned so the debugger can show *why* a chunk ranked where it did.
    Duplicate ids inside one list count once, at their best (first) position.

    Sorting is deterministic: by score desc, then best single rank, then id. Determinism matters
    because eval runs must be reproducible.
    """
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for name, ids in ranked_lists.items():
        seen: set[str] = set()
        for position, doc_id in enumerate(ids, start=1):
            if doc_id in seen:
                continue
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (c + position)
            ranks.setdefault(doc_id, {})[name] = position

    def sort_key(doc_id: str) -> tuple[float, int, str]:
        return (-scores[doc_id], min(ranks[doc_id].values()), doc_id)

    return [(doc_id, scores[doc_id], ranks[doc_id]) for doc_id in sorted(scores, key=sort_key)]
