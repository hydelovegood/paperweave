from __future__ import annotations

import sqlite3
from pathlib import Path


QA_TYPE_LABELS = {
    "reviewer": "审稿人视角",
    "interview": "面试深入",
    "author_defense": "作者答辩",
}


def export_qa(db_path: Path | str, output_path: Path | str) -> int:
    db = Path(db_path).expanduser().resolve()
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        papers = conn.execute(
            """
            SELECT id, canonical_title
            FROM papers
            WHERE qa_status = 'done'
            ORDER BY id
            """
        ).fetchall()

        if not papers:
            out.write_text("", encoding="utf-8")
            return 0

        parts: list[str] = []
        paper_count = 0

        for paper_id, title in papers:
            items = conn.execute(
                """
                SELECT qa_type, question, answer_text, category, depth_level, answer_mode
                FROM qa_items
                WHERE paper_id = ?
                ORDER BY id
                """,
                (paper_id,),
            ).fetchall()

            if not items:
                continue

            paper_count += 1
            parts.append(f"# {title or 'Paper ' + str(paper_id)}")
            parts.append("")

            current_type = ""
            for qa_type, question, answer, category, depth, mode in items:
                if qa_type != current_type:
                    current_type = qa_type
                    label = QA_TYPE_LABELS.get(qa_type, qa_type)
                    parts.append(f"## {label}")
                    parts.append("")

                meta = []
                if category:
                    meta.append(category)
                if depth is not None:
                    meta.append(f"深度: {depth}")
                if mode:
                    mode_label = "显式" if mode == "explicit" else "推理"
                    meta.append(mode_label)
                meta_str = f" [{', '.join(meta)}]" if meta else ""

                parts.append(f"### Q: {question}{meta_str}")
                parts.append("")
                parts.append(answer)
                parts.append("")

            parts.append("---")
            parts.append("")

    out.write_text("\n".join(parts), encoding="utf-8")
    return paper_count
