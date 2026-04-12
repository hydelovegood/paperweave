from __future__ import annotations

import sqlite3
import shutil
from pathlib import Path
from uuid import uuid4


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


def _build_project_root() -> Path:
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)
    return project_root


def _fetch_rows(db_path: Path, query: str) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(query).fetchall()


def test_ingest_directory_only_registers_pdfs_under_target_path() -> None:
    project_root = _build_project_root()
    target_dir = project_root / "imports" / "target"
    outside_dir = project_root / "imports" / "outside"
    target_dir.mkdir(parents=True, exist_ok=True)
    outside_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "paper_a.pdf").write_bytes(b"pdf-a")
    (target_dir / "notes.txt").write_text("ignore me", encoding="utf-8")
    (outside_dir / "paper_b.pdf").write_bytes(b"pdf-b")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        db_path = init_project(project_root)
        result = ingest_path(project_root, target_dir, recursive=False)

        assert result.discovered == 1
        assert result.registered == 1

        rows = _fetch_rows(db_path, "SELECT path FROM files")
        assert rows == [(str((target_dir / "paper_a.pdf").resolve()),)]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_identical_files_are_skipped_by_sha256() -> None:
    project_root = _build_project_root()
    target_dir = project_root / "imports" / "duplicates"
    target_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "paper_a.pdf").write_bytes(b"same-content")
    (target_dir / "paper_b.pdf").write_bytes(b"same-content")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        db_path = init_project(project_root)
        result = ingest_path(project_root, target_dir, recursive=False)

        assert result.discovered == 2
        assert result.registered == 1
        assert result.skipped_duplicates == 1

        file_rows = _fetch_rows(db_path, "SELECT COUNT(*) FROM files")
        paper_rows = _fetch_rows(db_path, "SELECT COUNT(*) FROM papers")
        assert file_rows == [(1,)]
        assert paper_rows == [(1,)]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_changed_file_content_marks_parse_as_stale() -> None:
    project_root = _build_project_root()
    target_dir = project_root / "imports" / "changed"
    target_dir.mkdir(parents=True, exist_ok=True)
    paper_path = target_dir / "paper_a.pdf"
    paper_path.write_bytes(b"v1")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        db_path = init_project(project_root)
        first_result = ingest_path(project_root, paper_path, recursive=False)
        assert first_result.registered == 1

        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE papers SET parse_status = 'done'")
            conn.commit()

        paper_path.write_bytes(b"v2")
        second_result = ingest_path(project_root, paper_path, recursive=False)

        assert second_result.updated == 1

        parse_status_rows = _fetch_rows(db_path, "SELECT parse_status FROM papers")
        assert parse_status_rows == [("stale",)]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_ingest_works_when_prompt_files_are_missing() -> None:
    project_root = _build_project_root()
    target_dir = project_root / "imports"
    target_dir.mkdir(parents=True, exist_ok=True)
    paper_path = target_dir / "paper.pdf"
    paper_path.write_bytes(b"pdf")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        db_path = init_project(project_root)
        assert db_path.exists()

        (project_root / "configs" / "prompts" / "qa_system_v1.txt").unlink()
        result = ingest_path(project_root, paper_path, recursive=False)

        assert result.registered == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_changed_file_to_existing_sha_is_deduplicated_without_integrity_error() -> None:
    project_root = _build_project_root()
    target_dir = project_root / "imports" / "dedupe"
    target_dir.mkdir(parents=True, exist_ok=True)

    file_a = target_dir / "paper_a.pdf"
    file_b = target_dir / "paper_b.pdf"
    file_a.write_bytes(b"same-a")
    file_b.write_bytes(b"same-b")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        db_path = init_project(project_root)
        first = ingest_path(project_root, target_dir, recursive=False)
        assert first.registered == 2

        file_b.write_bytes(b"same-a")
        second = ingest_path(project_root, file_b, recursive=False)

        assert second.skipped_duplicates == 1

        file_rows = _fetch_rows(db_path, "SELECT path, sha256 FROM files ORDER BY path")
        paper_rows = _fetch_rows(db_path, "SELECT COUNT(*) FROM papers")

        assert len(file_rows) == 1
        assert file_rows[0][1] != "same-b"
        assert paper_rows == [(1,)]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
