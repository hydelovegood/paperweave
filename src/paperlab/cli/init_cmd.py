from __future__ import annotations

from pathlib import Path

from paperlab.config import load_settings
from paperlab.storage.db import initialize_database


DEFAULT_CONFIG_TEXT = """database:
  path: db/papers.db

paths:
  parsed_dir: data/parsed
  cache_dir: data/cache
  export_dir: data/exports
  logs_dir: data/logs

parsing:
  prefer_deepxiv_for_arxiv: true
  pymupdf_section_split: true

llm:
  base_url: https://open.bigmodel.cn/api/coding/paas/v4
  summary_model: glm-5.1
  qa_model: glm-5.1
  lang: zh
  max_retries: 2
  research_context: "多智能体强化学习 (multi-agent reinforcement learning)"

citations:
  default_year_start: 2024
  default_year_end: 2026
  default_max_results: 30
  download_oa_only: true

export:
  summary_file: data/exports/summary.md
  qa_file: data/exports/QA.md
"""

DEFAULT_ENV_EXAMPLE = """DEEPXIV_TOKEN=
OPENAI_API_KEY=
SEMANTIC_SCHOLAR_API_KEY=
UNPAYWALL_EMAIL=
NCBI_API_KEY=
"""

DEFAULT_PROMPTS = {
    "summary_system_v1.txt": "You are a strict research assistant. Return only valid JSON.",
    "summary_user_v1.txt": "Summarize the paper.\nTitle: {paper_title}\nAbstract: {paper_abstract}\nSections:\n{paper_sections}",
    "qa_system_v1.txt": "You are a strict research assistant. Return only valid JSON.",
    "qa_user_v1.txt": "Generate deep QA for the paper.\nTitle: {paper_title}\nAbstract: {paper_abstract}\nSections:\n{paper_sections}",
    "summary_biomed_v1.txt": "You are a biomedical research assistant. Return only valid JSON. Context: {research_context}",
    "summary_biomed_user_v1.txt": "Summarize the biomedical paper.\nTitle: {paper_title}\nAbstract: {paper_abstract}\nSections:\n{paper_sections}",
    "qa_biomed_v1.txt": "You are a biomedical research assistant. Return only valid JSON.",
    "qa_biomed_user_v1.txt": "Generate biomedical QA for the paper.\nTitle: {paper_title}\nAbstract: {paper_abstract}\nSections:\n{paper_sections}",
}


def init_project(project_root: Path | str) -> Path:
    root = Path(project_root).expanduser().resolve()
    _bootstrap_project_files(root)
    settings = load_settings(root)

    for relative_path in (
        settings.paths.parsed_dir,
        settings.paths.cache_dir,
        settings.paths.export_dir,
        settings.paths.logs_dir,
        settings.database.path.parent,
    ):
        (root / relative_path).mkdir(parents=True, exist_ok=True)

    return initialize_database(root / settings.database.path)


def _bootstrap_project_files(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    config_dir = root / "configs"
    prompts_dir = config_dir / "prompts"
    config_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "app.yaml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")

    env_example_path = root / ".env.example"
    if not env_example_path.exists():
        env_example_path.write_text(DEFAULT_ENV_EXAMPLE, encoding="utf-8")

    for filename, content in DEFAULT_PROMPTS.items():
        prompt_path = prompts_dir / filename
        if not prompt_path.exists():
            prompt_path.write_text(content, encoding="utf-8")
