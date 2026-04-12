from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from paperlab.parsing.pdf_utils import extract_doi, read_pdf_head_text


def pre_enrich_biomed_metadata(
    db_path: Path,
    paper_id: int,
    input_path: Path | str,
    ncbi_api_key: str = "",
) -> None:
    existing = _get_biomed_metadata(db_path, paper_id)
    if existing.get("pmid") or existing.get("pmcid"):
        return

    from paperlab.enrich import pubmed_client

    try:
        head_text = read_pdf_head_text(input_path, max_pages=2)
    except Exception:
        return
    doi = extract_doi(head_text)
    resolved = None
    try:
        if doi:
            resolved = pubmed_client.resolve_by_doi(doi, api_key=ncbi_api_key)
        if resolved is None:
            title_guess = _extract_title_guess(head_text)
            if title_guess:
                resolved = pubmed_client.resolve_by_title(title_guess, api_key=ncbi_api_key)
    except Exception:
        return

    if not resolved:
        return

    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE papers
            SET doi = COALESCE(doi, ?),
                pmid = COALESCE(pmid, ?),
                pmcid = COALESCE(pmcid, ?),
                journal = COALESCE(journal, ?),
                publication_type = COALESCE(publication_type, ?),
                mesh_terms = COALESCE(mesh_terms, ?),
                canonical_title = COALESCE(canonical_title, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (
                resolved.get("doi"),
                resolved.get("pmid"),
                resolved.get("pmcid"),
                resolved.get("journal"),
                resolved.get("publication_type"),
                json.dumps(resolved.get("mesh_terms"), ensure_ascii=False) if resolved.get("mesh_terms") else None,
                resolved.get("title"),
                now,
                paper_id,
            ),
        )
        connection.commit()


def _get_biomed_metadata(db_path: Path, paper_id: int) -> dict:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT pmid, pmcid, journal, mesh_terms, publication_type, doi, canonical_title FROM papers WHERE id = ?",
            (paper_id,),
        ).fetchone()
    if not row:
        return {}
    mesh_terms = json.loads(row[3]) if row[3] else None
    return {
        "pmid": row[0],
        "pmcid": row[1],
        "journal": row[2],
        "mesh_terms": mesh_terms,
        "publication_type": row[4],
        "doi": row[5],
        "title": row[6],
    }


def _extract_title_guess(head_text: str) -> str | None:
    for line in head_text.splitlines():
        text = line.strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered.startswith("https://") or lowered.startswith("http://"):
            continue
        if lowered.startswith("nature ") or lowered.startswith("article"):
            continue
        if len(text) < 12:
            continue
        return text
    return None
