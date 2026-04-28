from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paperlab.cli.export_cmd import export_qa_cmd, export_summary_cmd
from paperlab.cli.ingest_cmd import ingest_path
from paperlab.cli.parse_cmd import ParseResult, parse_path
from paperlab.cli.qa_cmd import qa_path
from paperlab.cli.summarize_cmd import summarize_path
from paperlab.ingest.registry import IngestResult


@dataclass(frozen=True, slots=True)
class RunResult:
    ingest: IngestResult
    parse: ParseResult
    summarized: list[int]
    qa: list[int]
    summary_exports: int
    qa_exports: int


def run_path(
    project_root: Path | str,
    target: Path | str,
    *,
    recursive: bool = False,
    all_: bool = False,
    force: bool = False,
    fail_fast: bool = False,
) -> RunResult:
    process_all = all_ or force
    ingest_result = ingest_path(project_root, target, recursive=recursive)
    parse_result = parse_path(
        project_root,
        changed=not process_all,
        all_=process_all,
        force=force,
        fail_fast=fail_fast,
    )
    summarized = summarize_path(
        project_root,
        changed=not process_all,
        all_=process_all,
        force=force,
        fail_fast=fail_fast,
    )
    qa_completed = qa_path(
        project_root,
        changed=not process_all,
        all_=process_all,
        force=force,
        fail_fast=fail_fast,
    )
    summary_exports = export_summary_cmd(project_root)
    qa_exports = export_qa_cmd(project_root)

    return RunResult(
        ingest=ingest_result,
        parse=parse_result,
        summarized=summarized,
        qa=qa_completed,
        summary_exports=summary_exports,
        qa_exports=qa_exports,
    )
