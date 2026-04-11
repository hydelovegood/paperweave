from __future__ import annotations

import requests

from paperlab.enrich.http import get_json

_BASE = "https://api.unpaywall.org/v2"


def check_oa(doi: str, email: str) -> dict | None:
    resp = get_json(f"{_BASE}/{doi}", params={"email": email}, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    best = data.get("best_oa_location") or {}
    return {
        "is_oa": data.get("is_oa", False),
        "oa_url": best.get("url_for_pdf") or best.get("url"),
        "landing_url": best.get("url_for_landing_page") or data.get("doi_url"),
    }
