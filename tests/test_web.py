"""API smoke tests for the dashboard (demo provider, no network)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from mitra.config import get_settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MITRA_PROVIDER", "demo")
    monkeypatch.setenv("MITRA_DEMO_MODE", "1")
    monkeypatch.setenv("MITRA_ENABLE_SCHEDULER", "0")
    get_settings.cache_clear()
    from mitra.web.app import create_app

    app = create_app(tmp_path, start_scheduler=False)
    with TestClient(app) as test_client:
        yield test_client
    app.state.runtime.stop()
    get_settings.cache_clear()


def test_bootstrap_and_health(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["provider"] == "demo"
    boot = client.get("/api/bootstrap").json()
    for key in ("commitments", "proposals", "pages", "usage", "policy", "skills"):
        assert key in boot
    assert boot["router"]["provider"] == "demo"


def test_index_has_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Mitra" in response.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]


def test_create_run_and_evidence(client):
    created = client.post(
        "/api/commitments",
        json={
            "title": "Follow-up sweep",
            "schedule": "16:30",
            "skill": "commitment_followup",
            "instruction": "Check failed runs.",
            "params": {"max_words": 140},
            "delivery_channel": "outbox",
        },
    )
    assert created.status_code == 200, created.text
    commitment_id = created.json()["id"]

    run = client.post(f"/api/commitments/{commitment_id}/run", json={})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["outcome"]["state"] == "done"
    assert body["commitment"]["latest_run"]["evidence"]
    assert all(
        item["check_result"] == "passed" for item in body["commitment"]["latest_run"]["evidence"]
    )


def test_instruction_version_truth(client):
    created = client.post(
        "/api/commitments",
        json={
            "title": "Version test",
            "schedule": "07:00",
            "skill": "commitment_followup",
            "instruction": "v1 wording",
            "delivery_channel": "outbox",
        },
    ).json()
    cid = created["id"]
    # A future version must not displace the current one.
    response = client.post(
        f"/api/commitments/{cid}/instructions",
        json={
            "content": "v2 wording",
            "effective_from": "2999-01-01T00:00:00+00:00",
        },
    )
    assert response.status_code == 200
    detail = client.get(f"/api/commitments/{cid}").json()
    assert detail["active_version"]["content"] == "v1 wording"
    assert detail["upcoming_version"]["content"] == "v2 wording"


def test_memory_write_is_user_action(client):
    response = client.put("/api/memory/preferences.md", json={"body": "- A test preference.\n"})
    assert response.status_code == 200
    assert "test preference" in client.get("/api/memory/preferences.md").json()["body"]
    audit = client.get("/api/audit").json()["audit"]
    assert any(row["action"] == "memory_edit" for row in audit)


def test_chat_stream_returns_events(client):
    with client.stream(
        "POST", "/api/chat/stream", json={"message": "What needs a decision today?"}
    ) as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())
    assert "data: " in payload
    events = [json.loads(line[6:]) for line in payload.splitlines() if line.startswith("data: ")]
    assert any(event["type"] == "final" for event in events)
    assert any(event["type"] == "done" and event["provider"] == "demo" for event in events)


def test_unknown_memory_page_is_404(client):
    assert client.get("/api/memory/../../etc/passwd").status_code in {404, 400}
    assert client.put("/api/memory/secrets.md", json={"body": "x"}).status_code == 404
