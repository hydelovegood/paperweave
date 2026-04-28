from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from paperlab.cli.main import cli
from paperlab.parsing.canonical import CanonicalPaper, CanonicalSection


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


def _fake_paper(title: str = "Parsed Paper") -> CanonicalPaper:
    return CanonicalPaper(
        source="pymupdf",
        paper_id="paper-test",
        title=title,
        authors=[],
        abstract="Abstract",
        year=2026,
        venue="Test Venue",
        doi=None,
        arxiv_id=None,
        sections=[CanonicalSection(name="Introduction", text="Intro text", order=1)],
        references_raw=[],
        full_text="Intro text",
        parse_quality=0.8,
    )


def _sample_summary() -> dict:
    return {
        "problem": "Problem",
        "main_contributions": ["Contribution"],
        "core_innovations": ["Innovation"],
        "method_summary": "Method",
        "experiment_summary": "Experiment",
        "limitations": ["Limitation"],
        "key_takeaways": ["Takeaway"],
        "relation_to_user_research": "Relation",
        "evidence": [{"claim": "Claim", "quote": "Quote"}],
    }


def _sample_qa() -> list[dict]:
    return [
        {
            "type": "reviewer",
            "question": "Question?",
            "answer": "Answer.",
            "category": "method",
            "depth_level": 2,
            "answer_mode": "explicit",
            "evidence": "Evidence",
        }
    ]


def test_parse_and_run_help_are_registered() -> None:
    runner = CliRunner()

    parse_result = runner.invoke(cli, ["parse", "--help"])
    run_result = runner.invoke(cli, ["run", "--help"])

    assert parse_result.exit_code == 0
    assert run_result.exit_code == 0


def test_parse_path_processes_changed_papers_and_skips_done(monkeypatch) -> None:
    project_root = _build_project_root()
    imports = project_root / "imports"
    imports.mkdir(parents=True)
    pending_pdf = imports / "pending.pdf"
    done_pdf = imports / "done.pdf"
    pending_pdf.write_bytes(b"pending")
    done_pdf.write_bytes(b"done")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        db_path = init_project(project_root)
        ingest_path(project_root, imports)

        with sqlite3.connect(db_path) as conn:
            done_id = conn.execute(
                "SELECT p.id FROM papers p JOIN paper_files pf ON pf.paper_id = p.id JOIN files f ON f.id = pf.file_id WHERE f.filename = ?",
                ("done.pdf",),
            ).fetchone()[0]
            conn.execute("UPDATE papers SET parse_status = 'done' WHERE id = ?", (done_id,))
            conn.commit()

        calls: list[tuple[int, Path]] = []

        def fake_parse(project_root_arg, paper_id, input_path, deepxiv_token=None):
            calls.append((paper_id, Path(input_path)))
            return _fake_paper()

        monkeypatch.setattr("paperlab.cli.parse_cmd.parse_and_persist", fake_parse)

        from paperlab.cli.parse_cmd import parse_path

        result = parse_path(project_root)

        assert result.completed == [calls[0][0]]
        assert result.failed == []
        assert [path.name for _, path in calls] == ["pending.pdf"]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_parse_path_fail_fast_stops_after_first_failure(monkeypatch) -> None:
    project_root = _build_project_root()
    imports = project_root / "imports"
    imports.mkdir(parents=True)
    (imports / "a.pdf").write_bytes(b"a")
    (imports / "b.pdf").write_bytes(b"b")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        init_project(project_root)
        ingest_path(project_root, imports)

        calls = 0

        def fail_parse(*args, **kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("parse failed")

        monkeypatch.setattr("paperlab.cli.parse_cmd.parse_and_persist", fail_parse)

        from paperlab.cli.parse_cmd import parse_path

        with pytest.raises(RuntimeError, match="parse failed"):
            parse_path(project_root, fail_fast=True)

        assert calls == 1
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_run_path_ingests_parses_summarizes_qa_and_exports(monkeypatch) -> None:
    project_root = _build_project_root()
    imports = project_root / "imports"
    imports.mkdir(parents=True)
    (imports / "paper.pdf").write_bytes(b"pdf")

    try:
        from paperlab.cli.init_cmd import init_project

        init_project(project_root)

        def fake_parse(project_root_arg, paper_id, input_path, deepxiv_token=None):
            paper = _fake_paper("Run Paper")
            parsed_dir = Path(project_root_arg) / "data" / "parsed"
            parsed_dir.mkdir(parents=True, exist_ok=True)
            (parsed_dir / f"{paper_id}.json").write_text(
                json.dumps(paper.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
            with sqlite3.connect(Path(project_root_arg) / "db" / "papers.db") as conn:
                conn.execute(
                    "UPDATE papers SET canonical_title = ?, parse_status = 'done' WHERE id = ?",
                    (paper.title, paper_id),
                )
                conn.commit()
            return paper

        monkeypatch.setattr("paperlab.cli.parse_cmd.parse_and_persist", fake_parse)
        monkeypatch.setattr(
            "paperlab.llm.summary.call_llm",
            lambda *args, **kwargs: json.dumps(_sample_summary()),
        )
        monkeypatch.setattr(
            "paperlab.llm.qa.call_llm",
            lambda *args, **kwargs: json.dumps(_sample_qa()),
        )

        from paperlab.cli.run_cmd import run_path

        result = run_path(project_root, imports)

        assert result.ingest.registered == 1
        assert result.parse.completed == [1]
        assert result.summarized == [1]
        assert result.qa == [1]
        assert result.summary_exports == 1
        assert result.qa_exports == 1
        assert (project_root / "data" / "exports" / "summary.md").exists()
        assert (project_root / "data" / "exports" / "QA.md").exists()
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_run_path_force_reprocesses_done_papers(monkeypatch) -> None:
    project_root = _build_project_root()
    imports = project_root / "imports"
    imports.mkdir(parents=True)
    paper_path = imports / "paper.pdf"
    paper_path.write_bytes(b"pdf")

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.ingest_cmd import ingest_path

        db_path = init_project(project_root)
        ingest_path(project_root, paper_path)

        parsed_dir = project_root / "data" / "parsed"
        parsed_dir.mkdir(parents=True, exist_ok=True)
        parsed_dir.joinpath("1.json").write_text(
            json.dumps(_fake_paper("Done Paper").to_dict(), ensure_ascii=False),
            encoding="utf-8",
        )
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE papers SET canonical_title = 'Done Paper', parse_status = 'done', summary_status = 'done', qa_status = 'done'"
            )
            conn.execute(
                """
                INSERT INTO summaries (paper_id, version, lang, model_name, summary_json, summary_md, created_at)
                VALUES (1, 'v1', 'zh', 'glm-5.1', '{}', '# Old', '2026-04-28T00:00:00+00:00')
                """
            )
            conn.execute(
                """
                INSERT INTO qa_items (paper_id, version, qa_type, question, answer_text, created_at)
                VALUES (1, 'v1', 'reviewer', 'Old?', 'Old.', '2026-04-28T00:00:00+00:00')
                """
            )
            conn.commit()

        parse_calls = 0

        def fake_parse(project_root_arg, paper_id, input_path, deepxiv_token=None):
            nonlocal parse_calls
            parse_calls += 1
            return _fake_paper("Done Paper")

        monkeypatch.setattr("paperlab.cli.parse_cmd.parse_and_persist", fake_parse)
        monkeypatch.setattr(
            "paperlab.llm.summary.call_llm",
            lambda *args, **kwargs: json.dumps(_sample_summary()),
        )
        monkeypatch.setattr(
            "paperlab.llm.qa.call_llm",
            lambda *args, **kwargs: json.dumps(_sample_qa()),
        )

        from paperlab.cli.run_cmd import run_path

        result = run_path(project_root, imports, force=True)

        assert parse_calls == 1
        assert result.parse.completed == [1]
        assert result.summarized == [1]
        assert result.qa == [1]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
