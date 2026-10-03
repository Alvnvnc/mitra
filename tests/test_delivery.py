"""Unit tests for the delivery lanes (no network)."""

from __future__ import annotations

from mitra import delivery
from mitra.delivery import send_ntfy


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


def test_send_ntfy_success(monkeypatch):
    captured: dict = {}

    def fake_post(url, *, content=None, headers=None, timeout=None):
        captured["url"] = url
        captured["content"] = content
        return _FakeResponse(200, {"id": "ID123", "topic": "topik-uji", "time": 111})

    monkeypatch.setattr(delivery.httpx, "post", fake_post)
    result = send_ntfy("halo dari uji", topic="topik-uji", base_url="https://ntfy.sh")

    assert result.ok is True
    assert result.lane == "ntfy"
    assert result.receipt is not None and result.receipt["id"] == "ID123"
    assert captured["url"] == "https://ntfy.sh/topik-uji"
    assert b"halo" in (captured["content"] or b"")


def test_send_ntfy_missing_topic_fails_clearly(monkeypatch):
    def fake_post(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("HTTP call must not happen without a topic")

    monkeypatch.setattr(delivery.httpx, "post", fake_post)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    result = send_ntfy("halo", topic="")

    assert result.ok is False
    assert "NTFY_TOPIC" in (result.error or "")


def test_send_ntfy_http_error_is_delivery_failure(monkeypatch):
    monkeypatch.setattr(delivery.httpx, "post", lambda *a, **k: _FakeResponse(500))
    result = send_ntfy("halo", topic="topik-uji")

    assert result.ok is False
    assert "500" in (result.error or "")