from __future__ import annotations

import shutil
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
            "export:",
            "  summary_file: data/exports/summary.md",
            "  qa_file: data/exports/QA.md",
            "citations:",
            "  default_year_start: 2024",
            "  default_year_end: 2026",
            "  default_max_results: 30",
            "  download_oa_only: true",
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


def test_doctor_reports_core_checks(monkeypatch):
    project_root = Path(__file__).resolve().parent / ".tmp" / str(uuid4())
    project_root.mkdir(parents=True, exist_ok=True)
    _write_project_files(project_root)

    try:
        from paperlab.cli.init_cmd import init_project
        from paperlab.cli.doctor_cmd import run_doctor

        db_path = init_project(project_root)
        assert db_path.exists()

        monkeypatch.setattr("paperlab.cli.doctor_cmd._dependency_status", lambda: {"openai": True, "requests": True, "fitz": True, "deepxiv_sdk": True})

        report = run_doctor(project_root, check_llm=False)
        assert report["database"] is True
        assert report["config"] is True
        assert report["prompts"] is True
        assert report["dependencies"]["fitz"] is True
        assert report["llm_check"] is None
    finally:
        shutil.rmtree(project_root, ignore_errors=True)
