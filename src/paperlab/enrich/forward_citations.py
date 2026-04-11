from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests

from paperlab.config import load_settings
from paperlab.enrich import crossref_client as crossref
from paperlab.enrich import openalex_client as openalex
from paperlab.enrich import pubmed_client as pubmed
from paperlab.enrich import semanticscholar_client as s2
from paperlab.enrich import unpaywall_client as unpaywall
from paperlab.storage.status import compute_citations_input_hash
from paperlab.storage.task_runs import record_task_run


def track_forward_citations(
    project_root: Path | str,
    paper_id: int,
    year_start: int | None = None,
    year_end: int | None = None,
    max_results: int | None = None,
) -> list[int]:
    root = Path(project_root).expanduser().resolve()
    settings = load_settings(root)
    db_path = (root / settings.database.path).resolve()

    y_start = year_start or settings.citations.default_year_start
    y_end = year_end or settings.citations.default_year_end
    max_r = max_results or settings.citations.default_max_results
    email = settings.secrets.unpaywall_email
    s2_key = settings.secrets.semantic_scholar_api_key
    ncbi_key = settings.secrets.ncbi_api_key

    paper = _get_paper(db_path, paper_id)
    input_hash = compute_citations_input_hash(
        paper.get("title"),
        paper.get("doi"),
        paper.get("arxiv_id"),
        paper.get("openalex_id"),
        paper.get("s2_paper_id"),
        y_start,
        y_end,
        max_r,
    )
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        # Resolve to external IDs
        resolved = _resolve(paper, email, s2_key, ncbi_key)
        if resolved:
            _update_paper_ids(db_path, paper_id, resolved)

        # Fetch forward citations
        citations = _fetch_citations(
            {**paper, **(resolved or {})},
            y_start, y_end, max_r, email, s2_key, ncbi_key,
        )

        # Persist citing papers, edges, links
        citing_ids: list[int] = []
        for citing in citations:
            source = citing.pop("_source", "unknown")
            citing_id = _upsert_paper_stub(db_path, citing)
            _create_citation_edge(db_path, citing_id, paper_id, source)
            _create_external_link(db_path, citing_id, citing, settings)
            citing_ids.append(citing_id)

        # Update statuses
        ended_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE papers SET enrich_status = 'done', citation_status = 'done', updated_at = ? WHERE id = ?",
                (ended_at, paper_id),
            )
            conn.commit()

        record_task_run(
            db_path, "citations", "paper", str(paper_id), "metadata-only", "done",
            input_hash, started_at, ended_at,
        )
        return citing_ids
    except Exception:
        ended_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE papers SET citation_status = 'failed', updated_at = ? WHERE id = ?",
                (ended_at, paper_id),
            )
            conn.commit()
        record_task_run(
            db_path, "citations", "paper", str(paper_id), "metadata-only", "failed",
            input_hash, started_at, ended_at,
        )
        raise


def select_papers_for_citations(db_path: Path | str) -> list[int]:
    db = Path(db_path).expanduser().resolve()
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT id FROM papers WHERE citation_status IN ('pending', 'stale') AND parse_status = 'done' ORDER BY id"
        ).fetchall()
    return [row[0] for row in rows]


def _get_paper(db_path: Path, paper_id: int) -> dict:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT canonical_title, doi, arxiv_id, openalex_id, s2_paper_id, pmid, pmcid FROM papers WHERE id = ?",
            (paper_id,),
        ).fetchone()
    if not row:
        raise FileNotFoundError(f"Paper {paper_id} not found")
    return {
        "title": row[0],
        "doi": row[1],
        "arxiv_id": row[2],
        "openalex_id": row[3],
        "s2_paper_id": row[4],
        "pmid": row[5],
        "pmcid": row[6],
    }


def _resolve(paper: dict, email: str, s2_key: str, ncbi_key: str = "") -> dict | None:
    result: dict = {}

    # PubMed: try DOI, then title (first for biomedical coverage)
    if paper.get("doi"):
        pm = _safe_resolve(lambda: pubmed.resolve_by_doi(paper["doi"], api_key=ncbi_key))
        if pm:
            result.update(pm)

    if paper.get("title") and not result.get("pmid"):
        pm = _safe_resolve(lambda: pubmed.resolve_by_title(paper["title"], api_key=ncbi_key))
        if pm:
            result.update(pm)

    # OpenAlex: try DOI, then title
    if paper.get("doi"):
        oa = _safe_resolve(lambda: openalex.resolve_by_doi(paper["doi"], mailto=email))
        if oa:
            result.update(oa)

    if paper.get("title") and not result.get("openalex_id"):
        oa = _safe_resolve(lambda: openalex.resolve_by_title(paper["title"], mailto=email))
        if oa:
            result.update(oa)

    # Semantic Scholar: try arXiv, DOI, then title
    if paper.get("arxiv_id") and not result.get("s2_id"):
        s2r = _safe_resolve(lambda: s2.resolve_by_arxiv(paper["arxiv_id"], api_key=s2_key))
        if s2r:
            result.update(s2r)

    if paper.get("doi") and not result.get("s2_id"):
        s2r = _safe_resolve(lambda: s2.resolve_by_doi(paper["doi"], api_key=s2_key))
        if s2r:
            result.update(s2r)

    if paper.get("title") and not result.get("s2_id"):
        s2r = _safe_resolve(lambda: s2.resolve_by_title(paper["title"], api_key=s2_key))
        if s2r:
            result.update(s2r)

    # Crossref: try DOI, then title
    if paper.get("doi") and not result.get("doi"):
        cr = _safe_resolve(lambda: crossref.resolve_by_doi(paper["doi"], mailto=email))
        if cr:
            result.update(cr)

    if paper.get("title") and not result.get("doi"):
        cr = _safe_resolve(lambda: crossref.resolve_by_title(paper["title"], mailto=email))
        if cr:
            result.update(cr)

    return result or None


def _fetch_citations(
    paper: dict,
    year_start: int,
    year_end: int,
    max_results: int,
    email: str,
    s2_key: str,
    ncbi_key: str = "",
) -> list[dict]:
    if paper.get("pmid"):
        try:
            citations = pubmed.get_forward_citations(
                paper["pmid"], year_start, year_end, max_results, api_key=ncbi_key,
            )
            if citations:
                for c in citations:
                    c["_source"] = "pubmed"
                return citations
        except Exception:
            pass

    if paper.get("openalex_id"):
        try:
            citations = openalex.get_forward_citations(
                paper["openalex_id"], year_start, year_end, max_results, mailto=email,
            )
            for c in citations:
                c["_source"] = "openalex"
            return citations
        except Exception:
            pass

    s2_identifier = paper.get("s2_id") or paper.get("s2_paper_id")
    if s2_identifier:
        try:
            citations = s2.get_forward_citations(
                s2_identifier, year_start, year_end, max_results, api_key=s2_key,
            )
            for c in citations:
                c["_source"] = "semanticscholar"
            return citations
        except Exception:
            pass

    return []


def _update_paper_ids(db_path: Path, paper_id: int, resolved: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    updates = {}
    if resolved.get("openalex_id"):
        updates["openalex_id"] = resolved["openalex_id"]
    if resolved.get("s2_id"):
        updates["s2_paper_id"] = resolved["s2_id"]
    normalized_doi = _normalize_doi(resolved.get("doi"))
    if normalized_doi and not _normalize_doi(_get_paper(db_path, paper_id).get("doi")):
        updates["doi"] = normalized_doi
    if resolved.get("pmid"):
        updates["pmid"] = resolved["pmid"]
    if resolved.get("pmcid"):
        updates["pmcid"] = resolved["pmcid"]
    if resolved.get("journal"):
        updates["journal"] = resolved["journal"]
    if resolved.get("publication_type"):
        updates["publication_type"] = resolved["publication_type"]
    if resolved.get("mesh_terms"):
        updates["mesh_terms"] = json.dumps(resolved["mesh_terms"], ensure_ascii=False)

    if not updates:
        return

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [now, paper_id]
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE papers SET {set_clause}, updated_at = ? WHERE id = ?",
            values,
        )
        conn.commit()


def _upsert_paper_stub(db_path: Path, citing: dict) -> int:
    now = datetime.now(timezone.utc).isoformat()
    doi = _normalize_doi(citing.get("doi"))
    title = citing.get("title") or ""

    with sqlite3.connect(db_path) as conn:
        if doi:
            existing = conn.execute(
                "SELECT id FROM papers WHERE doi = ?", (doi,)
            ).fetchone()
            if existing:
                return existing[0]

        cursor = conn.execute(
            """
            INSERT INTO papers (
                paper_uid, canonical_title, year, doi, arxiv_id, openalex_id, s2_paper_id,
                pmid, pmcid, publication_type, journal,
                parse_status, enrich_status, summary_status, qa_status, graph_status, citation_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'pending', 'pending', 'pending', 'pending', 'pending', ?, ?)
            """,
            (
                f"paper-{uuid4()}",
                title,
                citing.get("year"),
                doi,
                citing.get("arxiv_id"),
                citing.get("openalex_id"),
                citing.get("s2_id"),
                citing.get("pmid"),
                citing.get("pmcid"),
                citing.get("publication_type"),
                citing.get("journal"),
                now,
                now,
            ),
        )
        conn.commit()
    return cursor.lastrowid


def _create_citation_edge(db_path: Path, citing_id: int, cited_id: int, source: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO citation_edges (citing_paper_id, cited_paper_id, edge_source, edge_type, confidence, created_at)
            VALUES (?, ?, ?, 'cites', 1.0, ?)
            """,
            (citing_id, cited_id, source, now),
        )
        conn.commit()


def _create_external_link(db_path: Path, paper_id: int, citing: dict, settings) -> None:
    is_oa = citing.get("is_oa", False)
    oa_url = citing.get("oa_url")
    doi = _normalize_doi(citing.get("doi"))

    if settings.citations.download_oa_only and not is_oa and doi and settings.secrets.unpaywall_email:
        ua_result = unpaywall.check_oa(doi, settings.secrets.unpaywall_email)
        if ua_result and ua_result["is_oa"]:
            is_oa = True
            oa_url = oa_url or ua_result["oa_url"]

    url = oa_url if is_oa and oa_url else (f"https://doi.org/{doi}" if doi else oa_url)
    if not url:
        return

    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO external_links (paper_id, link_type, url, source, is_open_access, is_downloaded, checked_at)
            VALUES (?, ?, ?, 'citation_tracking', ?, 0, ?)
            """,
            (paper_id, "oa_pdf" if is_oa else "landing_page", url, int(is_oa), now),
        )
        conn.commit()


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    normalized = doi.strip()
    lowered = normalized.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix):]
            lowered = normalized.lower()
            break
    return normalized


def _safe_resolve(fn):
    try:
        return fn()
    except (requests.RequestException, RuntimeError):
        return None
