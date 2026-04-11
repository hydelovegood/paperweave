from __future__ import annotations

import argparse
from pathlib import Path

from paperlab.config import load_settings
from paperlab.export.qa_export import export_qa
from paperlab.export.summary_export import export_summary


def export_summary_cmd(project_root: Path | str) -> int:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    db_path = (root / settings.database.path).resolve()
    output_path = root / settings.export.summary_file

    count = export_summary(db_path, output_path)
    print(f"Exported {count} summary(ies) to {output_path}")
    return count


def export_qa_cmd(project_root: Path | str) -> int:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    db_path = (root / settings.database.path).resolve()
    output_path = root / settings.export.qa_file

    count = export_qa(db_path, output_path)
    print(f"Exported {count} paper(s) QA to {output_path}")
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperctl-export")
    subparsers = parser.add_subparsers(dest="export_type", required=True)

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("project_root")

    qa_parser = subparsers.add_parser("qa")
    qa_parser.add_argument("project_root")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.export_type == "summary":
        export_summary_cmd(args.project_root)
    elif args.export_type == "qa":
        export_qa_cmd(args.project_root)

    return 0
