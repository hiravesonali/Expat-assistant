"""A tiny Python evaluator for Chroma's `where` filter language.

Why: ONE filter dict (built by `expat.rag.filters`) must drive BOTH retrievers. Chroma evaluates it
natively for dense search; BM25 (bm25s) knows nothing about metadata, so we apply the same dict
post-hoc on the metadata stored next to the BM25 index (ADR-0004). Re-implementing the handful
of operators we use (~40 lines) is simpler than maintaining two filter representations.

Semantics deliberately mirror Chroma: an operator on a key that is MISSING from the metadata
never matches (tests/store/test_chroma_spike.py pins this for Chroma itself).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

Where = dict[str, Any]


def _compare(value: Any, op: str, operand: Any) -> bool:
    match op:
        case "$eq":
            return bool(value == operand)
        case "$ne":
            return bool(value != operand)
        case "$gt":
            return bool(value > operand)
        case "$gte":
            return bool(value >= operand)
        case "$lt":
            return bool(value < operand)
        case "$lte":
            return bool(value <= operand)
        case "$in":
            return value in operand
        case "$nin":
            return value not in operand
        case "$contains":
            return isinstance(value, list) and operand in value
        case "$not_contains":
            return isinstance(value, list) and operand not in value
    raise ValueError(f"Unsupported where operator: {op}")


def matches_where(metadata: Mapping[str, Any], where: Where | None) -> bool:
    """True if `metadata` (flattened, as stored in Chroma) satisfies `where`. None/{} matches all."""
    if not where:
        return True
    for key, cond in where.items():
        if key == "$and":
            if not all(matches_where(metadata, sub) for sub in cond):
                return False
        elif key == "$or":
            if not any(matches_where(metadata, sub) for sub in cond):
                return False
        else:
            if key not in metadata:
                return False
            ops = cond if isinstance(cond, dict) else {"$eq": cond}
            if not all(_compare(metadata[key], op, operand) for op, operand in ops.items()):
                return False
    return True
