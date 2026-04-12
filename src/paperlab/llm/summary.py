from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from paperlab.config import load_settings
from paperlab.llm.client import call_llm, extract_json_object
from paperlab.llm.task_common import infer_prompt_version, write_llm_log
from paperlab.storage.status import compute_summary_input_hash
from paperlab.storage.task_runs import is_task_completed, record_task_run


REQUIRED_SUMMARY_FIELDS = (
    "problem",
    "main_contributions",
    "core_innovations",
    "method_summary",
    "experiment_summary",
    "limitations",
    "key_takeaways",
    "relation_to_user_research",
    "evidence",
)

REQUIRED_BIOMED_SUMMARY_FIELDS = (
    "study_question",
    "study_design",
    "participants",
    "intervention",
    "comparator",
    "primary_outcome",
    "main_findings",
    "limitations_bias",
    "clinical_relevance",
    "evidence_anchors",
)


def summarize_paper(project_root: Path | str, paper_id: int) -> dict:
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
        system_prompt_path = root / "configs" / "prompts" / "summary_biomed_v1.txt"
        user_prompt_path = root / "configs" / "prompts" / "summary_biomed_user_v1.txt"
        if not system_prompt_path.exists():
            system_prompt_path = root / settings.prompts.summary_system
            user_prompt_path = root / settings.prompts.summary_user
    else:
        system_prompt_path = root / settings.prompts.summary_system
        user_prompt_path = root / settings.prompts.summary_user

    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    system_prompt = system_prompt.replace("{research_context}", settings.llm.research_context)

    user_template = user_prompt_path.read_text(encoding="utf-8")
    sections_text = "\n\n".join(
        f"## {s['name']}\n{s['text']}" for s in paper.get("sections", [])
    )
    user_prompt = user_template.replace("{paper_title}", paper.get("title", ""))
    user_prompt = user_prompt.replace("{paper_abstract}", paper.get("abstract", ""))
    user_prompt = user_prompt.replace("{paper_sections}", sections_text)

    version = infer_prompt_version(system_prompt_path, user_prompt_path)

    input_hash = compute_summary_input_hash(
        parsed_path, system_prompt, user_prompt, settings.llm.summary_model, settings.llm.lang,
    )
    if _can_reuse_existing_summary(db_path, paper_id, input_hash):
        return _load_existing_summary(db_path, paper_id)

    started_at = datetime.now(timezone.utc).isoformat()

    raw = ""
    log_path = None
    try:
        raw = call_llm(
            api_key=settings.secrets.openai_api_key,
            base_url=settings.llm.base_url,
            model=settings.llm.summary_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=settings.llm.max_retries,
        )

        log_path = write_llm_log(root, "summary", paper_id, started_at, raw)
        summary = extract_json_object(raw)
        _validate_summary(summary)

        summary_json = json.dumps(summary, ensure_ascii=False)
        summary_md = _build_summary_md(paper.get("title", ""), summary)
        evidence_json = json.dumps(summary.get("evidence", []), ensure_ascii=False)

        ended_at = datetime.now(timezone.utc).isoformat()
        now = ended_at
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO summaries (paper_id, version, lang, model_name, summary_json, summary_md, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (paper_id, version, settings.llm.lang, settings.llm.summary_model, summary_json, summary_md, evidence_json, now),
            )
            conn.execute(
                "UPDATE papers SET summary_status = 'done', updated_at = ? WHERE id = ?",
                (now, paper_id),
            )
            conn.commit()

        record_task_run(
            db_path, "summary", "paper", str(paper_id), settings.llm.summary_model, "done",
            input_hash, started_at, ended_at, log_path,
        )

        return summary
    except Exception:
        ended_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE papers SET summary_status = 'failed', updated_at = ? WHERE id = ?",
                (ended_at, paper_id),
            )
            conn.commit()
        record_task_run(
            db_path, "summary", "paper", str(paper_id), settings.llm.summary_model, "failed",
            input_hash, started_at, ended_at, log_path,
        )
        raise


def _load_existing_summary(db_path: Path, paper_id: int) -> dict:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT summary_json FROM summaries WHERE paper_id = ? ORDER BY id DESC LIMIT 1",
            (paper_id,),
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"No existing summary for paper {paper_id}")
    return json.loads(row[0])


def _can_reuse_existing_summary(db_path: Path, paper_id: int, input_hash: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT summary_status FROM papers WHERE id = ?",
            (paper_id,),
        ).fetchone()

    if row is None:
        return False
    if row[0] in {"stale", "failed"}:
        return False
    return is_task_completed(db_path, "summary", str(paper_id), input_hash)


def select_papers_for_summary(db_path: Path | str) -> list[int]:
    db = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT id FROM papers WHERE summary_status IN ('pending', 'stale', 'failed') AND parse_status = 'done' ORDER BY id"
        ).fetchall()
    return [row[0] for row in rows]


def _validate_summary(data: dict) -> None:
    if any(f in data for f in REQUIRED_BIOMED_SUMMARY_FIELDS):
        required = REQUIRED_BIOMED_SUMMARY_FIELDS
    else:
        required = REQUIRED_SUMMARY_FIELDS
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Summary missing required fields: {', '.join(missing)}")


def _build_summary_md(title: str, summary: dict) -> str:
    if any(field in summary for field in REQUIRED_BIOMED_SUMMARY_FIELDS):
        lines = [f"# {title}", ""]
        for heading, key in [
            ("研究问题", "study_question"),
            ("研究设计", "study_design"),
            ("受试者", "participants"),
            ("干预措施", "intervention"),
            ("对照", "comparator"),
            ("主要终点", "primary_outcome"),
            ("主要发现", "main_findings"),
            ("局限与偏倚", "limitations_bias"),
            ("临床意义", "clinical_relevance"),
        ]:
            lines.append(f"## {heading}")
            lines.append(str(summary.get(key, "")))
            lines.append("")

        anchors = summary.get("evidence_anchors", [])
        if anchors:
            lines.append("## 证据锚点")
            for anchor in anchors:
                lines.append(f"- **{anchor.get('claim', '')}**: {anchor.get('quote', '')}")
            lines.append("")

        return "\n".join(lines)

    lines = [f"# {title}", ""]

    lines.append("## 核心问题")
    lines.append(summary.get("problem", ""))
    lines.append("")

    for heading, key in [
        ("主要贡献", "main_contributions"),
        ("核心创新", "core_innovations"),
    ]:
        lines.append(f"## {heading}")
        for item in summary.get(key, []):
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## 方法概述")
    lines.append(summary.get("method_summary", ""))
    lines.append("")

    lines.append("## 实验概述")
    lines.append(summary.get("experiment_summary", ""))
    lines.append("")

    for heading, key in [
        ("局限性", "limitations"),
        ("关键结论", "key_takeaways"),
    ]:
        lines.append(f"## {heading}")
        for item in summary.get(key, []):
            lines.append(f"- {item}")
    lines.append("")

    lines.append("## 与研究方向的关系")
    relation = summary.get("relation_to_user_research", "")
    if isinstance(relation, dict):
        relation_summary = relation.get("summary", "")
        if relation_summary:
            lines.append(str(relation_summary))
        applications = relation.get("applications", [])
        for item in applications:
            lines.append(f"- {item}")
    else:
        lines.append(str(relation))
    lines.append("")

    evidence = summary.get("evidence", [])
    if evidence:
        lines.append("## 证据")
        for e in evidence:
            lines.append(f"- **{e.get('claim', '')}**: {e.get('quote', '')}")
        lines.append("")

    return "\n".join(lines)
