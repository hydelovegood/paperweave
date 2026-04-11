from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from paperlab.parsing.classifier import classify_paper


def test_classify_by_pmid():
    assert classify_paper({"pmid": "12345678"}) == "biomedical"


def test_classify_by_mesh_terms():
    assert classify_paper({"mesh_terms": ["Hypertension"]}) == "biomedical"


def test_classify_by_publication_type():
    assert classify_paper({"publication_type": "Clinical Trial"}) == "biomedical"
    assert classify_paper({"publication_type": "Randomized Controlled Trial"}) == "biomedical"


def test_classify_by_journal():
    assert classify_paper({"journal": "The Lancet"}) == "biomedical"
    assert classify_paper({"journal": "New England Journal of Medicine"}) == "biomedical"


def test_classify_cs_by_arxiv():
    assert classify_paper({"arxiv_id": "2401.12345"}) == "cs"


def test_classify_general():
    assert classify_paper({}) == "general"
    assert classify_paper({"title": "Some paper"}) == "general"


def test_biomed_takes_priority_over_arxiv():
    assert classify_paper({"arxiv_id": "2401.12345", "pmid": "99999"}) == "biomedical"


def _setup_project(root: Path):
    prompts_dir = root / "configs" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (root / "configs" / "app.yaml").write_text(
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
            "  download_oa_only: false",
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
    (prompts_dir / "summary_biomed_v1.txt").write_text(
        "biomed summary prompt {research_context}", encoding="utf-8",
    )
    (prompts_dir / "summary_biomed_user_v1.txt").write_text(
        "biomed user {paper_title}", encoding="utf-8",
    )
    (prompts_dir / "qa_biomed_v1.txt").write_text(
        "biomed qa prompt", encoding="utf-8",
    )
    (prompts_dir / "qa_biomed_user_v1.txt").write_text(
        "biomed qa user {paper_title}", encoding="utf-8",
    )


def test_summary_routes_biomed_prompt(monkeypatch):
    from paperlab.cli.init_cmd import init_project
    from paperlab.llm.summary import summarize_paper

    root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    root.mkdir(parents=True, exist_ok=True)
    _setup_project(root)

    try:
        db_path = init_project(root)
        parsed_dir = root / "data" / "parsed"
        parsed_dir.mkdir(parents=True, exist_ok=True)

        biomed_paper = {
            "title": "A Novel Treatment",
            "abstract": "We conducted an RCT.",
            "pmid": "12345678",
            "mesh_terms": ["Hypertension"],
            "sections": [{"name": "Introduction", "text": "Test text"}],
        }
        (parsed_dir / "1.json").write_text(json.dumps(biomed_paper), encoding="utf-8")

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, created_at, updated_at) "
                "VALUES ('paper-1', 'done', 'pending', 'pending', 'pending', 'pending', '2024-01-01', '2024-01-01')",
            )
            conn.commit()

        captured_prompt = {}

        def fake_call_llm(**kwargs):
            captured_prompt["system"] = kwargs.get("system_prompt", "")
            captured_prompt["model"] = kwargs.get("model", "")
            return json.dumps({
                "study_question": "Does drug X work?",
                "study_design": "RCT",
                "participants": "500 adults",
                "intervention": "Drug X 10mg",
                "comparator": "Placebo",
                "primary_outcome": "Systolic BP change",
                "main_findings": "Lowered by 12 mmHg",
                "limitations_bias": "Single center",
                "clinical_relevance": "May reduce CV events",
                "evidence_anchors": [{"claim": "Effective", "quote": "Results section"}],
            })

        monkeypatch.setattr("paperlab.llm.summary.call_llm", fake_call_llm)

        result = summarize_paper(root, 1)
        assert "study_design" in result
        assert "biomed" in captured_prompt["system"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_qa_routes_biomed_types(monkeypatch):
    from paperlab.cli.init_cmd import init_project
    from paperlab.llm.qa import generate_qa

    root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    root.mkdir(parents=True, exist_ok=True)
    _setup_project(root)

    try:
        db_path = init_project(root)
        parsed_dir = root / "data" / "parsed"
        parsed_dir.mkdir(parents=True, exist_ok=True)

        biomed_paper = {
            "title": "Surgical Outcomes Study",
            "abstract": "A cohort study.",
            "pmid": "99999",
            "sections": [{"name": "Methods", "text": "We enrolled 200 patients."}],
        }
        (parsed_dir / "1.json").write_text(json.dumps(biomed_paper), encoding="utf-8")

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO papers (paper_uid, parse_status, summary_status, enrich_status, qa_status, graph_status, created_at, updated_at) "
                "VALUES ('paper-1', 'done', 'done', 'pending', 'pending', 'pending', '2024-01-01', '2024-01-01')",
            )
            conn.commit()

        def fake_call_llm(**kwargs):
            return json.dumps([
                {"type": "methodological", "question": "Was blinding adequate?", "answer": "No, open label.", "category": "偏倚评估", "depth_level": 3, "answer_mode": "explicit", "evidence": "Methods"},
                {"type": "clinical", "question": "Can this apply to elderly?", "answer": "Sample was 40-60.", "category": "临床适用性", "depth_level": 2, "answer_mode": "inferred", "evidence": "Table 1"},
                {"type": "interview", "question": "Why choose this design?", "answer": "RCT not ethical.", "category": "研究设计", "depth_level": 2, "answer_mode": "explicit", "evidence": "Introduction"},
            ])

        monkeypatch.setattr("paperlab.llm.qa.call_llm", fake_call_llm)

        result = generate_qa(root, 1)
        assert len(result) == 3
        types = [item["type"] for item in result]
        assert "methodological" in types
    finally:
        shutil.rmtree(root, ignore_errors=True)
