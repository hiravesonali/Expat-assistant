from pathlib import Path

from expat.store.docstore import ParentDocstore
from expat.store.synthetic import synthetic_parents


def test_put_get_roundtrip_and_idempotent(tmp_path: Path) -> None:
    store = ParentDocstore(tmp_path / "docstore.sqlite")
    parents = synthetic_parents()
    store.put_many(parents)
    store.put_many(parents)  # second run must not duplicate
    assert store.count() == len(parents)
    assert store.get("bgb#573c") == next(p for p in parents if p.parent_id == "bgb#573c")
    assert store.get("missing") is None


def test_put_overwrites_and_get_many_dedupes(tmp_path: Path) -> None:
    store = ParentDocstore(tmp_path / "d.sqlite")
    parent = synthetic_parents()[0]
    store.put(parent)
    store.put(parent.model_copy(update={"text": "new text"}))
    got = store.get_many([parent.parent_id, parent.parent_id, "nope"])
    assert list(got) == [parent.parent_id]
    assert got[parent.parent_id].text == "new text"


def test_delete_many(tmp_path: Path) -> None:
    store = ParentDocstore(tmp_path / "d.sqlite")
    store.put_many(synthetic_parents())
    store.delete_many(["bgb#573c"])
    assert "bgb#573c" not in store.all_ids()
