from __future__ import annotations

import argparse
from pathlib import Path

from paperlab.config import load_settings
from paperlab.storage.db import initialize_database


def init_project(project_root: Path | str) -> Path:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)

    for relative_path in (
        settings.paths.parsed_dir,
        settings.paths.cache_dir,
        settings.paths.export_dir,
        settings.paths.logs_dir,
        settings.database.path.parent,
    ):
        (root / relative_path).mkdir(parents=True, exist_ok=True)

    return initialize_database(root / settings.database.path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("root")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        init_project(args.root)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
