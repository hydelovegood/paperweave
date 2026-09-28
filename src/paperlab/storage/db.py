from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from paperlab.storage.schema import INDEX_STATEMENTS, create_all_tables

BUSY_TIMEOUT_MS = 5000

_indexed_paths: set[Path] = set()


def _ensure_indexes(conn: sqlite3.Connection) -> None:
    # Once per process per path: upgrades databases created before the indexes
    # existed. Skipped silently for databases that predate init (no tables yet).
    try:
        for statement in INDEX_STATEMENTS:
            conn.execute(statement)
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()


@contextmanager
def db_connection(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    """Open a connection that is always closed and commits on success.

    `with sqlite3.connect(...) as conn` alone commits/rolls back but never
    closes the connection; use this helper everywhere instead.
    """
    path = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(path)
    try:
        if path not in _indexed_paths:
            _ensure_indexes(conn)
            _indexed_paths.add(path)
        # journal_mode is persistent, so this also upgrades pre-WAL databases.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            yield conn
    finally:
        conn.close()


def initialize_database(db_path: Path | str) -> Path:
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            create_all_tables(conn)
    finally:
        conn.close()

    return path
