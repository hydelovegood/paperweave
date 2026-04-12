from __future__ import annotations

import logging
from pathlib import Path

from paperlab.config import load_settings
from paperlab.config.settings import REQUIRED_PROMPT_FILES

log = logging.getLogger(__name__)


def run_doctor(project_root: Path | str, check_llm: bool = False) -> dict:
    root = Path(project_root).expanduser().resolve()
    config_path = root / "configs" / "app.yaml"
    prompts_ok = all((root / "configs" / "prompts" / filename).exists() for filename in REQUIRED_PROMPT_FILES)

    report = {
        "config": config_path.exists(),
        "prompts": prompts_ok,
        "database": False,
        "dependencies": _dependency_status(),
        "llm_check": None,
    }

    if not report["config"]:
        return report

    settings = load_settings(root, require_prompts=False)
    db_path = (root / settings.database.path).resolve()
    report["database"] = db_path.exists()

    if check_llm:
        from paperlab.llm.client import call_llm, extract_json_object

        raw = call_llm(
            api_key=settings.secrets.openai_api_key,
            base_url=settings.llm.base_url,
            model=settings.llm.summary_model,
            system_prompt="Return only strict JSON.",
            user_prompt='Return {"status":"ok"}',
            max_retries=1,
        )
        report["llm_check"] = extract_json_object(raw)

    return report


def _dependency_status() -> dict[str, bool]:
    results: dict[str, bool] = {}
    for module_name in ("openai", "requests", "fitz", "deepxiv_sdk"):
        try:
            __import__(module_name)
            results[module_name] = True
        except ImportError:
            results[module_name] = False
    return results
