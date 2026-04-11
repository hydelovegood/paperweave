from __future__ import annotations

import sqlite3
from pathlib import Path


def is_task_completed(db_path: Path | str, task_name: str, target_id: str, input_hash: str) -> bool:
    db = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT id FROM task_runs WHERE task_name = ? AND target_id = ? AND input_hash = ? AND status = 'done'",
            (task_name, target_id, input_hash),
        ).fetchone()
    return row is not None


def record_task_run(
    db_path: Path | str,
    task_name: str,
    target_type: str,
    target_id: str,
    model_name: str,
    status: str,
    input_hash: str,
    started_at: str,
    ended_at: str,
    log_path: str | None = None,
) -> int:
    db = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db) as conn:
        cursor = conn.execute(
            """
            INSERT INTO task_runs (task_name, target_type, target_id, model_name, status, input_hash, started_at, ended_at, log_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_name, target_type, target_id, model_name, status, input_hash, started_at, ended_at, log_path),
        )
        conn.commit()
    return cursor.lastrowid
