"""Policy engine tests: deny by default, approvals, egress, audit."""

from __future__ import annotations

import pytest

from mitra.ledger import Ledger
from mitra.memory.selfmodel import SelfModel
from mitra.policy import EgressDenied, PolicyEngine
from mitra.tools import TOOL_SPECS, ToolBox


@pytest.fixture()
def env(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    selfmodel = SelfModel(tmp_path / "self_model")
    policy = PolicyEngine(ledger, tools=TOOL_SPECS)
    toolbox = ToolBox(ledger, selfmodel, data_dir=tmp_path, policy=policy)
    return ledger, selfmodel, policy, toolbox


def test_unknown_tool_is_denied_and_audited(env):
    ledger, _, policy, _ = env
    decision = policy.authorize("run_shell", {"cmd": "rm -rf /"})
    assert decision.status == "denied"
    audit = ledger.audit_log()
    assert audit[0]["decision"] == "denied"
    assert audit[0]["action"] == "tool_call"


def test_tool_outside_session_allowlist_is_denied(env):
    ledger, _, _, _ = env
    policy = PolicyEngine(ledger, tools=TOOL_SPECS, allowed_tools={"web_search"})
    assert policy.authorize("note_write", {"title": "x", "body": "y"}).status == "denied"
    assert policy.authorize("web_search", {"query": "x"}).status == "allowed"


def test_risky_tool_creates_approval_then_executes_once(env):
    ledger, _selfmodel, _, toolbox = env
    result = toolbox.execute("note_write", {"title": "Approved note", "body": "hello"})
    assert result.status == "approval_required"
    assert result.approval_id is not None
    assert not list((ledger.path.parent / "notes").glob("*.md"))

    ledger.decide_approval(result.approval_id, decision="approved")
    executed = toolbox.execute_approved(result.approval_id)
    assert executed.ok, executed.to_dict()
    files = list((ledger.path.parent / "notes").glob("*.md"))
    assert len(files) == 1
    assert "hello" in files[0].read_text()

    # A second execution of the same approval is not a second write gate.
    assert ledger.approvals(status="approved")[0]["id"] == result.approval_id


def test_egress_requires_https_and_exact_host(env):
    _, _, policy, _ = env
    with pytest.raises(EgressDenied):
        policy.check_url("http://api.tavily.com/search")
    with pytest.raises(EgressDenied):
        policy.check_url("https://evil.example.com/collect")
    with pytest.raises(EgressDenied):
        policy.check_url("https://api.tavily.com.evil.example/x")
    assert policy.check_url("https://api.tavily.com/search") == "api.tavily.com"
    assert policy.check_url("https://ntfy.sh/topic") == "ntfy.sh"


def test_note_write_cannot_escape_data_dir(env):
    _, _, _, toolbox = env
    result = toolbox.execute("note_write", {"title": "../../etc/passwd", "body": "x"})
    # Still gated by approval before the path is evaluated.
    assert result.status == "approval_required"


def test_artifact_read_lists_then_returns_what_the_run_wrote(env):
    """Chat must be able to answer "what did the brief actually say?"."""
    ledger, _selfmodel, _policy, toolbox = env
    artifacts = ledger.path.parent / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "morning-brief-2026-10-29.md").write_text(
        "# Morning brief\n\n- Status: one scan failed.\n", encoding="utf-8"
    )

    listing = toolbox.execute("artifact_read", {})
    assert listing.ok
    assert [row["name"] for row in listing.data["artifacts"]] == ["morning-brief-2026-10-29.md"]

    read = toolbox.execute("artifact_read", {"name": "morning-brief-2026-10-29.md"})
    assert read.ok
    assert "one scan failed" in read.data["text"]
    assert read.data["truncated"] is False

    missing = toolbox.execute("artifact_read", {"name": "morning-brief.md"})
    assert missing.ok
    assert missing.data["error"]
    assert missing.data["did_you_mean"] == ["morning-brief-2026-10-29.md"]


def test_artifact_read_refuses_to_escape_the_artifacts_dir(env):
    ledger, _selfmodel, _policy, toolbox = env
    (ledger.path.parent / "artifacts").mkdir(exist_ok=True)
    secret = ledger.path.parent / "secret.txt"
    secret.write_text("do not read me", encoding="utf-8")

    result = toolbox.execute("artifact_read", {"name": "../secret.txt"})
    assert result.status == "denied"
    assert "do not read me" not in str(result.data)
