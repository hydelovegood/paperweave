from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from paperlab.llm.client import extract_json_object, extract_json_array
from paperlab.llm.summary import (
    _build_summary_md,
    _validate_summary,
    select_papers_for_summary,
    summarize_paper,
)


def _sample_summary():
    return {
        "problem": "How to scale MARL",
        "main_contributions": ["A new algorithm", "Better convergence"],
        "core_innovations": ["Decentralized coordination"],
        "method_summary": "Uses PPO with multi-agent credit assignment",
        "experiment_summary": "Tested on StarCraft II and Google Research Football",
        "limitations": ["Only tested on cooperative tasks", "Scalability unclear beyond 50 agents"],
        "key_takeaways": ["Scalable MARL is feasible"],
        "relation_to_user_research": "Directly relevant to cooperative MARL settings",
        "evidence": [{"claim": "Algorithm converges", "quote": "Figure 3 shows convergence after 1M steps"}],
    }


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


def _setup_parsed_paper(project_root: Path, paper_id: int) -> Path:
    parsed_dir = project_root / "data" / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    paper_data = {
        "title": "Test Paper on MARL",
        "abstract": "We study multi-agent reinforcement learning.",
        "sections": [
            {"name": "Introduction", "text": "Multi-agent RL is important.", "order": 1},
            {"name": "Method", "text": "We propose MAPPO.", "order": 2},
        ],
        "full_text": "Multi-agent RL is important.\nWe propose MAPPO.",
    }
    parsed_path = parsed_dir / f"{paper_id}.json"
    parsed_path.write_text(json.dumps(paper_data, ensure_ascii=False), encoding="utf-8")
    return parsed_path


# --- JSON extraction tests ---

def test_extract_json_object_handles_pure_json():
    raw = '{"problem": "test", "main_contributions": ["a"]}'
    result = extract_json_object(raw)
    assert result["problem"] == "test"


def test_extract_json_object_handles_code_block():
    raw = '```json\n{"problem": "test", "main_contributions": ["a"]}\n```'
    result = extract_json_object(raw)
    assert result["problem"] == "test"


def test_extract_json_object_handles_surrounding_text():
    raw = 'Here is the summary:\n{"problem": "test", "main_contributions": ["a"]}\nEnd.'
    result = extract_json_object(raw)
    assert result["problem"] == "test"


def test_extract_json_array_handles_pure_array():
    raw = '[{"type": "reviewer", "question": "Q1", "answer": "A1"}]'
    result = extract_json_array(raw)
    assert len(result) == 1
    assert result[0]["type"] == "reviewer"


def test_extract_json_array_handles_code_block():
    raw = '```json\n[{"type": "reviewer", "question": "Q1"}]\n```'
    result = extract_json_array(raw)
    assert len(result) == 1


def test_extract_json_array_handles_invalid_latex_style_backslashes():
    raw = '[{"type": "reviewer", "question": "What about \\\\{0,1\\\\}^n and \\\\pi?"}]'
    # Simulate model output that uses single backslashes in JSON text content
    raw = raw.replace("\\\\{", "\\{").replace("\\\\}", "\\}").replace("\\\\pi", "\\pi")
    result = extract_json_array(raw)
    assert len(result) == 1
    assert "\\{0,1\\}^n" in result[0]["question"]
    assert "\\pi" in result[0]["question"]


def test_extract_json_object_raises_on_invalid():
    with pytest.raises(ValueError):
        extract_json_object("not json at all")


def test_extract_json_array_raises_on_invalid():
    with pytest.raises(ValueError):
        extract_json_array("not json at all")


# --- Summary validation tests ---

def test_validate_summary_passes_with_all_fields():
    _validate_summary(_sample_summary())


def test_validate_summary_raises_on_missing_fields():
    data = {"problem": "test"}
    with pytest.raises(ValueError, match="missing required fields"):
        _validate_summary(data)


# --- Markdown generation test ---

def test_build_summary_md_contains_all_sections():
    md = _build_summary_md("Test Paper", _sample_summary())
    assert "# Test Paper" in md
    assert "## 核心问题" in md
    assert "How to scale MARL" in md
    assert "## 主要贡献" in md
    assert "- A new algorithm" in md
    assert "## 证据" in md
    assert "Algorithm converges" in md


def test_build_summary_md_handles_structured_relation_field():
    summary = _sample_summary()
    summary["relation_to_user_research"] = {
        "summary": "与多智能体强化学习直接相关。",
        "applications": ["策略平滑性", "鲁棒性分析"],
    }

    md = _build_summary_md("Test Paper", summary)

    assert "## 与研究方向的关系" in md
    assert "与多智能体强化学习直接相关。" in md
    assert "- 策略平滑性" in md
    assert "- 鲁棒性分析" in md


# --- Paper selection test ---

def test_select_papers_for_summary_returns_pending_with_done_parse():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, created_at, updated_at) "
                "VALUES ('p-1', 'done', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, created_at, updated_at) "
                "VALUES ('p-2', 'done', 'done', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, created_at, updated_at) "
                "VALUES ('p-3', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.commit()

        ids = select_papers_for_summary(db_path)
        assert ids == [1]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_select_papers_for_summary_includes_failed_with_done_parse():
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, created_at, updated_at) "
                "VALUES ('p-failed', 'done', 'failed', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            conn.commit()

        ids = select_papers_for_summary(db_path)
        assert ids == [1]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


# --- End-to-end with mocked LLM ---

def test_summarize_paper_persists_to_db(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
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

        _setup_parsed_paper(project_root, paper_id)

        monkeypatch.setattr(
            "paperlab.llm.summary.call_llm",
            lambda *a, **kw: json.dumps(_sample_summary()),
        )

        result = summarize_paper(project_root, paper_id)
        assert result["problem"] == "How to scale MARL"

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT version, model_name, lang FROM summaries WHERE paper_id = ?",
                (paper_id,),
            ).fetchall()
            status_rows = conn.execute(
                "SELECT summary_status FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchall()
            log_row = conn.execute(
                "SELECT log_path FROM task_runs WHERE task_name = 'summary' AND target_id = ? ORDER BY id DESC LIMIT 1",
                (str(paper_id),),
            ).fetchone()

        assert rows == [("v1", "glm-5.1", "zh")]
        assert status_rows == [("done",)]
        assert log_row is not None
        assert (project_root / log_row[0]).exists()
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_summarize_paper_records_failed_task_run(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, citation_status, created_at, updated_at) "
                "VALUES ('p-fail', 'done', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        _setup_parsed_paper(project_root, paper_id)
        monkeypatch.setattr("paperlab.llm.summary.call_llm", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))

        with pytest.raises(RuntimeError, match="boom"):
            summarize_paper(project_root, paper_id)

        with sqlite3.connect(db_path) as conn:
            status = conn.execute("SELECT summary_status FROM papers WHERE id = ?", (paper_id,)).fetchone()[0]
            task = conn.execute(
                "SELECT status FROM task_runs WHERE task_name = 'summary' AND target_id = ? ORDER BY id DESC LIMIT 1",
                (str(paper_id),),
            ).fetchone()[0]

        assert status == "failed"
        assert task == "failed"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_summarize_paper_recomputes_when_research_context_changes(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)

        now = "2026-04-10T00:00:00+00:00"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, citation_status, created_at, updated_at) "
                "VALUES ('p-context', 'done', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)",
                (now, now),
            )
            paper_id = cursor.lastrowid
            conn.commit()

        _setup_parsed_paper(project_root, paper_id)
        settings_path = project_root / "configs" / "app.yaml"
        original = settings_path.read_text(encoding="utf-8")
        (project_root / "configs" / "prompts" / "summary_system_v1.txt").write_text(
            "system {research_context}",
            encoding="utf-8",
        )

        calls: list[str] = []

        def fake_call_llm(**kwargs):
            calls.append(kwargs["system_prompt"])
            return json.dumps({
                "problem": kwargs["system_prompt"],
                "main_contributions": [],
                "core_innovations": [],
                "method_summary": "m",
                "experiment_summary": "e",
                "limitations": [],
                "key_takeaways": [],
                "relation_to_user_research": "r",
                "evidence": [],
            })

        monkeypatch.setattr("paperlab.llm.summary.call_llm", fake_call_llm)

        first = summarize_paper(project_root, paper_id)
        settings_path.write_text(
            original.replace(
                "research_context: multi-agent reinforcement learning",
                "research_context: causal inference",
            ),
            encoding="utf-8",
        )
        second = summarize_paper(project_root, paper_id)

        assert len(calls) == 2
        assert first["problem"] != second["problem"]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_build_summary_md_supports_biomedical_schema():
    biomed_summary = {
        "study_question": "Does treatment X reduce blood pressure?",
        "study_design": "Randomized controlled trial",
        "participants": "120 adults",
        "intervention": "Treatment X",
        "comparator": "Placebo",
        "primary_outcome": "Systolic blood pressure at 12 weeks",
        "main_findings": "Treatment X lowered blood pressure by 8 mmHg.",
        "limitations_bias": "Single-center study",
        "clinical_relevance": "Useful for moderate hypertension",
        "evidence_anchors": [{"claim": "BP reduction", "quote": "Results paragraph 2"}],
    }

    md = _build_summary_md("Bio Paper", biomed_summary)

    assert "# Bio Paper" in md
    assert "## 研究问题" in md
    assert "Does treatment X reduce blood pressure?" in md
    assert "## 主要发现" in md
    assert "Treatment X lowered blood pressure by 8 mmHg." in md
    assert "## 证据锚点" in md
    assert "BP reduction" in md
