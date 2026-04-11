from __future__ import annotations

import argparse
from pathlib import Path

from paperlab.cli import citations_cmd, doctor_cmd, export_cmd, init_cmd, ingest_cmd, summarize_cmd, qa_cmd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperctl",
        description="PaperLab: local paper library CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize project")
    p_init.add_argument("root", help="Project root directory")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest PDFs")
    p_ingest.add_argument("project_root", help="Project root directory")
    p_ingest.add_argument("target", help="PDF file or folder to ingest")
    p_ingest.add_argument("--recursive", action="store_true", help="Recursively scan folders")

    # summarize
    p_sum = subparsers.add_parser("summarize", help="Generate structured summaries")
    p_sum.add_argument("project_root", help="Project root directory")
    p_sum.add_argument("--paper-ids", nargs="+", type=int, help="Specific paper IDs")
    p_sum.add_argument("--changed", action="store_true", help="Only changed or stale papers")
    p_sum.add_argument("--all", action="store_true", help="All parsed papers")
    p_sum.add_argument("--force", action="store_true", help="Force rerun for specified paper IDs")

    # qa
    p_qa = subparsers.add_parser("qa", help="Generate deep Q&A")
    p_qa.add_argument("project_root", help="Project root directory")
    p_qa.add_argument("--paper-ids", nargs="+", type=int, help="Specific paper IDs")
    p_qa.add_argument("--changed", action="store_true", help="Only changed or stale papers")
    p_qa.add_argument("--all", action="store_true", help="All parsed papers")
    p_qa.add_argument("--force", action="store_true", help="Force rerun for specified paper IDs")

    # citations
    p_cit = subparsers.add_parser("citations", help="Citation tracking")
    cit_sub = p_cit.add_subparsers(dest="cit_command", required=True)
    p_fwd = cit_sub.add_parser("forward", help="Track forward citations")
    p_fwd.add_argument("project_root", help="Project root directory")
    p_fwd.add_argument("--paper-ids", nargs="+", type=int, help="Specific paper IDs")
    p_fwd.add_argument("--year-start", type=int)
    p_fwd.add_argument("--year-end", type=int)
    p_fwd.add_argument("--max-results", type=int)

    # export
    p_exp = subparsers.add_parser("export", help="Export to Markdown")
    exp_sub = p_exp.add_subparsers(dest="export_type", required=True)
    p_exp_sum = exp_sub.add_parser("summary", help="Export summaries")
    p_exp_sum.add_argument("project_root", help="Project root directory")
    p_exp_qa = exp_sub.add_parser("qa", help="Export Q&A")
    p_exp_qa.add_argument("project_root", help="Project root directory")

    # doctor
    p_doc = subparsers.add_parser("doctor", help="Validate project and environment health")
    p_doc.add_argument("project_root", help="Project root directory")
    p_doc.add_argument("--check-llm", action="store_true", help="Run a live minimal LLM connectivity check")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        init_cmd.init_project(args.root)
        print(f"Project initialized at {args.root}")
        return 0

    if args.command == "ingest":
        result = ingest_cmd.ingest_path(args.project_root, args.target, recursive=args.recursive)
        print(f"\nIngest complete")
        print(f"- discovered: {result.discovered}")
        print(f"- registered: {result.registered}")
        print(f"- updated: {result.updated}")
        print(f"- skipped_duplicates: {result.skipped_duplicates}")
        return 0

    if args.command == "summarize":
        completed = summarize_cmd.summarize_path(
            args.project_root,
            paper_ids=args.paper_ids,
            changed=args.changed or not args.all,
            all_=args.all,
            force=args.force,
        )
        print(f"\nSummary complete: {len(completed)} paper(s) processed")
        return 0

    if args.command == "qa":
        completed = qa_cmd.qa_path(
            args.project_root,
            paper_ids=args.paper_ids,
            changed=args.changed or not args.all,
            all_=args.all,
            force=args.force,
        )
        print(f"\nQA complete: {len(completed)} paper(s) processed")
        return 0

    if args.command == "citations":
        if args.cit_command == "forward":
            citing = citations_cmd.citations_forward_cmd(
                args.project_root,
                paper_ids=args.paper_ids,
                year_start=args.year_start,
                year_end=args.year_end,
                max_results=args.max_results,
            )
            print(f"\nCitation tracking complete: {len(citing)} citing paper(s) found")
        return 0

    if args.command == "export":
        if args.export_type == "summary":
            export_cmd.export_summary_cmd(args.project_root)
        elif args.export_type == "qa":
            export_cmd.export_qa_cmd(args.project_root)
        return 0

    if args.command == "doctor":
        report = doctor_cmd.run_doctor(args.project_root, check_llm=args.check_llm)
        for key, value in report.items():
            print(f"{key}: {value}")
        return 0

    return 1
