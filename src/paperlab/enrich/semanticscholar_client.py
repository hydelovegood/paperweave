from __future__ import annotations

import requests

from paperlab.enrich.http import get_json

_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "externalIds,title,year,isOpenAccess,openAccessPdf"


def resolve_by_arxiv(arxiv_id: str, api_key: str = "") -> dict | None:
    return _resolve(f"ARXIV:{arxiv_id}", api_key)


def resolve_by_doi(doi: str, api_key: str = "") -> dict | None:
    return _resolve(f"DOI:{doi}", api_key)


def resolve_by_title(title: str, api_key: str = "") -> dict | None:
    headers = _headers(api_key)
    resp = get_json(
        f"{_BASE}/paper/search",
        params={"query": title, "limit": 1, "fields": _FIELDS},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        return None
    return _normalize(data[0])


def get_forward_citations(
    s2_id: str,
    year_start: int,
    year_end: int,
    max_results: int,
    api_key: str = "",
) -> list[dict]:
    headers = _headers(api_key)
    resp = get_json(
        f"{_BASE}/paper/{s2_id}/citations",
        params={"fields": "externalIds,title,year,isOpenAccess,openAccessPdf", "limit": max_results},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json().get("data", [])
    results = []
    for entry in raw:
        paper = entry.get("citingPaper")
        if not paper:
            continue
        year = paper.get("year")
        if year and year_start <= year <= year_end:
            results.append(_normalize(paper))
    return results


def _resolve(paper_id: str, api_key: str) -> dict | None:
    headers = _headers(api_key)
    resp = get_json(
        f"{_BASE}/paper/{paper_id}",
        params={"fields": _FIELDS},
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _normalize(resp.json())


def _headers(api_key: str) -> dict:
    return {"x-api-key": api_key} if api_key else {}


def _normalize(paper: dict) -> dict:
    ext = paper.get("externalIds", {})
    oa_pdf = paper.get("openAccessPdf") or {}
    return {
        "s2_id": paper.get("paperId"),
        "doi": ext.get("DOI"),
        "arxiv_id": ext.get("ArXiv"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "is_oa": paper.get("isOpenAccess", False),
        "oa_url": oa_pdf.get("url"),
    }
