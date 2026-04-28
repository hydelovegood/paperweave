from __future__ import annotations

import logging
import sys

import click

from paperlab.cli import citations_cmd, doctor_cmd, export_cmd, init_cmd, ingest_cmd, parse_cmd, qa_cmd, run_cmd, summarize_cmd

log = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)


@click.group()
def cli():
    """PaperWeave (溯源文库): local-first paper library CLI"""


@cli.command()
@click.argument("root")
def init(root):
    """Initialize project"""
    init_cmd.init_project(root)
    log.info("Project initialized at %s", root)


@cli.command()
@click.argument("project_root")
@click.argument("target")
@click.option("--recursive", is_flag=True, help="Recursively scan folders")
def ingest(project_root, target, recursive):
    """Ingest PDFs"""
    result = ingest_cmd.ingest_path(project_root, target, recursive=recursive)
    log.info("Ingest complete")
    log.info("- discovered: %s", result.discovered)
    log.info("- registered: %s", result.registered)
    log.info("- updated: %s", result.updated)
    log.info("- skipped_duplicates: %s", result.skipped_duplicates)


@cli.command()
@click.argument("project_root")
@click.option("--paper-ids", multiple=True, type=int, help="Specific paper IDs")
@click.option("--changed", is_flag=True, help="Only changed or stale papers")
@click.option("--all", "all_", is_flag=True, help="All registered papers")
@click.option("--force", is_flag=True, help="Force rerun for specified paper IDs")
@click.option("--fail-fast", is_flag=True, help="Stop on first failed paper")
def parse(project_root, paper_ids, changed, all_, force, fail_fast):
    """Parse registered PDFs"""
    ids = list(paper_ids) if paper_ids else None
    result = parse_cmd.parse_path(
        project_root,
        paper_ids=ids,
        changed=changed or not all_,
        all_=all_,
        force=force,
        fail_fast=fail_fast,
    )
    log.info("Parse complete")
    log.info("- parsed: %s", len(result.completed))
    log.info("- failed: %s", len(result.failed))


@cli.command()
@click.argument("project_root")
@click.argument("target")
@click.option("--recursive", is_flag=True, help="Recursively scan folders")
@click.option("--all", "all_", is_flag=True, help="Process all registered papers")
@click.option("--force", is_flag=True, help="Force rerun changed stages")
@click.option("--fail-fast", is_flag=True, help="Stop on first failed paper")
def run(project_root, target, recursive, all_, force, fail_fast):
    """Run ingest, parse, summary, QA, and exports"""
    result = run_cmd.run_path(
        project_root,
        target,
        recursive=recursive,
        all_=all_,
        force=force,
        fail_fast=fail_fast,
    )
    log.info("Run complete")
    log.info("- discovered: %s", result.ingest.discovered)
    log.info("- registered: %s", result.ingest.registered)
    log.info("- updated: %s", result.ingest.updated)
    log.info("- parsed: %s", len(result.parse.completed))
    log.info("- parse_failed: %s", len(result.parse.failed))
    log.info("- summarized: %s", len(result.summarized))
    log.info("- qa: %s", len(result.qa))
    log.info("- summary_exports: %s", result.summary_exports)
    log.info("- qa_exports: %s", result.qa_exports)


@cli.command()
@click.argument("project_root")
@click.option("--paper-ids", multiple=True, type=int, help="Specific paper IDs")
@click.option("--changed", is_flag=True, help="Only changed or stale papers")
@click.option("--all", "all_", is_flag=True, help="All parsed papers")
@click.option("--force", is_flag=True, help="Force rerun for specified paper IDs")
def summarize(project_root, paper_ids, changed, all_, force):
    """Generate structured summaries"""
    ids = list(paper_ids) if paper_ids else None
    completed = summarize_cmd.summarize_path(
        project_root,
        paper_ids=ids,
        changed=changed or not all_,
        all_=all_,
        force=force,
    )
    log.info("Summary complete: %d paper(s) processed", len(completed))


@cli.command()
@click.argument("project_root")
@click.option("--paper-ids", multiple=True, type=int, help="Specific paper IDs")
@click.option("--changed", is_flag=True, help="Only changed or stale papers")
@click.option("--all", "all_", is_flag=True, help="All parsed papers")
@click.option("--force", is_flag=True, help="Force rerun for specified paper IDs")
def qa(project_root, paper_ids, changed, all_, force):
    """Generate deep Q&A"""
    ids = list(paper_ids) if paper_ids else None
    completed = qa_cmd.qa_path(
        project_root,
        paper_ids=ids,
        changed=changed or not all_,
        all_=all_,
        force=force,
    )
    log.info("QA complete: %d paper(s) processed", len(completed))


@cli.group()
def citations():
    """Citation tracking"""


@citations.command("forward")
@click.argument("project_root")
@click.option("--paper-ids", multiple=True, type=int, help="Specific paper IDs")
@click.option("--year-start", type=int)
@click.option("--year-end", type=int)
@click.option("--max-results", type=int)
def citations_forward(project_root, paper_ids, year_start, year_end, max_results):
    """Track forward citations"""
    ids = list(paper_ids) if paper_ids else None
    citing = citations_cmd.citations_forward_cmd(
        project_root,
        paper_ids=ids,
        year_start=year_start,
        year_end=year_end,
        max_results=max_results,
    )
    log.info("Citation tracking complete: %d citing paper(s) found", len(citing))


@cli.group("export")
def export_group():
    """Export to Markdown"""


@export_group.command("summary")
@click.argument("project_root")
def export_summary(project_root):
    """Export summaries"""
    export_cmd.export_summary_cmd(project_root)


@export_group.command("qa")
@click.argument("project_root")
def export_qa(project_root):
    """Export Q&A"""
    export_cmd.export_qa_cmd(project_root)


@cli.command()
@click.argument("project_root")
@click.option("--check-llm", is_flag=True, help="Run a live minimal LLM connectivity check")
def doctor(project_root, check_llm):
    """Validate project and environment health"""
    report = doctor_cmd.run_doctor(project_root, check_llm=check_llm)
    for key, value in report.items():
        log.info("%s: %s", key, value)


def main():
    cli()
