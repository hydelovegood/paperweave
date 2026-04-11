from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any

import yaml


DEFAULT_CONFIG_RELATIVE_PATH = Path("configs/app.yaml")
DEFAULT_ENV_RELATIVE_PATH = Path(".env")
REQUIRED_PROMPT_FILES = (
    "summary_system_v1.txt",
    "summary_user_v1.txt",
    "qa_system_v1.txt",
    "qa_user_v1.txt",
)


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    path: Path


@dataclass(frozen=True, slots=True)
class PathsSettings:
    parsed_dir: Path
    cache_dir: Path
    export_dir: Path
    logs_dir: Path


@dataclass(frozen=True, slots=True)
class ParsingSettings:
    prefer_deepxiv_for_arxiv: bool
    pymupdf_section_split: bool


@dataclass(frozen=True, slots=True)
class LLMSettings:
    base_url: str
    summary_model: str
    qa_model: str
    lang: str
    max_retries: int
    research_context: str


@dataclass(frozen=True, slots=True)
class CitationSettings:
    default_year_start: int
    default_year_end: int
    default_max_results: int
    download_oa_only: bool


@dataclass(frozen=True, slots=True)
class ExportSettings:
    summary_file: Path
    qa_file: Path


@dataclass(frozen=True, slots=True)
class SecretSettings:
    deepxiv_token: str
    openai_api_key: str
    semantic_scholar_api_key: str
    unpaywall_email: str
    ncbi_api_key: str


@dataclass(frozen=True, slots=True)
class PromptSettings:
    summary_system: Path
    summary_user: Path
    qa_system: Path
    qa_user: Path


@dataclass(frozen=True, slots=True)
class PaperLabSettings:
    root_dir: Path
    database: DatabaseSettings
    paths: PathsSettings
    parsing: ParsingSettings
    llm: LLMSettings
    citations: CitationSettings
    export: ExportSettings
    secrets: SecretSettings
    prompts: PromptSettings


def load_settings(project_root: Path | str, config_path: Path | str | None = None) -> PaperLabSettings:
    root = Path(project_root).expanduser().resolve()
    config_file = Path(config_path).expanduser().resolve() if config_path else root / DEFAULT_CONFIG_RELATIVE_PATH
    env_file = root / DEFAULT_ENV_RELATIVE_PATH

    config_data = _load_config_file(config_file)
    env_data = _load_env_file(env_file)
    merged_env = {**env_data, **os.environ}

    prompts = PromptSettings(
        summary_system=_require_prompt_file(root, "summary_system_v1.txt"),
        summary_user=_require_prompt_file(root, "summary_user_v1.txt"),
        qa_system=_require_prompt_file(root, "qa_system_v1.txt"),
        qa_user=_require_prompt_file(root, "qa_user_v1.txt"),
    )

    return PaperLabSettings(
        root_dir=root,
        database=DatabaseSettings(path=_as_path(config_data["database"]["path"])),
        paths=PathsSettings(
            parsed_dir=_as_path(config_data["paths"]["parsed_dir"]),
            cache_dir=_as_path(config_data["paths"]["cache_dir"]),
            export_dir=_as_path(config_data["paths"]["export_dir"]),
            logs_dir=_as_path(config_data["paths"]["logs_dir"]),
        ),
        parsing=ParsingSettings(
            prefer_deepxiv_for_arxiv=_as_bool(config_data["parsing"]["prefer_deepxiv_for_arxiv"]),
            pymupdf_section_split=_as_bool(config_data["parsing"]["pymupdf_section_split"]),
        ),
        llm=LLMSettings(
            base_url=str(config_data["llm"].get("base_url", "https://open.bigmodel.cn/api/coding/paas/v4")),
            summary_model=str(config_data["llm"]["summary_model"]),
            qa_model=str(config_data["llm"]["qa_model"]),
            lang=str(config_data["llm"]["lang"]),
            max_retries=_as_int(config_data["llm"]["max_retries"]),
            research_context=str(config_data["llm"].get("research_context", "")),
        ),
        citations=CitationSettings(
            default_year_start=_as_int(config_data["citations"]["default_year_start"]),
            default_year_end=_as_int(config_data["citations"]["default_year_end"]),
            default_max_results=_as_int(config_data["citations"]["default_max_results"]),
            download_oa_only=_as_bool(config_data["citations"]["download_oa_only"]),
        ),
        export=ExportSettings(
            summary_file=_as_path(config_data["export"]["summary_file"]),
            qa_file=_as_path(config_data["export"]["qa_file"]),
        ),
        secrets=SecretSettings(
            deepxiv_token=merged_env.get("DEEPXIV_TOKEN", ""),
            openai_api_key=merged_env.get("OPENAI_API_KEY", ""),
            semantic_scholar_api_key=merged_env.get("SEMANTIC_SCHOLAR_API_KEY", ""),
            unpaywall_email=merged_env.get("UNPAYWALL_EMAIL", ""),
            ncbi_api_key=merged_env.get("NCBI_API_KEY", ""),
        ),
        prompts=prompts,
    )


def _load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must parse to a mapping: {path}")
    return loaded


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _require_prompt_file(root: Path, filename: str) -> Path:
    prompt_path = root / "configs" / "prompts" / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Missing required prompt file: {prompt_path}")
    return prompt_path.relative_to(root)


def _as_path(value: Any) -> Path:
    return Path(str(value))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
    raise ValueError(f"Expected boolean value, got {value!r}")


def _as_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected integer value, got {value!r}") from exc
