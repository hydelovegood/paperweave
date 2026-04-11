from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from paperlab.config import load_settings
from paperlab.enrich.forward_citations import select_papers_for_citations, track_forward_citations


def citations_forward_cmd(
    project_root: Path | str,
    paper_ids: list[int] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    max_results: int | None = None,
) -> list[int]:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    db_path = (root / settings.database.path).resolve()

    target_ids = paper_ids or select_papers_for_citations(db_path)
    if not target_ids:
        print("No papers for citation tracking.")
        return []

    all_citing: list[int] = []
    for pid in target_ids:
        try:
            citing_ids = track_forward_citations(
                root, pid, year_start=year_start, year_end=year_end, max_results=max_results,
            )
            all_citing.extend(citing_ids)
            print(f"Paper {pid}: found {len(citing_ids)} forward citations")
        except Exception as exc:
            print(f"Failed to track citations for paper {pid}: {exc}")

    return all_citing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperctl-citations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fwd = subparsers.add_parser("forward")
    fwd.add_argument("project_root")
    fwd.add_argument("--paper-ids", nargs="+", type=int)
    fwd.add_argument("--year-start", type=int)
    fwd.add_argument("--year-end", type=int)
    fwd.add_argument("--max-results", type=int)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "forward":
        citing = citations_forward_cmd(
            args.project_root,
            paper_ids=args.paper_ids,
            year_start=args.year_start,
            year_end=args.year_end,
            max_results=args.max_results,
        )
        print(f"\nCitation tracking complete: {len(citing)} citing paper(s) found")
    return 0
