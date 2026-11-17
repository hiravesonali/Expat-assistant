"""SQLite key-value store for parent records (the "big" half of small-to-big retrieval).

Why SQLite and not Chroma: parents are never searched by vector, only looked up by `parent_id`
after their children were found. A plain table is simpler, keeps the vector index small, and
ships with Python (`sqlite3`), so there is nothing to install or run.

Schema: `parents(parent_id TEXT PRIMARY KEY, doc_key TEXT, json TEXT)`. The whole ParentRecord is
stored as validated JSON, so the schema can evolve without SQL migrations (`schema_version` lives
in the record). `INSERT ... ON CONFLICT DO UPDATE` makes `put` idempotent.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from expat.schemas import ParentRecord


class ParentDocstore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS parents "
                "(parent_id TEXT PRIMARY KEY, doc_key TEXT NOT NULL, json TEXT NOT NULL)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a short-lived connection per operation.

        sqlite3 connections may not be shared across threads by default, and retrieval runs in a
        thread pool; a connection per call is cheap for a local file and avoids that whole class of bugs.
        """
        conn = sqlite3.connect(self.path)
        try:
            with conn:  # commits on success, rolls back on exception
                yield conn
        finally:
            conn.close()

    def put_many(self, parents: Iterable[ParentRecord]) -> int:
        rows = [(p.parent_id, p.doc_key, p.model_dump_json()) for p in parents]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO parents (parent_id, doc_key, json) VALUES (?, ?, ?) "
                "ON CONFLICT(parent_id) DO UPDATE SET doc_key = excluded.doc_key, json = excluded.json",
                rows,
            )
        return len(rows)

    def put(self, parent: ParentRecord) -> None:
        self.put_many([parent])

    def get(self, parent_id: str) -> ParentRecord | None:
        return self.get_many([parent_id]).get(parent_id)

    def get_many(self, parent_ids: Iterable[str]) -> dict[str, ParentRecord]:
        ids = list(dict.fromkeys(parent_ids))
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT parent_id, json FROM parents WHERE parent_id IN ({placeholders})", ids)
            return {pid: ParentRecord.model_validate_json(raw) for pid, raw in rows}

    def all_ids(self) -> set[str]:
        with self._connect() as conn:
            return {row[0] for row in conn.execute("SELECT parent_id FROM parents")}

    def delete_many(self, parent_ids: Iterable[str]) -> int:
        ids = [(pid,) for pid in parent_ids]
        with self._connect() as conn:
            conn.executemany("DELETE FROM parents WHERE parent_id = ?", ids)
        return len(ids)

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM parents").fetchone()[0])
