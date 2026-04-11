from __future__ import annotations

import hashlib
from pathlib import Path

from paperlab.utils.hashing import sha256_file


def compute_parse_input_hash(file_sha256: str) -> str:
    return hashlib.sha256(f"parse:{file_sha256}".encode()).hexdigest()[:16]


def compute_summary_input_hash(
    parsed_json_path: Path,
    system_prompt_path: Path,
    user_prompt_path: Path,
    model: str,
) -> str:
    parts = [
        "summary",
        sha256_file(parsed_json_path),
        sha256_file(system_prompt_path),
        sha256_file(user_prompt_path),
        model,
    ]
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


def compute_qa_input_hash(
    parsed_json_path: Path,
    system_prompt_path: Path,
    user_prompt_path: Path,
    model: str,
) -> str:
    parts = [
        "qa",
        sha256_file(parsed_json_path),
        sha256_file(system_prompt_path),
        sha256_file(user_prompt_path),
        model,
    ]
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


def compute_citations_input_hash(
    title: str | None,
    doi: str | None,
    arxiv_id: str | None,
    openalex_id: str | None,
    s2_paper_id: str | None,
    year_start: int,
    year_end: int,
    max_results: int,
) -> str:
    parts = [
        "citations",
        title or "",
        doi or "",
        arxiv_id or "",
        openalex_id or "",
        s2_paper_id or "",
        str(year_start),
        str(year_end),
        str(max_results),
    ]
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


def mark_downstream_stale(db_path: Path | str, paper_id: int) -> None:
    import sqlite3
    from datetime import datetime, timezone

    db = Path(db_path).expanduser().resolve()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            UPDATE papers
            SET parse_status = 'stale',
                summary_status = 'stale',
                qa_status = 'stale',
                graph_status = 'stale',
                citation_status = 'stale',
                updated_at = ?
            WHERE id = ?
            """,
            (now, paper_id),
        )
        conn.commit()
