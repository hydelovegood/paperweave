from __future__ import annotations

import json
import re
from pathlib import Path
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

from paperlab.config import load_settings
from paperlab.enrich.biomed_pre_enrich import pre_enrich_biomed_metadata
from paperlab.parsing.canonical import CanonicalPaper
from paperlab.parsing.deepxiv_parser import (
    DeepXivRecoverableError,
    parse_arxiv_paper,
    search_arxiv_paper,
)
from paperlab.parsing.pdf_utils import extract_arxiv_id, extract_doi, read_pdf_text, read_pdf_head_text
from paperlab.parsing.pymupdf_parser import parse_pdf


def _get_pmcid(db_path: Path, paper_id: int) -> str | None:
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT pmcid FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return row[0] if row and row[0] else None


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


def _apply_biomed_metadata(canonical: CanonicalPaper, metadata: dict) -> CanonicalPaper:
    return replace(
        canonical,
        title=canonical.title or metadata.get("title") or "",
        doi=canonical.doi or metadata.get("doi"),
        pmid=canonical.pmid or metadata.get("pmid"),
        pmcid=canonical.pmcid or metadata.get("pmcid"),
        journal=canonical.journal or metadata.get("journal"),
        mesh_terms=canonical.mesh_terms or metadata.get("mesh_terms"),
        publication_type=canonical.publication_type or metadata.get("publication_type"),
    )


def _parse_with_pmc_fallback(
    pmcid: str | None,
    input_path: Path | str,
    deepxiv_token: str | None = None,
) -> CanonicalPaper:
    if pmcid:
        from paperlab.enrich.pmc_client import fetch_fulltext_xml, parse_jats_xml
        xml_text = fetch_fulltext_xml(pmcid)
        if xml_text:
            canonical = parse_jats_xml(xml_text)
            if canonical:
                return replace(canonical, pmcid=pmcid)

    return parse_document(
        input_path=input_path,
        deepxiv_token=deepxiv_token,
    )


def parse_document(
    input_path: Path | str,
    deepxiv_token: str | None = None,
) -> CanonicalPaper:
    candidate = str(input_path).strip()
    direct_id = _extract_direct_arxiv_id(candidate)
    if direct_id:
        return parse_arxiv_paper(direct_id, token=deepxiv_token)

    resolved_path = Path(candidate).expanduser()
    if resolved_path.suffix.lower() == ".pdf":
        resolved_path = resolved_path.resolve()
        text = read_pdf_head_text(resolved_path)
        arxiv_id = extract_arxiv_id(text)

        if arxiv_id:
            try:
                return parse_arxiv_paper(arxiv_id, token=deepxiv_token)
            except DeepXivRecoverableError:
                return parse_pdf(resolved_path)

        return parse_pdf(resolved_path)

    if not resolved_path.exists():
        arxiv_id = search_arxiv_paper(candidate, token=deepxiv_token)
        if arxiv_id is None:
            raise FileNotFoundError(f"No local file or DeepXiv search result for: {candidate}")
        return parse_arxiv_paper(arxiv_id, token=deepxiv_token)

    resolved_path = resolved_path.resolve()
    text = read_pdf_text(resolved_path)
    arxiv_id = extract_arxiv_id(text)

    if arxiv_id:
        try:
            return parse_arxiv_paper(arxiv_id, token=deepxiv_token)
        except DeepXivRecoverableError:
            return parse_pdf(resolved_path)

    return parse_pdf(resolved_path)


def _extract_direct_arxiv_id(value: str) -> str | None:
    direct_match = re.fullmatch(r"\d{4}\.\d{4,5}", value)
    return direct_match.group(0) if direct_match else None


def parse_and_persist(
    project_root: Path | str,
    paper_id: int,
    input_path: Path | str,
    deepxiv_token: str | None = None,
) -> CanonicalPaper:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root, require_prompts=False)
    db_path = (root / settings.database.path).resolve()
    pre_enrich_biomed_metadata(
        db_path=db_path,
        paper_id=paper_id,
        input_path=input_path,
        ncbi_api_key=settings.secrets.ncbi_api_key,
    )

    # Check if paper has PMCID (from prior resolve) -> prefer PMC full text
    pmcid = _get_pmcid(db_path, paper_id)
    canonical = _parse_with_pmc_fallback(
        pmcid=pmcid,
        input_path=input_path,
        deepxiv_token=deepxiv_token or settings.secrets.deepxiv_token,
    )
    canonical = _apply_biomed_metadata(canonical, _get_biomed_metadata(db_path, paper_id))

    parsed_dir = (root / settings.paths.parsed_dir).resolve()
    parsed_dir.mkdir(parents=True, exist_ok=True)
    parsed_json_path = parsed_dir / f"{paper_id}.json"
    parsed_json_path.write_text(
        json.dumps(canonical.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM sections WHERE paper_id = ?", (paper_id,))
        for section in canonical.sections:
            connection.execute(
                """
                INSERT INTO sections (paper_id, section_order, section_name, section_type, text_content, token_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    paper_id,
                    section.order,
                    section.name,
                    None,
                    section.text,
                    None,
                ),
            )

        connection.execute(
            """
            UPDATE papers
            SET canonical_title = ?,
                abstract = ?,
                arxiv_id = ?,
                year = ?,
                venue = ?,
                doi = ?,
                parse_quality = ?,
                pmid = ?,
                pmcid = ?,
                journal = ?,
                mesh_terms = ?,
                publication_type = ?,
                parse_status = 'done',
                updated_at = ?
            WHERE id = ?
            """,
            (
                canonical.title,
                canonical.abstract,
                canonical.arxiv_id,
                canonical.year,
                canonical.venue,
                canonical.doi,
                canonical.parse_quality,
                canonical.pmid,
                canonical.pmcid,
                canonical.journal,
                json.dumps(canonical.mesh_terms, ensure_ascii=False) if canonical.mesh_terms else None,
                canonical.publication_type,
                now,
                paper_id,
            ),
        )
        connection.commit()

    return canonical
