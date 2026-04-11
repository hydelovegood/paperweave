from __future__ import annotations

import time
from typing import Any

import requests


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 3,
    backoff_base: float = 0.5,
) -> requests.Response:
    last_response: requests.Response | None = None
    for attempt in range(retries):
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        last_response = response
        if response.status_code in {429, 500, 502, 503, 504} and attempt < retries - 1:
            time.sleep(backoff_base * (2**attempt))
            continue
        return response
    assert last_response is not None
    return last_response
