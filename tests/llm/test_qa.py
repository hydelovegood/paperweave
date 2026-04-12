from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from paperlab.llm.qa import (
    _validate_qa_items,
    generate_qa,
    select_papers_for_qa,
)


def _sample_qa_items():
    return [
        {
            "type": "reviewer",
            "question": "Why not test on competitive tasks?",
            "answer": "The authors focus on cooperative MARL as stated in Section 1.",
            "category": "实验设计",
            "depth_level": 3,
            "answer_mode": "explicit",
            "evidence": "Section 1 states the scope is cooperative settings.",
        },
        {
            "type": "interview",
            "question": "How does credit assignment work?",
            "answer": "Uses a counterfactual baseline for each agent.",
            "category": "方法论",
            "depth_level": 2,
            "answer_mode": "explicit",
            "evidence": "Equation 4 defines the baseline.",
        },
        {
            "type": "author_defense",
            "question": "Why is your approach better than QMIX?",
            "answer": "QMIX enforces monotonicity which limits expressiveness.",
            "category": "贡献评估",
            "depth_level": 3,
            "answer_mode": "inferred",
            "evidence": "Table 2 shows MAPPO outperforming QMIX.",
        },
    ]


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
            "  base_url: https://open.bigmodel.cn/api/coding/paas/v4",
            "  summary_model: glm-5.1",
            "  qa_model: glm-5.1",
            "  lang: zh",
            "  max_retries: 2",
            "  research_context: multi-agent reinforcement learning",
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


def _setup_parsed_paper(project_root: Path, paper_id: int) -> None:
    parsed_dir = project_root / "data" / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    paper_data = {
        "title": "Test Paper on MARL",
        "abstract": "We study multi-agent reinforcement learning.",
        "sections": [
            {"name": "Introduction", "text": "Multi-agent RL is important.", "order": 1},
        ],
        "full_text": "Multi-agent RL is important.",
    }
    (parsed_dir / f"{paper_id}.json").write_text(
        json.dumps(paper_data, ensure_ascii=False), encoding="utf-8"
    )


# --- QA validation tests ---

def test_validate_qa_items_passes_with_valid_items():
    _validate_qa_items(_sample_qa_items())


def test_validate_qa_items_raises_on_missing_fields():
    items = [{"type": "reviewer", "question": "Q1"}]
    with pytest.raises(ValueError, match="missing required fields"):
        _validate_qa_items(items)


def test_validate_qa_items_raises_on_invalid_type():
    items = [
        {
            "type": "invalid",
            "question": "Q1",
            "answer": "A1",
            "category": "方法论",
            "depth_level": 2,
            "answer_mode": "explicit",
            "evidence": "none",
        }
    ]
    with pytest.raises(ValueError, match="invalid type"):
        _validate_qa_items(items)


# --- Paper selection test ---

def test_select_papers_for_qa_returns_eligible_papers():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, qa_status, enrich_status, summary_status, graph_status, created_at, updated_at) "
                "VALUES ('p-1', 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, qa_status, enrich_status, summary_status, graph_status, created_at, updated_at) "
                "VALUES ('p-2', 'done', 'done', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, qa_status, enrich_status, summary_status, graph_status, created_at, updated_at) "
                "VALUES ('p-3', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.commit()

        ids = select_papers_for_qa(db_path)
        assert ids == [1]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_select_papers_for_qa_includes_failed_with_done_parse():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, qa_status, enrich_status, summary_status, graph_status, created_at, updated_at) "
                "VALUES ('p-failed', 'done', 'failed', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.commit()

        ids = select_papers_for_qa(db_path)
        assert ids == [1]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


# --- End-to-end with mocked LLM ---

def test_generate_qa_persists_items_to_db(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, qa_status, enrich_status, summary_status, graph_status, created_at, updated_at) "
                "VALUES ('p-1', 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        _setup_parsed_paper(project_root, paper_id)

        monkeypatch.setattr(
            "paperlab.llm.qa.call_llm",
            lambda *a, **kw: json.dumps(_sample_qa_items()),
        )

        result = generate_qa(project_root, paper_id)
        assert len(result) == 3

        with sqlite3.connect(db_path) as conn:
            items = conn.execute(
                "SELECT qa_type, question, depth_level FROM qa_items WHERE paper_id = ? ORDER BY id",
                (paper_id,),
            ).fetchall()
            status_rows = conn.execute(
                "SELECT qa_status FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchall()
            log_row = conn.execute(
                "SELECT log_path FROM task_runs WHERE task_name = 'qa' AND target_id = ? ORDER BY id DESC LIMIT 1",
                (str(paper_id),),
            ).fetchone()

        assert len(items) == 3
        assert items[0][0] == "reviewer"
        assert items[1][0] == "interview"
        assert items[2][0] == "author_defense"
        assert status_rows == [("done",)]
        assert log_row is not None
        assert (project_root / log_row[0]).exists()
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_generate_qa_replaces_previous_items_for_same_paper(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, qa_status, enrich_status, summary_status, graph_status, created_at, updated_at) "
                "VALUES ('p-1', 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        _setup_parsed_paper(project_root, paper_id)

        monkeypatch.setattr(
            "paperlab.llm.qa.call_llm",
            lambda *a, **kw: json.dumps(_sample_qa_items()),
        )
        generate_qa(project_root, paper_id)

        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE papers SET qa_status = 'stale' WHERE id = ?", (paper_id,))
            conn.commit()

        newer_items = _sample_qa_items()[:1]
        monkeypatch.setattr(
            "paperlab.llm.qa.call_llm",
            lambda *a, **kw: json.dumps(newer_items),
        )
        result = generate_qa(project_root, paper_id)

        assert len(result) == 1
        with sqlite3.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM qa_items WHERE paper_id = ?",
                (paper_id,),
            ).fetchone()[0]

        assert count == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_generate_qa_cached_result_keeps_evidence_shape(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, qa_status, enrich_status, summary_status, graph_status, created_at, updated_at) "
                "VALUES ('p-cache', 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        _setup_parsed_paper(project_root, paper_id)

        structured_items = _sample_qa_items()
        structured_items[0]["evidence"] = [{"section": "Intro", "quote": "scope"}]
        monkeypatch.setattr(
            "paperlab.llm.qa.call_llm",
            lambda *a, **kw: json.dumps(structured_items),
        )
        first = generate_qa(project_root, paper_id)
        second = generate_qa(project_root, paper_id)

        assert isinstance(first[0]["evidence"], list)
        assert isinstance(second[0]["evidence"], list)
        assert second[0]["evidence"] == first[0]["evidence"]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
