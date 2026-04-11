from __future__ import annotations

import requests

from paperlab.enrich.http import get_json

_BASE = "https://api.openalex.org"


def resolve_by_doi(doi: str, mailto: str = "") -> dict | None:
    params = {"mailto": mailto} if mailto else {}
    resp = get_json(f"{_BASE}/works/doi:{doi}", params=params, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _normalize(resp.json())


def resolve_by_title(title: str, mailto: str = "") -> dict | None:
    params = {"search": title, "per_page": 1}
    if mailto:
        params["mailto"] = mailto
    resp = get_json(f"{_BASE}/works", params=params, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    return _normalize(results[0])


def get_forward_citations(
    openalex_id: str,
    year_start: int,
    year_end: int,
    max_results: int,
    mailto: str = "",
) -> list[dict]:
    filt = f"cites:{openalex_id},from_publication_date:{year_start}-01-01,to_publication_date:{year_end}-12-31"
    params = {"filter": filt, "per_page": max_results}
    if mailto:
        params["mailto"] = mailto
    resp = get_json(f"{_BASE}/works", params=params, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [_normalize(r) for r in results]


def _normalize(work: dict) -> dict:
    return {
        "openalex_id": work.get("id"),
        "doi": work.get("doi"),
        "title": work.get("title"),
        "year": work.get("publication_year"),
        "is_oa": work.get("open_access", {}).get("is_oa", False),
        "oa_url": work.get("open_access", {}).get("oa_url"),
    }
