from __future__ import annotations

from paperlab.enrich.http import get_json


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_get_json_retries_on_429(monkeypatch):
    calls = []
    responses = [_FakeResponse(429), _FakeResponse(200)]

    monkeypatch.setattr("paperlab.enrich.http.time.sleep", lambda *_: None)

    def fake_get(*args, **kwargs):
        calls.append(1)
        return responses.pop(0)

    monkeypatch.setattr("paperlab.enrich.http.requests.get", fake_get)

    response = get_json("https://example.com")

    assert response.status_code == 200
    assert len(calls) == 2


def test_get_json_retries_on_5xx(monkeypatch):
    calls = []
    responses = [_FakeResponse(503), _FakeResponse(200)]

    monkeypatch.setattr("paperlab.enrich.http.time.sleep", lambda *_: None)

    def fake_get(*args, **kwargs):
        calls.append(1)
        return responses.pop(0)

    monkeypatch.setattr("paperlab.enrich.http.requests.get", fake_get)

    response = get_json("https://example.com")

    assert response.status_code == 200
    assert len(calls) == 2
