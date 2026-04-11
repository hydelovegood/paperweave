from __future__ import annotations

import argparse
from dataclasses import fields
from pathlib import Path

from paperlab.config import load_settings


def run_doctor(project_root: Path | str, check_llm: bool = False) -> dict:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    db_path = (root / settings.database.path).resolve()

    report = {
        "config": (root / "configs" / "app.yaml").exists(),
        "prompts": all(
            (root / getattr(settings.prompts, field.name)).exists()
            for field in fields(settings.prompts)
        ),
        "database": db_path.exists(),
        "dependencies": _dependency_status(),
        "llm_check": None,
    }

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperctl-doctor")
    parser.add_argument("project_root")
    parser.add_argument("--check-llm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_doctor(args.project_root, check_llm=args.check_llm)
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0
