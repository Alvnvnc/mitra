"""Consolidation tests: propose, never auto-apply; approve writes, reject does not."""

from __future__ import annotations

from mitra.consolidation import decide_proposal, run_consolidation
from mitra.ledger import Ledger
from mitra.memory.selfmodel import SelfModel
from mitra.models.router import ModelRouter


def _env(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    selfmodel = SelfModel(tmp_path / "self_model")
    selfmodel.ensure_defaults()
    router = ModelRouter(provider="demo", ledger=ledger)
    return ledger, selfmodel, router


def test_consolidation_proposes_without_writing(tmp_path):
    ledger, selfmodel, router = _env(tmp_path)
    before = selfmodel.read("preferences.md").body
    ledger.log_message(
        "ses_1",
        "user",
        "Remember that I prefer Indonesian for personal notes, English for anything I publish.",
    )
    result = run_consolidation(ledger, selfmodel, router)
    assert result.created, result
    assert selfmodel.read("preferences.md").body == before
    proposals = ledger.proposals(status="pending")
    assert proposals[0]["page"] == "preferences.md"
    assert proposals[0]["source_refs"]


def test_approve_writes_and_reject_leaves_page(tmp_path):
    ledger, selfmodel, router = _env(tmp_path)
    ledger.log_message("ses_1", "user", "I prefer a three-bullet brief on weekdays.")
    run_consolidation(ledger, selfmodel, router)
    proposal = ledger.proposals(status="pending")[0]
    decide_proposal(ledger, selfmodel, proposal["id"], decision="rejected")
    assert "three-bullet" not in selfmodel.read("preferences.md").body
    assert ledger.get_proposal(proposal["id"])["status"] == "rejected"

    ledger.log_message("ses_2", "user", "Remember that I prefer quiet Sundays.")
    run_consolidation(ledger, selfmodel, router)
    second = next(p for p in ledger.proposals(status="pending") if "Sunday" in p["body"])
    decide_proposal(ledger, selfmodel, second["id"], decision="approved")
    assert "quiet Sundays" in selfmodel.read("preferences.md").body
    assert any(row["action"] == "memory_proposal" for row in ledger.audit_log())


def test_duplicate_proposals_are_skipped(tmp_path):
    ledger, selfmodel, router = _env(tmp_path)
    ledger.log_message("ses_1", "user", "I prefer evidence over reassurance.")
    first = run_consolidation(ledger, selfmodel, router)
    second = run_consolidation(ledger, selfmodel, router)
    assert first.created
    assert second.created == []
    assert len(ledger.proposals(status="pending")) == len(first.created)
