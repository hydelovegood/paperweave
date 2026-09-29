from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from openai import APIConnectionError, APIError, APITimeoutError

from paperlab.config import load_settings
from paperlab.llm.summary import select_papers_for_summary, summarize_paper
from paperlab.storage.db import db_connection

log = logging.getLogger(__name__)

_WORKER_ERRORS = (
    FileNotFoundError,
    ValueError,
    json.JSONDecodeError,
    APIError,
    APIConnectionError,
    APITimeoutError,
    requests.RequestException,
)


def summarize_path(
    project_root: Path | str,
    paper_ids: list[int] | None = None,
    *,
    changed: bool = True,
    all_: bool = False,
    force: bool = False,
    fail_fast: bool = False,
    concurrency: int = 1,
) -> list[int]:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    db_path = (root / settings.database.path).resolve()

    if paper_ids:
        target_ids = paper_ids
    elif all_:
        target_ids = _select_all_parsed(db_path)
    elif changed:
        target_ids = select_papers_for_summary(db_path)
    else:
        target_ids = []
    if force and target_ids:
        _mark_pending(db_path, target_ids)
    if not target_ids:
        log.info("No papers to summarize.")
        return []

    if concurrency > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = pool.map(lambda pid: _try_summarize(root, pid, fail_fast), target_ids)
        return [pid for pid in results if pid is not None]

    completed = []
    for pid in target_ids:
        done = _try_summarize(root, pid, fail_fast)
        if done is not None:
            completed.append(done)
    return completed


def _try_summarize(root: Path, pid: int, fail_fast: bool) -> int | None:
    try:
        summarize_paper(root, pid)
        log.info("Summarized paper %d", pid)
        return pid
    except _WORKER_ERRORS as exc:
        log.warning("Failed to summarize paper %d: %s", pid, exc)
        if fail_fast:
            raise
        return None


def _mark_pending(db_path: Path, paper_ids: list[int]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with db_connection(db_path) as conn:
        for paper_id in paper_ids:
            conn.execute(
                "UPDATE papers SET summary_status = 'stale', updated_at = ? WHERE id = ?",
                (now, paper_id),
            )
        conn.commit()


def _select_all_parsed(db_path: Path) -> list[int]:
    with db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM papers WHERE parse_status = 'done' ORDER BY id"
        ).fetchall()
    return [row[0] for row in rows]
