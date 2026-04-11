from __future__ import annotations

import argparse
from pathlib import Path

from paperlab.config import load_settings
from paperlab.ingest.registry import IngestResult, register_scanned_files
from paperlab.ingest.scanner import scan_target


def ingest_path(project_root: Path | str, target: Path | str, recursive: bool = False) -> IngestResult:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    db_path = (root / settings.database.path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not initialized: {db_path}. Run `paperctl init {root}` first.")
    scanned_files = scan_target(target, recursive=recursive)
    return register_scanned_files(db_path, scanned_files)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperctl-ingest")
    parser.add_argument("project_root")
    parser.add_argument("target")
    parser.add_argument("--recursive", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = ingest_path(args.project_root, args.target, recursive=args.recursive)
    print(
        "\n".join(
            [
                "Ingest complete",
                f"- discovered: {result.discovered}",
                f"- registered: {result.registered}",
                f"- updated: {result.updated}",
                f"- skipped_duplicates: {result.skipped_duplicates}",
            ]
        )
    )
    return 0
