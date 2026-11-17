"""Day-2 spike: does LOCAL persistent chromadb accept list-valued metadata + `$contains`?

docs/vector-db-design.md §4 asks us to verify this instead of trusting the changelog. These tests
document the behaviour we rely on in `expat.store.vectorstore` / `expat.rag.filters`, so a Chroma
upgrade that changes it fails loudly here rather than silently returning zero hits.
"""

from pathlib import Path

import chromadb
import pytest


@pytest.fixture
def collection(tmp_path: Path) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(tmp_path))
    col = client.get_or_create_collection("spike")
    col.upsert(
        ids=["a", "b", "c"],
        embeddings=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        metadatas=[
            {"applies_to": ["non_eu", "employee"], "city": "munich", "valid_until_ts": 30000},
            {"applies_to": ["all"], "city": ""},
            {"applies_to": ["eu"], "city": "berlin", "valid_until_ts": 10},
        ],
        documents=["a", "b", "c"],
    )
    return col


def test_array_metadata_round_trips_after_reload(collection: chromadb.Collection, tmp_path: Path) -> None:
    reloaded = chromadb.PersistentClient(path=str(tmp_path)).get_collection("spike")
    got = reloaded.get(ids=["a"], include=["metadatas"])
    assert got["metadatas"] is not None
    assert got["metadatas"][0]["applies_to"] == ["non_eu", "employee"]


def test_contains_filters_on_get_and_query(collection: chromadb.Collection) -> None:
    assert collection.get(where={"applies_to": {"$contains": "non_eu"}})["ids"] == ["a"]
    either = {"$or": [{"applies_to": {"$contains": "non_eu"}}, {"applies_to": {"$contains": "all"}}]}
    assert sorted(collection.get(where=either)["ids"]) == ["a", "b"]
    res = collection.query(query_embeddings=[[1.0, 0.0]], n_results=3, where={"applies_to": {"$contains": "all"}})
    assert res["ids"] == [["b"]]


def test_range_filter_excludes_documents_missing_the_key(collection: chromadb.Collection) -> None:
    """Chroma semantics: a comparison on a missing key does NOT match.

    That is why the indexer writes a sentinel `valid_until_ts` for open-ended chunks instead of
    omitting the key (see `expat.store.vectorstore.OPEN_ENDED_TS`).
    """
    assert collection.get(where={"valid_until_ts": {"$gte": 100}})["ids"] == ["a"]


def test_in_on_empty_string(collection: chromadb.Collection) -> None:
    assert sorted(collection.get(where={"city": {"$in": ["munich", ""]}})["ids"]) == ["a", "b"]
