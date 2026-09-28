from __future__ import annotations

import hashlib
from pathlib import Path

from paperlab.utils.hashing import sha256_file


def compute_summary_input_hash(
    parsed_json_path: Path,
    system_prompt: Path | str,
    user_prompt: Path | str,
    model: str,
    lang: str = "",
) -> str:
    parts = [
        "summary",
        sha256_file(parsed_json_path),
        _hash_value(system_prompt),
        _hash_value(user_prompt),
        model,
        lang,
    ]
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


def compute_qa_input_hash(
    parsed_json_path: Path,
    system_prompt: Path | str,
    user_prompt: Path | str,
    model: str,
    lang: str = "",
) -> str:
    parts = [
        "qa",
        sha256_file(parsed_json_path),
        _hash_value(system_prompt),
        _hash_value(user_prompt),
        model,
        lang,
    ]
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


def compute_citations_input_hash(
    title: str | None,
    doi: str | None,
    arxiv_id: str | None,
    openalex_id: str | None,
    s2_paper_id: str | None,
    year_start: int,
    year_end: int,
    max_results: int,
) -> str:
    parts = [
        "citations",
        title or "",
        doi or "",
        arxiv_id or "",
        openalex_id or "",
        s2_paper_id or "",
        str(year_start),
        str(year_end),
        str(max_results),
    ]
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


def _hash_value(value: Path | str) -> str:
    if isinstance(value, Path):
        return sha256_file(value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
