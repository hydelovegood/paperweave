from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from paperlab.export.qa_export import export_qa
from paperlab.export.summary_export import export_summary
from paperlab.cli.export_cmd import export_qa_cmd, export_summary_cmd


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


def _insert_paper_with_summary(db_path: Path, title: str, summary_md: str) -> int:
    now = "2026-04-10T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO papers (paper_uid, canonical_title, parse_status, summary_status, qa_status, enrich_status, graph_status, created_at, updated_at) "
            "VALUES (?, ?, 'done', 'done', 'pending', 'pending', 'pending', ?, ?)",
            (f"paper-{uuid4()}", title, now, now),
        )
        paper_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO summaries (paper_id, version, lang, model_name, summary_json, summary_md, evidence_json, created_at) "
            "VALUES (?, 'v1', 'zh', 'glm-5.1', ?, ?, '[]', ?)",
            (paper_id, '{}', summary_md, now),
        )
        conn.commit()
    return paper_id


def _insert_paper_with_qa(db_path: Path, title: str, items: list[dict]) -> int:
    now = "2026-04-10T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO papers (paper_uid, canonical_title, parse_status, summary_status, qa_status, enrich_status, graph_status, created_at, updated_at) "
            "VALUES (?, ?, 'done', 'pending', 'done', 'pending', 'pending', ?, ?)",
            (f"paper-{uuid4()}", title, now, now),
        )
        paper_id = cursor.lastrowid
        for item in items:
            conn.execute(
                "INSERT INTO qa_items (paper_id, qa_type, category, depth_level, question, answer_text, answer_mode, evidence_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '', ?)",
                (
                    paper_id,
                    item["type"],
                    item.get("category"),
                    item.get("depth_level", 2),
                    item["question"],
                    item["answer"],
                    item.get("answer_mode"),
                    now,
                ),
            )
        conn.commit()
    return paper_id


# --- Summary export tests ---

def test_export_summary_writes_completed_summaries():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        _insert_paper_with_summary(db_path, "Paper A", "# Paper A\n\nSummary A")
        _insert_paper_with_summary(db_path, "Paper B", "# Paper B\n\nSummary B")

        output_path = project_root / "data" / "exports" / "summary.md"
        count = export_summary(db_path, output_path)

        assert count == 2
        content = output_path.read_text(encoding="utf-8")
        assert "# Paper A" in content
        assert "# Paper B" in content
        assert "---" in content
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_summary_omits_non_done_papers():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        _insert_paper_with_summary(db_path, "Done Paper", "# Done Paper")

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO papers (paper_uid, canonical_title, parse_status, summary_status, qa_status, enrich_status, graph_status, created_at, updated_at) "
                "VALUES ('p-pending', 'Pending Paper', 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.commit()

        output_path = project_root / "data" / "exports" / "summary.md"
        count = export_summary(db_path, output_path)

        assert count == 1
        content = output_path.read_text(encoding="utf-8")
        assert "Done Paper" in content
        assert "Pending Paper" not in content
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_summary_outputs_deterministic_order():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        id_b = _insert_paper_with_summary(db_path, "Paper B", "# B")
        id_a = _insert_paper_with_summary(db_path, "Paper A", "# A")

        output_path = project_root / "data" / "exports" / "summary.md"
        export_summary(db_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert content.index("# B") < content.index("# A")
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_summary_empty_writes_blank():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        output_path = project_root / "data" / "exports" / "summary.md"
        count = export_summary(db_path, output_path)

        assert count == 0
        assert output_path.read_text(encoding="utf-8") == ""
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_summary_uses_only_latest_summary_per_paper():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, canonical_title, parse_status, summary_status, qa_status, enrich_status, graph_status, created_at, updated_at) "
                "VALUES ('p-latest', 'Latest Paper', 'done', 'done', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            paper_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO summaries (paper_id, version, lang, model_name, summary_json, summary_md, evidence_json, created_at) "
                "VALUES (?, 'v1', 'zh', 'glm-5.1', '{}', '# Old Summary', '[]', ?)",
                (paper_id, now),
            )
            conn.execute(
                "INSERT INTO summaries (paper_id, version, lang, model_name, summary_json, summary_md, evidence_json, created_at) "
                "VALUES (?, 'v1', 'zh', 'glm-5.1', '{}', '# New Summary', '[]', ?)",
                (paper_id, '2026-04-10T01:00:00+00:00'),
            )
            conn.commit()

        output_path = project_root / "data" / "exports" / "summary.md"
        count = export_summary(db_path, output_path)

        assert count == 1
        content = output_path.read_text(encoding="utf-8")
        assert "# New Summary" in content
        assert "# Old Summary" not in content
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


# --- QA export tests ---

def test_export_qa_groups_items_by_paper_and_type():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        _insert_paper_with_qa(db_path, "Test Paper", [
            {"type": "reviewer", "question": "Q1", "answer": "A1", "category": "方法论", "depth_level": 3, "answer_mode": "explicit"},
            {"type": "reviewer", "question": "Q2", "answer": "A2", "category": "实验", "depth_level": 2, "answer_mode": "inferred"},
            {"type": "interview", "question": "Q3", "answer": "A3"},
        ])

        output_path = project_root / "data" / "exports" / "QA.md"
        count = export_qa(db_path, output_path)

        assert count == 1
        content = output_path.read_text(encoding="utf-8")
        assert "# Test Paper" in content
        assert "审稿人视角" in content
        assert "面试深入" in content
        assert "Q1" in content
        assert "A1" in content
        assert "方法论" in content
        assert "显式" in content
        assert "推理" in content
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_qa_omits_papers_without_items():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO papers (paper_uid, canonical_title, parse_status, summary_status, qa_status, enrich_status, graph_status, created_at, updated_at) "
                "VALUES ('p-done', 'Done No QA', 'done', 'pending', 'done', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.commit()

        output_path = project_root / "data" / "exports" / "QA.md"
        count = export_qa(db_path, output_path)

        assert count == 0
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_does_not_modify_db():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        _insert_paper_with_summary(db_path, "Paper", "# Paper\n\nContent")

        with sqlite3.connect(db_path) as conn:
            before_rows = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
            before_sums = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]

        output_path = project_root / "data" / "exports" / "summary.md"
        export_summary(db_path, output_path)

        with sqlite3.connect(db_path) as conn:
            after_rows = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
            after_sums = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]

        assert before_rows == after_rows
        assert before_sums == after_sums
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_qa_uses_single_connection(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    connect_calls = {"count": 0}
    real_connect = sqlite3.connect

    def counting_connect(*args, **kwargs):
        connect_calls["count"] += 1
        return real_connect(*args, **kwargs)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        _insert_paper_with_qa(db_path, "Test Paper A", [
            {"type": "reviewer", "question": "Q1", "answer": "A1"},
        ])
        _insert_paper_with_qa(db_path, "Test Paper B", [
            {"type": "reviewer", "question": "Q2", "answer": "A2"},
        ])

        monkeypatch.setattr("paperlab.export.qa_export.sqlite3.connect", counting_connect)
        output_path = project_root / "data" / "exports" / "QA.md"
        export_qa(db_path, output_path)

        assert connect_calls["count"] == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_commands_work_when_prompt_files_are_missing():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        _insert_paper_with_summary(db_path, "Paper A", "# Paper A")
        _insert_paper_with_qa(db_path, "Paper B", [
            {"type": "reviewer", "question": "Q1", "answer": "A1"},
        ])

        (project_root / "configs" / "prompts" / "summary_system_v1.txt").unlink()

        assert export_summary_cmd(project_root) == 1
        assert export_qa_cmd(project_root) == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_export_qa_labels_biomedical_types():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        _insert_paper_with_qa(db_path, "Bio Paper", [
            {"type": "methodological", "question": "Q1", "answer": "A1"},
            {"type": "clinical", "question": "Q2", "answer": "A2"},
            {"type": "interview", "question": "Q3", "answer": "A3"},
        ])

        output_path = project_root / "data" / "exports" / "QA.md"
        export_qa(db_path, output_path)
        content = output_path.read_text(encoding="utf-8")

        assert "方法学审查" in content
        assert "临床适用性" in content
        assert "面试深入" in content
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
