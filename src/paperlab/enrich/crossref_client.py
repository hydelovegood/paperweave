from __future__ import annotations

import requests

from paperlab.enrich.http import get_json

_BASE = "https://api.crossref.org/works"


def resolve_by_doi(doi: str, mailto: str = "") -> dict | None:
    headers = _headers(mailto)
    resp = get_json(f"{_BASE}/{doi}", headers=headers, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _normalize(resp.json().get("message", {}))


def resolve_by_title(title: str, mailto: str = "") -> dict | None:
    headers = _headers(mailto)
    resp = get_json(
        _BASE,
        params={"query.title": title, "rows": 1},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("message", {}).get("items", [])
    if not items:
        return None
    return _normalize(items[0])


def _headers(mailto: str) -> dict:
    if mailto:
        return {"User-Agent": f"PaperLab/0.1 (mailto:{mailto})"}
    return {}


def _normalize(item: dict) -> dict:
    titles = item.get("title", [])
    return {
        "doi": item.get("DOI"),
        "title": titles[0] if titles else None,
        "year": _extract_year(item),
    }


def _extract_year(item: dict) -> int | None:
    for key in ("published-print", "published-online", "created"):
        parts = item.get(key, {}).get("date-parts", [[None]])
        if parts and parts[0] and parts[0][0]:
            return parts[0][0]
    return None
