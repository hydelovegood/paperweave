from __future__ import annotations

import sqlite3
from pathlib import Path


def export_summary(db_path: Path | str, output_path: Path | str) -> int:
    db = Path(db_path).expanduser().resolve()
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.canonical_title, s.summary_md
            FROM papers p
            JOIN summaries s ON s.id = (
                SELECT s2.id
                FROM summaries s2
                WHERE s2.paper_id = p.id
                ORDER BY s2.id DESC
                LIMIT 1
            )
            WHERE p.summary_status = 'done'
            ORDER BY p.id
            """
        ).fetchall()

    if not rows:
        out.write_text("", encoding="utf-8")
        return 0

    parts: list[str] = []
    for paper_id, title, md in rows:
        parts.append(md or f"# {title or 'Paper ' + str(paper_id)}")
        parts.append("\n---\n")

    out.write_text("\n".join(parts), encoding="utf-8")
    return len(rows)
