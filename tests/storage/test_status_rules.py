from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from paperlab.storage.status import (
    compute_citations_input_hash,
    compute_parse_input_hash,
    compute_qa_input_hash,
    compute_summary_input_hash,
    mark_downstream_stale,
)
from paperlab.storage.task_runs import is_task_completed, record_task_run


def _write_project_files(project_root: Path) -> None:
    prompts_dir = project_root / "configs" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (project_root / "configs" / "app.yaml").write_text(
        "\n".join([
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
            "  summary_model: glm-5.1",
            "  qa_model: glm-5.1",
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
        ]),
        encoding="utf-8",
    )

    for filename in (
        "summary_system_v1.txt",
        "summary_user_v1.txt",
        "qa_system_v1.txt",
        "qa_user_v1.txt",
    ):
        (prompts_dir / filename).write_text("placeholder", encoding="utf-8")


# --- Input hash tests ---

def test_parse_hash_is_consistent_for_same_input():
    h1 = compute_parse_input_hash("abc123")
    h2 = compute_parse_input_hash("abc123")
    assert h1 == h2
    assert len(h1) == 16


def test_parse_hash_differs_for_different_input():
    h1 = compute_parse_input_hash("abc123")
    h2 = compute_parse_input_hash("def456")
    assert h1 != h2


def test_summary_hash_differs_when_model_changes():
    tmp = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        paper_file = tmp / "1.json"
        paper_file.write_text('{"title": "test"}', encoding="utf-8")
        sys_file = tmp / "sys.txt"
        sys_file.write_text("system prompt", encoding="utf-8")
        user_file = tmp / "user.txt"
        user_file.write_text("user prompt", encoding="utf-8")

        h1 = compute_summary_input_hash(paper_file, sys_file, user_file, "glm-5.1")
        h2 = compute_summary_input_hash(paper_file, sys_file, user_file, "glm-4.0")
        assert h1 != h2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_summary_hash_differs_when_prompt_changes():
    tmp = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        paper_file = tmp / "1.json"
        paper_file.write_text('{"title": "test"}', encoding="utf-8")
        sys_file = tmp / "sys.txt"
        sys_file.write_text("v1 prompt", encoding="utf-8")
        user_file = tmp / "user.txt"
        user_file.write_text("user prompt", encoding="utf-8")

        h1 = compute_summary_input_hash(paper_file, sys_file, user_file, "glm-5.1")

        sys_file.write_text("v2 prompt", encoding="utf-8")
        h2 = compute_summary_input_hash(paper_file, sys_file, user_file, "glm-5.1")
        assert h1 != h2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_qa_hash_differs_from_summary_hash():
    tmp = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        paper_file = tmp / "1.json"
        paper_file.write_text('{"title": "test"}', encoding="utf-8")
        sys_file = tmp / "sys.txt"
        sys_file.write_text("system", encoding="utf-8")
        user_file = tmp / "user.txt"
        user_file.write_text("user", encoding="utf-8")

        sh = compute_summary_input_hash(paper_file, sys_file, user_file, "glm-5.1")
        qh = compute_qa_input_hash(paper_file, sys_file, user_file, "glm-5.1")
        assert sh != qh
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_citations_hash_changes_when_identifier_changes():
    h1 = compute_citations_input_hash("t", "d", "a", "o", "s", 2024, 2026, 30)
    h2 = compute_citations_input_hash("t", "d2", "a", "o", "s", 2024, 2026, 30)
    assert h1 != h2


# --- Task runs tests ---

def test_is_task_completed_returns_false_when_no_run():
    tmp = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    tmp.mkdir(parents=True, exist_ok=True)
    db_path = tmp / "test.db"

    try:
        from paperlab.storage.db import initialize_database
        initialize_database(db_path)

        assert not is_task_completed(db_path, "summary", "1", "hash123")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_record_and_check_task_run():
    tmp = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    tmp.mkdir(parents=True, exist_ok=True)
    db_path = tmp / "test.db"

    try:
        from paperlab.storage.db import initialize_database
        initialize_database(db_path)

        record_task_run(
            db_path, "summary", "paper", "1", "glm-5.1", "done", "hash123",
            "2026-04-10T10:00:00+00:00", "2026-04-10T10:01:00+00:00",
        )
        assert is_task_completed(db_path, "summary", "1", "hash123")
        assert not is_task_completed(db_path, "summary", "1", "different_hash")
        assert not is_task_completed(db_path, "qa", "1", "hash123")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- Cascade staleness test ---

def test_mark_downstream_stale_sets_all_statuses():
    tmp = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    tmp.mkdir(parents=True, exist_ok=True)
    _write_project_files(tmp)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(tmp)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, qa_status, graph_status, citation_status, enrich_status, created_at, updated_at) "
                "VALUES ('p-1', 'done', 'done', 'done', 'done', 'done', 'pending', ?, ?)",
                (now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        mark_downstream_stale(db_path, paper_id)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT parse_status, summary_status, qa_status, graph_status, citation_status FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchone()

        assert row == ("stale", "stale", "stale", "stale", "stale")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- Integration: file change cascades via registry ---

def test_file_change_cascades_all_statuses_to_stale():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    target_dir = project_root / "imports"
    target_dir.mkdir(parents=True, exist_ok=True)
    paper_path = target_dir / "paper.pdf"
    paper_path.write_bytes(b"v1")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        db_path = init_project(project_root)
        ingest_path(project_root, paper_path)

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE papers SET parse_status = 'done', summary_status = 'done', qa_status = 'done', graph_status = 'done', citation_status = 'done'"
            )
            conn.commit()

        paper_path.write_bytes(b"v2")
        ingest_path(project_root, paper_path)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT parse_status, summary_status, qa_status, graph_status, citation_status FROM papers"
            ).fetchone()

        assert row == ("stale", "stale", "stale", "stale", "stale")
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


# --- Integration: summarize skips when input_hash matches ---

def test_summarize_skips_when_input_hash_unchanged(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.llm.summary import summarize_paper

        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, created_at, updated_at) "
                "VALUES ('p-1', 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        parsed_dir = project_root / "data" / "parsed"
        parsed_dir.mkdir(parents=True, exist_ok=True)
        parsed_dir.joinpath(f"{paper_id}.json").write_text(
            json.dumps({"title": "T", "abstract": "A", "sections": [], "full_text": "FT"}),
            encoding="utf-8",
        )

        call_count = 0

        def fake_call_llm(*a, **kw):
            nonlocal call_count
            call_count += 1
            return json.dumps({
                "problem": "p", "main_contributions": [], "core_innovations": [],
                "method_summary": "m", "experiment_summary": "e", "limitations": [],
                "key_takeaways": [], "relation_to_user_research": "r", "evidence": [],
            })

        monkeypatch.setattr("paperlab.llm.summary.call_llm", fake_call_llm)

        summarize_paper(project_root, paper_id)
        assert call_count == 1

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE papers SET summary_status = 'pending'"
            )
            conn.commit()

        summarize_paper(project_root, paper_id)
        assert call_count == 1, "LLM should not be called again for same input hash"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
