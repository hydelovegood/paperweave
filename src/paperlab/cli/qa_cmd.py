from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from paperlab.config import load_settings
from paperlab.llm.qa import generate_qa, select_papers_for_qa


def qa_path(
    project_root: Path | str,
    paper_ids: list[int] | None = None,
    *,
    changed: bool = True,
    all_: bool = False,
    force: bool = False,
) -> list[int]:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    db_path = (root / settings.database.path).resolve()

    if paper_ids and force:
        _mark_pending(db_path, paper_ids)

    if paper_ids:
        target_ids = paper_ids
    elif all_:
        target_ids = _select_all_parsed(db_path)
    elif changed:
        target_ids = select_papers_for_qa(db_path)
    else:
        target_ids = []
    if not target_ids:
        print("No papers for QA generation.")
        return []

    completed = []
    for pid in target_ids:
        try:
            generate_qa(root, pid)
            completed.append(pid)
            print(f"Generated QA for paper {pid}")
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            print(f"Failed to generate QA for paper {pid}: {exc}")
    return completed


def _mark_pending(db_path: Path, paper_ids: list[int]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        for paper_id in paper_ids:
            conn.execute(
                "UPDATE papers SET qa_status = 'stale', updated_at = ? WHERE id = ?",
                (now, paper_id),
            )
        conn.commit()


def _select_all_parsed(db_path: Path) -> list[int]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM papers WHERE parse_status = 'done' ORDER BY id"
        ).fetchall()
    return [row[0] for row in rows]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperctl-qa")
    parser.add_argument("project_root")
    parser.add_argument("--paper-ids", nargs="+", type=int)
    parser.add_argument("--changed", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    completed = qa_path(
        args.project_root,
        paper_ids=args.paper_ids,
        changed=args.changed or not args.all,
        all_=args.all,
        force=args.force,
    )
    print(f"\nQA complete: {len(completed)} paper(s) processed")
    return 0
