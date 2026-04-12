from __future__ import annotations

import sqlite3
import shutil
from pathlib import Path
from uuid import uuid4


CORE_TABLES = {
    "files",
    "papers",
    "paper_files",
    "sections",
    "summaries",
    "qa_items",
    "citation_edges",
    "external_links",
    "task_runs",
}


def _write_project_files(project_root: Path) -> None:
    prompts_dir = project_root / "configs" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (project_root / "configs" / "app.yaml").write_text(
        "\n".join(
            [
                "database:",
                "  path: db/papers.db",
                "paths:",
                "  parsed_dir: data/parsed",
                "  cache_dir: data/cache",
                "  export_dir: data/exports",
                "  logs_dir: data/logs",
                "parsing:",
                "  prefer_deepxiv_for_arxiv: true",
                "  pymupdf_section_split: true",
                "llm:",
                "  summary_model: gpt-5.4",
                "  qa_model: gpt-5.4",
                "  lang: zh",
                "  max_retries: 2",
                "citations:",
                "  default_year_start: 2024",
                "  default_year_end: 2026",
                "  default_max_results: 30",
                "  download_oa_only: true",
                "export:",
                "  summary_file: data/exports/summary.md",
                "  qa_file: data/exports/QA.md",
            ]
        ),
        encoding="utf-8",
    )

    for filename in (
        "summary_system_v1.txt",
        "summary_user_v1.txt",
        "qa_system_v1.txt",
        "qa_user_v1.txt",
    ):
        (prompts_dir / filename).write_text("placeholder", encoding="utf-8")


def test_init_project_creates_database_and_core_tables() -> None:
    tmp_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    tmp_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(tmp_root)

    try:
        from paperlab.cli.init_cmd import init_project

        init_project(str(tmp_root))
        db_path = tmp_root / "db" / "papers.db"
        assert db_path.exists()

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()

        existing_tables = {row[0] for row in rows}
        assert CORE_TABLES.issubset(existing_tables)

        paper_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(papers)").fetchall()
        }
        assert "citation_status" in paper_columns
        assert "parse_quality" in paper_columns
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_init_project_bootstraps_missing_project_files() -> None:
    tmp_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    tmp_root.mkdir(parents=True, exist_ok=True)

    try:
        from paperlab.cli.init_cmd import init_project

        db_path = init_project(str(tmp_root))

        assert db_path.exists()
        assert (tmp_root / "configs" / "app.yaml").exists()
        assert (tmp_root / "configs" / "prompts" / "summary_system_v1.txt").exists()
        assert (tmp_root / "configs" / "prompts" / "summary_user_v1.txt").exists()
        assert (tmp_root / "configs" / "prompts" / "qa_system_v1.txt").exists()
        assert (tmp_root / "configs" / "prompts" / "qa_user_v1.txt").exists()
        assert (tmp_root / ".env.example").exists()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
