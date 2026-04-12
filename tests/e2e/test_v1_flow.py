"""V1 end-to-end acceptance test.

Full flow: init → ingest → parse → summarize → qa → citations → export.
All external calls (LLM, APIs) are mocked.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4


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


def _sample_summary():
    return {
        "problem": "How to scale multi-agent RL",
        "main_contributions": ["New credit assignment method"],
        "core_innovations": ["Decentralized coordination"],
        "method_summary": "Uses PPO with multi-agent credit assignment",
        "experiment_summary": "Tested on StarCraft II",
        "limitations": ["Only cooperative tasks"],
        "key_takeaways": ["Scalable MARL is feasible"],
        "relation_to_user_research": "Directly relevant to MARL",
        "evidence": [{"claim": "Converges", "quote": "Figure 3"}],
    }


def _sample_qa():
    return [
        {"type": "reviewer", "question": "Why not competitive?", "answer": "Scope limitation", "category": "实验", "depth_level": 3, "answer_mode": "explicit", "evidence": "Section 1"},
        {"type": "interview", "question": "How does credit assignment work?", "answer": "Counterfactual baseline", "category": "方法论", "depth_level": 2, "answer_mode": "explicit", "evidence": "Eq 4"},
    ]


def _sample_citations():
    return [
        {"doi": "10.1234/citer1", "title": "Citing Paper", "year": 2025, "is_oa": True, "oa_url": "https://oa.example.com/citer1.pdf"},
    ]


def test_v1_full_flow(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    pdf_dir = project_root / "imports"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "sample.pdf").write_bytes(b"%PDF-1.4 fake content for testing")

    try:
        # --- Step 1: Init ---
        from paperlab.cli.init_cmd import init_project
        db_path = init_project(project_root)
        assert db_path.exists()

        # --- Step 2: Ingest ---
        from paperlab.cli.ingest_cmd import ingest_path
        result = ingest_path(project_root, pdf_dir)
        assert result.registered == 1

        paper_id = None
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT id FROM papers").fetchone()
            paper_id = row[0]

        # --- Step 3: Parse ---
        from paperlab.parsing.canonical import CanonicalPaper, CanonicalSection

        fake_paper = CanonicalPaper(
            source="pymupdf",
            paper_id="paper-test",
            title="Sample MARL Paper",
            authors=[{"name": "Alice"}],
            abstract="We study multi-agent reinforcement learning.",
            year=2024,
            venue="arXiv",
            doi=None,
            arxiv_id=None,
            sections=[
                CanonicalSection(name="Introduction", text="MARL is important.", order=1),
                CanonicalSection(name="Method", text="We propose MAPPO.", order=2),
            ],
            references_raw=[],
            full_text="MARL is important. We propose MAPPO.",
            parse_quality=0.8,
        )

        monkeypatch.setattr(
            "paperlab.parsing.pipeline.parse_document",
            lambda *a, **kw: fake_paper,
        )
        monkeypatch.setattr(
            "paperlab.enrich.biomed_pre_enrich.pre_enrich_biomed_metadata",
            lambda *args, **kwargs: None,
        )

        from paperlab.parsing.pipeline import parse_and_persist
        canonical = parse_and_persist(project_root, paper_id, pdf_dir / "sample.pdf")
        assert canonical.title == "Sample MARL Paper"

        # --- Step 4: Summarize ---
        monkeypatch.setattr(
            "paperlab.llm.summary.call_llm",
            lambda *a, **kw: json.dumps(_sample_summary()),
        )

        from paperlab.llm.summary import summarize_paper
        summary = summarize_paper(project_root, paper_id)
        assert summary["problem"] == "How to scale multi-agent RL"

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT summary_status FROM papers WHERE id = ?", (paper_id,)).fetchone()
            assert row[0] == "done"

        # --- Step 5: QA ---
        monkeypatch.setattr(
            "paperlab.llm.qa.call_llm",
            lambda *a, **kw: json.dumps(_sample_qa()),
        )

        from paperlab.llm.qa import generate_qa
        qa_items = generate_qa(project_root, paper_id)
        assert len(qa_items) == 2

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT qa_status FROM papers WHERE id = ?", (paper_id,)).fetchone()
            assert row[0] == "done"

        # --- Step 6: Citations ---
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.resolve_by_title",
            lambda *a, **kw: {"openalex_id": "W999", "doi": "10.1/marl", "title": "Sample MARL Paper", "year": 2024, "is_oa": True, "oa_url": None},
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.openalex.get_forward_citations",
            lambda *a, **kw: _sample_citations(),
        )
        monkeypatch.setattr(
            "paperlab.enrich.forward_citations.unpaywall.check_oa",
            lambda *a, **kw: None,
        )

        from paperlab.enrich.forward_citations import track_forward_citations
        citing_ids = track_forward_citations(project_root, paper_id)
        assert len(citing_ids) == 1

        with sqlite3.connect(db_path) as conn:
            edges = conn.execute("SELECT COUNT(*) FROM citation_edges WHERE cited_paper_id = ?", (paper_id,)).fetchone()
            links = conn.execute("SELECT COUNT(*) FROM external_links").fetchone()
            assert edges[0] == 1
            assert links[0] == 1

        # --- Step 7: Export ---
        from paperlab.export.summary_export import export_summary
        from paperlab.export.qa_export import export_qa

        summary_path = project_root / "data" / "exports" / "summary.md"
        qa_path = project_root / "data" / "exports" / "QA.md"

        s_count = export_summary(db_path, summary_path)
        q_count = export_qa(db_path, qa_path)

        assert s_count == 1
        assert summary_path.exists()
        assert "Sample MARL Paper" in summary_path.read_text(encoding="utf-8")

        assert q_count == 1
        assert qa_path.exists()
        assert "审稿人视角" in qa_path.read_text(encoding="utf-8")

    finally:
        shutil.rmtree(project_root, ignore_errors=True)
