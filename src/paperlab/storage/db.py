from __future__ import annotations

from pathlib import Path
import sqlite3

from paperlab.storage.schema import create_all_tables


def initialize_database(db_path: Path | str) -> Path:
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        create_all_tables(connection)

    return path
