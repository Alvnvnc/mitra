"""API smoke tests for the dashboard (demo provider, no network)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from mitra.config import get_settings

ADMIN = "test-admin-secret"


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


def test_demo_reset_reseeds_in_place(tmp_path, monkeypatch):
    """Reset must work when the data dir is a mount point (container volume)."""
    from mitra.demo_data import seed

    data = tmp_path / "data"
    seed(data)
    marker = data / "keepme.txt"
    marker.write_text("stale", encoding="utf-8")

    from mitra.web.app import create_app

    app = create_app(data)
    app.state.runtime.settings.mitra_demo_mode = True
    app.state.runtime.settings.mitra_admin_token = ADMIN
    client = TestClient(app)
    response = client.post("/api/demo/reset", json={}, headers={"x-mitra-admin": ADMIN})
    assert response.status_code == 200
    assert not marker.exists()
    body = response.json()
    assert len(body["commitments"]) == 4
    assert len(body["proposals"]) >= 1


def test_chat_still_works_after_demo_reset(tmp_path):
    """Every component must rebind to the new ledger, not a closed connection."""
    from mitra.demo_data import seed

    data = tmp_path / "data"
    seed(data)

    from mitra.web.app import create_app

    app = create_app(data)
    app.state.runtime.settings.mitra_demo_mode = True
    app.state.runtime.settings.mitra_admin_token = ADMIN
    client = TestClient(app)
    assert (
        client.post("/api/demo/reset", json={}, headers={"x-mitra-admin": ADMIN}).status_code == 200
    )

    session = client.post("/api/sessions", json={"title": "after reset"}).json()["session_id"]
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": session, "message": "Did yesterday's brief actually deliver?"},
    ) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert '"type": "final"' in text
    assert "closed database" not in text.lower()


# ------------------------------------------------------------ public hardening


def test_chat_rate_limit_is_per_client(client):
    """One visitor must not be able to hammer the endpoint that costs money."""
    guard = client.app.state.guard
    guard.chats_per_hour = 1
    guard.chats_per_day = 1
    guard.chat_cooldown_s = 0.0

    session = client.post("/api/sessions", json={"title": "limits"}).json()["session_id"]
    payload = {"session_id": session, "message": "hello"}
    assert client.post("/api/chat/stream", json=payload).status_code == 200

    blocked = client.post("/api/chat/stream", json=payload)
    assert blocked.status_code == 429
    assert blocked.json()["limited"] == "chat"
    assert blocked.headers["retry-after"]


def test_client_address_header_is_ignored_unless_trusted(client):
    """Spoofing CF-Connecting-IP must not mint a fresh allowance per request."""
    guard = client.app.state.guard
    guard.chats_per_hour = 1
    guard.chats_per_day = 1
    guard.chat_cooldown_s = 0.0

    session = client.post("/api/sessions", json={"title": "spoof"}).json()["session_id"]
    payload = {"session_id": session, "message": "hello"}
    assert (
        client.post(
            "/api/chat/stream", json=payload, headers={"cf-connecting-ip": "1.1.1.1"}
        ).status_code
        == 200
    )
    blocked = client.post("/api/chat/stream", json=payload, headers={"cf-connecting-ip": "2.2.2.2"})
    assert blocked.status_code == 429


def test_global_chat_ceiling_holds_across_clients(client):
    """A crowd with many addresses still meets one ceiling, not one each."""
    guard = client.app.state.guard
    guard.chats_per_hour = 5
    guard.chats_per_day = 5
    guard.global_chats_per_day = 1
    guard.chat_cooldown_s = 0.0

    session = client.post("/api/sessions", json={"title": "global"}).json()["session_id"]
    payload = {"session_id": session, "message": "hello"}
    assert client.post("/api/chat/stream", json=payload).status_code == 200
    for index in range(3):
        client.app.state.runtime.settings.mitra_trust_proxy = True
        blocked = client.post(
            "/api/chat/stream",
            json=payload,
            headers={"cf-connecting-ip": f"203.0.113.{index}"},
        )
        assert blocked.status_code == 429


def test_write_rate_limit_is_enforced(client):
    guard = client.app.state.guard
    guard.writes_per_minute = 1
    assert client.post("/api/sessions", json={"title": "one"}).status_code == 200
    blocked = client.post("/api/sessions", json={"title": "two"})
    assert blocked.status_code == 429
    assert blocked.json()["limited"] == "write"


def test_api_key_never_appears_in_a_response(client):
    """The key lives in the environment; no endpoint may echo it back."""
    secret = "sk-do-not-leak-0123456789abcdef"
    client.app.state.runtime.settings.nebius_api_key = secret

    paths = [
        "/api/health",
        "/api/bootstrap",
        "/api/audit?limit=20",
        "/api/sessions",
        "/api/export",
        "/api/docs",
        "/",
    ]
    for path in paths:
        response = client.get(path)
        assert secret not in response.text, path


def test_docs_are_off_by_default(client):
    assert client.get("/api/docs").status_code == 404


def test_budget_ceiling_applies_to_skill_calls():
    """`complete()` is used by scheduled skills; it must honour the same cap."""
    import pytest as _pytest

    from mitra.models.router import BudgetExceeded, ModelRouter

    class Spend:
        def usage_summary(self, days: int = 1) -> dict[str, float]:
            return {"cost_usd": 0.02}

    router = ModelRouter(
        api_key="test-key", provider="nebius", ledger=Spend(), daily_budget_usd=0.01
    )
    assert router.budget_exceeded()
    with _pytest.raises(BudgetExceeded):
        router.complete(purpose="reasoning", messages=[{"role": "user", "content": "hi"}])


def test_reset_requires_the_admin_token(tmp_path):
    """A visitor must not be able to reset the ledger.

    The daily spend counter is derived from the ledger, so an open reset would
    also re-open the inference budget.
    """
    from mitra.demo_data import seed

    data = tmp_path / "data"
    seed(data)

    from mitra.web.app import create_app

    app = create_app(data)
    app.state.runtime.settings.mitra_demo_mode = True
    app.state.runtime.settings.mitra_admin_token = ADMIN
    client = TestClient(app)

    assert client.post("/api/demo/reset", json={}).status_code == 403
    assert (
        client.post("/api/demo/reset", json={}, headers={"x-mitra-admin": "wrong"}).status_code
        == 403
    )
    assert (
        client.post("/api/demo/reset", json={}, headers={"x-mitra-admin": ADMIN}).status_code == 200
    )


def test_admin_secret_is_traded_for_a_cookie_and_scrubbed(tmp_path):
    from mitra.demo_data import seed

    data = tmp_path / "data"
    seed(data)

    from mitra.web.app import create_app

    app = create_app(data)
    app.state.runtime.settings.mitra_demo_mode = True
    app.state.runtime.settings.mitra_admin_token = ADMIN
    client = TestClient(app)

    response = client.get(f"/?admin={ADMIN}", follow_redirects=False)
    assert response.status_code == 303
    assert "admin" not in response.headers["location"]
    assert response.cookies.get("mitra_admin") == ADMIN

    # The cookie is Secure (the public site is HTTPS behind Cloudflare), so the
    # plain-HTTP test client has to present it explicitly, as a browser would.
    client.cookies.set("mitra_admin", ADMIN, domain="testserver.local")
    assert client.get("/api/bootstrap").json()["app"]["is_admin"] is True
    assert client.post("/api/demo/reset", json={}).status_code == 200


def test_code_assets_are_not_cached_blindly(client):
    """A CDN must revalidate the shell and its code, or the UI goes stale."""
    for path in ("/", "/static/js/app.js", "/static/css/app.css"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "no-cache", path
    fonts = client.get("/static/fonts/fonts-local.css")
    assert fonts.status_code == 200


def test_shell_references_versioned_assets(client):
    """A CDN must never be able to serve last deploy's JavaScript."""
    html = client.get("/").text
    assert "/static/js/app.js?v=" in html
    assert "/static/css/app.css?v=" in html
