from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

from paperlab.ingest.scanner import ScannedFile


@dataclass(frozen=True, slots=True)
class IngestResult:
    discovered: int
    registered: int
    skipped_duplicates: int
    updated: int


def register_scanned_files(db_path: Path | str, scanned_files: list[ScannedFile]) -> IngestResult:
    database_path = Path(db_path).expanduser().resolve()
    registered = 0
    skipped_duplicates = 0
    updated = 0
    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(database_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        for scanned in scanned_files:
            existing_by_path = conn.execute(
                "SELECT id, sha256 FROM files WHERE path = ?",
                (str(scanned.path),),
            ).fetchone()

            if existing_by_path:
                file_id, current_sha = existing_by_path
                if current_sha == scanned.sha256:
                    continue

                conn.execute(
                    """
                    UPDATE files
                    SET sha256 = ?, filename = ?, size_bytes = ?, mtime_utc = ?, status = 'changed'
                    WHERE id = ?
                    """,
                    (
                        scanned.sha256,
                        scanned.filename,
                        scanned.size_bytes,
                        scanned.mtime_utc,
                        file_id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE papers
                    SET parse_status = 'stale',
                        summary_status = 'stale',
                        qa_status = 'stale',
                        graph_status = 'stale',
                        citation_status = 'stale',
                        updated_at = ?
                    WHERE id IN (
                        SELECT paper_id FROM paper_files WHERE file_id = ?
                    )
                    """,
                    (now, file_id),
                )
                updated += 1
                continue

            duplicate_sha = conn.execute(
                "SELECT id FROM files WHERE sha256 = ?",
                (scanned.sha256,),
            ).fetchone()
            if duplicate_sha:
                skipped_duplicates += 1
                continue

            cursor = conn.execute(
                """
                INSERT INTO files (sha256, path, filename, size_bytes, mtime_utc, imported_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'new')
                """,
                (
                    scanned.sha256,
                    str(scanned.path),
                    scanned.filename,
                    scanned.size_bytes,
                    scanned.mtime_utc,
                    now,
                ),
            )
            file_id = cursor.lastrowid

            paper_cursor = conn.execute(
                """
                INSERT INTO papers (
                    paper_uid,
                    parse_status,
                    enrich_status,
                    summary_status,
                    qa_status,
                    graph_status,
                    citation_status,
                    created_at,
                    updated_at
                )
                VALUES (?, 'pending', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)
                """,
                (f"paper-{uuid4()}", now, now),
            )
            paper_id = paper_cursor.lastrowid

            conn.execute(
                """
                INSERT INTO paper_files (paper_id, file_id, is_primary)
                VALUES (?, ?, 1)
                """,
                (paper_id, file_id),
            )
            registered += 1

        conn.commit()

    return IngestResult(
        discovered=len(scanned_files),
        registered=registered,
        skipped_duplicates=skipped_duplicates,
        updated=updated,
    )
