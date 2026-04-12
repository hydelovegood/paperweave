from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from paperlab.config import load_settings
from paperlab.llm.client import call_llm, extract_json_array
from paperlab.llm.task_common import infer_prompt_version, write_llm_log
from paperlab.storage.status import compute_qa_input_hash
from paperlab.storage.task_runs import is_task_completed, record_task_run


QA_TYPES = ("reviewer", "interview", "author_defense")
BIOMED_QA_TYPES = ("methodological", "clinical", "interview")
REQUIRED_QA_FIELDS = ("type", "question", "answer", "category", "depth_level", "answer_mode", "evidence")


def generate_qa(project_root: Path | str, paper_id: int) -> list[dict]:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)

    db_path = (root / settings.database.path).resolve()
    parsed_path = root / settings.paths.parsed_dir / f"{paper_id}.json"

    if not parsed_path.exists():
        raise FileNotFoundError(f"Parsed paper not found: {parsed_path}")

    paper = json.loads(parsed_path.read_text(encoding="utf-8"))

    from paperlab.parsing.classifier import classify_paper
    paper_type = classify_paper(paper)

    if paper_type == "biomedical":
        system_prompt_path = root / "configs" / "prompts" / "qa_biomed_v1.txt"
        user_prompt_path = root / "configs" / "prompts" / "qa_biomed_user_v1.txt"
        if not system_prompt_path.exists():
            system_prompt_path = root / settings.prompts.qa_system
            user_prompt_path = root / settings.prompts.qa_user
        valid_types = BIOMED_QA_TYPES
    else:
        system_prompt_path = root / settings.prompts.qa_system
        user_prompt_path = root / settings.prompts.qa_user
        valid_types = QA_TYPES

    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    user_template = user_prompt_path.read_text(encoding="utf-8")
    sections_text = "\n\n".join(
        f"## {s['name']}\n{s['text']}" for s in paper.get("sections", [])
    )
    user_prompt = user_template.replace("{paper_title}", paper.get("title", ""))
    user_prompt = user_prompt.replace("{paper_abstract}", paper.get("abstract", ""))
    user_prompt = user_prompt.replace("{paper_sections}", sections_text)

    version = infer_prompt_version(system_prompt_path, user_prompt_path)

    input_hash = compute_qa_input_hash(
        parsed_path, system_prompt, user_prompt, settings.llm.qa_model, settings.llm.lang,
    )
    if _can_reuse_existing_qa(db_path, paper_id, input_hash):
        return _load_existing_qa(db_path, paper_id)

    started_at = datetime.now(timezone.utc).isoformat()

    raw = ""
    log_path = None
    try:
        raw = call_llm(
            api_key=settings.secrets.openai_api_key,
            base_url=settings.llm.base_url,
            model=settings.llm.qa_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=settings.llm.max_retries,
        )

        log_path = write_llm_log(root, "qa", paper_id, started_at, raw)
        qa_items = extract_json_array(raw)
        _validate_qa_items(qa_items, valid_types)

        ended_at = datetime.now(timezone.utc).isoformat()
        now = ended_at
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM qa_items WHERE paper_id = ?", (paper_id,))
            for item in qa_items:
                conn.execute(
                    """
                    INSERT INTO qa_items (paper_id, version, qa_type, category, depth_level, question, answer_text, answer_mode, evidence_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        paper_id,
                        version,
                        item["type"],
                        item.get("category"),
                        item.get("depth_level", 2),
                        item["question"],
                        item["answer"],
                        item.get("answer_mode"),
                        json.dumps(item.get("evidence", []), ensure_ascii=False),
                        now,
                    ),
                )
            conn.execute(
                "UPDATE papers SET qa_status = 'done', updated_at = ? WHERE id = ?",
                (now, paper_id),
            )
            conn.commit()

        record_task_run(
            db_path, "qa", "paper", str(paper_id), settings.llm.qa_model, "done",
            input_hash, started_at, ended_at, log_path,
        )

        return qa_items
    except Exception:
        ended_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE papers SET qa_status = 'failed', updated_at = ? WHERE id = ?",
                (ended_at, paper_id),
            )
            conn.commit()
        record_task_run(
            db_path, "qa", "paper", str(paper_id), settings.llm.qa_model, "failed",
            input_hash, started_at, ended_at, log_path,
        )
        raise


def _load_existing_qa(db_path: Path, paper_id: int) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT qa_type, category, depth_level, question, answer_text, answer_mode, evidence_json FROM qa_items WHERE paper_id = ? ORDER BY id",
            (paper_id,),
        ).fetchall()
    return [
        {
            "type": r[0],
            "category": r[1],
            "depth_level": r[2],
            "question": r[3],
            "answer": r[4],
            "answer_mode": r[5],
            "evidence": json.loads(r[6]) if r[6] else [],
        }
        for r in rows
    ]


def _can_reuse_existing_qa(db_path: Path, paper_id: int, input_hash: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT qa_status FROM papers WHERE id = ?",
            (paper_id,),
        ).fetchone()

    if row is None:
        return False
    if row[0] in {"stale", "failed"}:
        return False
    return is_task_completed(db_path, "qa", str(paper_id), input_hash)


def select_papers_for_qa(db_path: Path | str) -> list[int]:
    db = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT id FROM papers WHERE qa_status IN ('pending', 'stale', 'failed') AND parse_status = 'done' ORDER BY id"
        ).fetchall()
    return [row[0] for row in rows]


def _validate_qa_items(items: list[dict], valid_types: tuple[str, ...] = QA_TYPES) -> None:
    for i, item in enumerate(items):
        missing = [f for f in REQUIRED_QA_FIELDS if f not in item]
        if missing:
            raise ValueError(f"QA item {i} missing required fields: {', '.join(missing)}")
        if item["type"] not in valid_types:
            raise ValueError(f"QA item {i} has invalid type: {item['type']}")
