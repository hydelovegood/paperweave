from __future__ import annotations

from pathlib import Path


def infer_prompt_version(*paths: Path) -> str:
    for path in paths:
        for part in path.stem.split("_"):
            if part.startswith("v") and part[1:].isdigit():
                return part
    return "v1"


def write_llm_log(root: Path, task_name: str, paper_id: int, started_at: str, raw: str) -> str:
    safe_stamp = started_at.replace(":", "-")
    log_dir = root / "data" / "logs" / "llm"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{task_name}_paper_{paper_id}_{safe_stamp}.txt"
    log_path.write_text(raw, encoding="utf-8")
    return str(log_path.relative_to(root))
