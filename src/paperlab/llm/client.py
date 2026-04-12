from __future__ import annotations

import json
import re

_client_cache: dict[str, object] = {}


def _get_client(api_key: str, base_url: str, max_retries: int = 2):
    from openai import OpenAI

    cache_key = f"{api_key}:{base_url}:{max_retries}"
    client = _client_cache.get(cache_key)
    if client is None:
        client = OpenAI(api_key=api_key, base_url=base_url, max_retries=max_retries)
        _client_cache[cache_key] = client
    return client


def call_llm(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 2,
) -> str:
    if not api_key or not api_key.strip():
        raise ValueError("Missing OPENAI_API_KEY for LLM request")
    if not base_url or not base_url.strip():
        raise ValueError("Missing base_url for LLM request")
    if not model or not model.strip():
        raise ValueError("Missing model for LLM request")

    client = _get_client(api_key, base_url, max_retries)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    try:
        result = _safe_json_loads(stripped)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", stripped, re.DOTALL)
    if match:
        try:
            result = _safe_json_loads(match.group(1).strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    try:
        start = stripped.index("{")
        end = stripped.rindex("}") + 1
        return _safe_json_loads(stripped[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"LLM output is not valid JSON (object): {e}") from e


def extract_json_array(text: str) -> list:
    stripped = text.strip()
    try:
        result = _safe_json_loads(stripped)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", stripped, re.DOTALL)
    if match:
        try:
            result = _safe_json_loads(match.group(1).strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    try:
        start = stripped.index("[")
        end = stripped.rindex("]") + 1
        return _safe_json_loads(stripped[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"LLM output is not valid JSON (array): {e}") from e


def _safe_json_loads(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        sanitized = _escape_invalid_backslashes(text)
        return json.loads(sanitized)


def _escape_invalid_backslashes(text: str) -> str:
    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
