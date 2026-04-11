from dataclasses import is_dataclass
from pathlib import Path
import tempfile

import pytest

from paperlab.config.settings import load_settings


def _write_project_files(root: Path, *, include_prompt: bool = True) -> None:
    (root / "configs" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "db").mkdir(parents=True, exist_ok=True)

    (root / "configs" / "app.yaml").write_text(
        "\n".join(
            [
                "database:",
                "  path: db/papers.db",
                "",
                "paths:",
                "  parsed_dir: data/parsed",
                "  cache_dir: data/cache",
                "  export_dir: data/exports",
                "  logs_dir: data/logs",
                "",
                "parsing:",
                "  prefer_deepxiv_for_arxiv: true",
                "  pymupdf_section_split: true",
                "",
                "llm:",
                "  summary_model: gpt-5.4",
                "  qa_model: gpt-5.4",
                "  lang: zh",
                "  max_retries: 2",
                "",
                "citations:",
                "  default_year_start: 2024",
                "  default_year_end: 2026",
                "  default_max_results: 30",
                "  download_oa_only: true",
                "",
                "export:",
                "  summary_file: data/exports/summary.md",
                "  qa_file: data/exports/QA.md",
            ]
        ),
        encoding="utf-8",
    )

    if include_prompt:
        (root / "configs" / "prompts" / "summary_system_v1.txt").write_text(
            "summary system", encoding="utf-8"
        )
        (root / "configs" / "prompts" / "summary_user_v1.txt").write_text(
            "summary user", encoding="utf-8"
        )
        (root / "configs" / "prompts" / "qa_system_v1.txt").write_text(
            "qa system", encoding="utf-8"
        )
        (root / "configs" / "prompts" / "qa_user_v1.txt").write_text(
            "qa user", encoding="utf-8"
        )


def test_load_settings_reads_default_config_and_env(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_project_files(root)
        (root / ".env").write_text(
            "\n".join(
                [
                    "DEEPXIV_TOKEN=deepxiv-test-token",
                    "OPENAI_API_KEY=openai-test-key",
                    "SEMANTIC_SCHOLAR_API_KEY=s2-test-key",
                    "UNPAYWALL_EMAIL=test@example.com",
                ]
            ),
            encoding="utf-8",
        )

        monkeypatch.delenv("DEEPXIV_TOKEN", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
        monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)

        settings = load_settings(root)

        assert is_dataclass(settings)
        assert settings.database.path == Path("db/papers.db")
        assert settings.paths.export_dir == Path("data/exports")
        assert settings.llm.summary_model == "gpt-5.4"
        assert settings.secrets.deepxiv_token == "deepxiv-test-token"
        assert settings.secrets.openai_api_key == "openai-test-key"
        assert settings.secrets.semantic_scholar_api_key == "s2-test-key"
        assert settings.secrets.unpaywall_email == "test@example.com"


def test_missing_prompt_path_raises_clear_error():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_project_files(root, include_prompt=False)

        with pytest.raises(FileNotFoundError, match="summary_system_v1.txt"):
            load_settings(root)
