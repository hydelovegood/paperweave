from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3

from paperlab.config import load_settings
from paperlab.parsing.pipeline import parse_and_persist

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ParseResult:
    completed: list[int] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    errors: dict[int, str] = field(default_factory=dict)


def parse_path(
    project_root: Path | str,
    paper_ids: list[int] | None = None,
    *,
    changed: bool = True,
    all_: bool = False,
    force: bool = False,
    fail_fast: bool = False,
) -> ParseResult:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root, require_prompts=False)
    db_path = (root / settings.database.path).resolve()

    if paper_ids:
        target_ids = paper_ids
    elif all_:
        target_ids = _select_all_with_files(db_path)
    elif changed:
        target_ids = select_papers_for_parse(db_path)
    else:
        target_ids = []

    if force and target_ids:
        _mark_parse_stale(db_path, target_ids)

    completed: list[int] = []
    failed: list[int] = []
    errors: dict[int, str] = {}

    for paper_id in target_ids:
        try:
            input_path = _primary_file_path(db_path, paper_id)
            if input_path is None:
                raise FileNotFoundError(f"No primary file for paper {paper_id}")
            parse_and_persist(root, paper_id, input_path, deepxiv_token=settings.secrets.deepxiv_token)
            _mark_parse_done(db_path, paper_id)
            completed.append(paper_id)
            log.info("Parsed paper %d", paper_id)
        except Exception as exc:
            _mark_parse_failed(db_path, paper_id)
            failed.append(paper_id)
            errors[paper_id] = str(exc)
            log.warning("Failed to parse paper %d: %s", paper_id, exc)
            if fail_fast:
                raise

    if not target_ids:
        log.info("No papers to parse.")

    return ParseResult(completed=completed, failed=failed, errors=errors)


def select_papers_for_parse(db_path: Path | str) -> list[int]:
    db = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT p.id
            FROM papers p
            JOIN paper_files pf ON pf.paper_id = p.id
            WHERE p.parse_status IN ('pending', 'stale', 'failed')
            ORDER BY p.id
            """
        ).fetchall()
    return [row[0] for row in rows]


def _select_all_with_files(db_path: Path) -> list[int]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT p.id
            FROM papers p
            JOIN paper_files pf ON pf.paper_id = p.id
            ORDER BY p.id
            """
        ).fetchall()
    return [row[0] for row in rows]


def _primary_file_path(db_path: Path, paper_id: int) -> Path | None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT f.path
            FROM files f
            JOIN paper_files pf ON pf.file_id = f.id
            WHERE pf.paper_id = ?
            ORDER BY pf.is_primary DESC, f.id ASC
            LIMIT 1
            """,
            (paper_id,),
        ).fetchone()
    return Path(row[0]) if row else None


def _mark_parse_stale(db_path: Path, paper_ids: list[int]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        for paper_id in paper_ids:
            conn.execute(
                "UPDATE papers SET parse_status = 'stale', updated_at = ? WHERE id = ?",
                (now, paper_id),
            )
        conn.commit()


def _mark_parse_done(db_path: Path, paper_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE papers SET parse_status = 'done', updated_at = ? WHERE id = ?",
            (now, paper_id),
        )
        conn.commit()


def _mark_parse_failed(db_path: Path, paper_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE papers SET parse_status = 'failed', updated_at = ? WHERE id = ?",
            (now, paper_id),
        )
        conn.commit()
