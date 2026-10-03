"""Invariant tests for the commitment ledger and the run pipeline (no network).

Each test maps to one promise of the locked problem statement:

    O1  instruction versions        -> resolve latest effective; runs snapshot the version
    O2  evidence gate               -> "done" is impossible without passed evidence
    O3  delivery is a separate stage -> failure becomes delivery_failed + visible notice
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from mitra.delivery import DeliveryResult
from mitra.ledger import EvidenceGateError, Ledger, NoActiveInstructionError
from mitra.runner import run_commitment_once


def _ledger(tmp_path) -> Ledger:
    return Ledger(tmp_path / "ledger.db")


def _commitment(ledger: Ledger) -> str:
    return ledger.add_commitment(title="Ringkasan harian", skill="daily_digest", schedule="07:30")


def _approved(ledger: Ledger, commitment_id: str, *, content: str, effective_from) -> int:
    return ledger.add_instruction_version(
        commitment_id, content=content, effective_from=effective_from
    )


# --------------------------------------------------------------------- O1

def test_resolve_returns_latest_effective_version(tmp_path):
    ledger = _ledger(tmp_path)
    cid = _commitment(ledger)
    t0 = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
    v1 = _approved(ledger, cid, content="pukul 21.00", effective_from=t0)
    v2 = _approved(ledger, cid, content="pukul 07.30", effective_from=t0 + timedelta(days=1))

    assert ledger.resolve_instruction(cid, at=t0).id == v1
    at_next_day = t0 + timedelta(days=1, minutes=30)
    assert ledger.resolve_instruction(cid, at=at_next_day).id == v2


def test_run_snapshots_used_version(tmp_path):
    ledger = _ledger(tmp_path)
    cid = _commitment(ledger)
    t0 = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
    v1 = _approved(ledger, cid, content="v1", effective_from=t0)

    run_id = ledger.create_run(cid, v1, at=t0)
    assert ledger.get_run(run_id).instruction_version_id == v1


def test_no_active_instruction_blocks_resolution(tmp_path):
    ledger = _ledger(tmp_path)
    cid = _commitment(ledger)
    with pytest.raises(NoActiveInstructionError):
        ledger.resolve_instruction(cid, at=datetime.now(UTC))


# --------------------------------------------------------------------- O2

def test_completion_requires_passed_evidence(tmp_path):
    ledger = _ledger(tmp_path)
    cid = _commitment(ledger)
    t0 = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
    v1 = _approved(ledger, cid, content="v1", effective_from=t0)
    run_id = ledger.create_run(cid, v1, at=t0)

    with pytest.raises(EvidenceGateError):  # no evidence at all
        ledger.complete_run(run_id)

    ev_pending = ledger.record_evidence(run_id, kind="artifact", summary="belum diperiksa")
    with pytest.raises(EvidenceGateError):  # pending is not passed
        ledger.complete_run(run_id)

    ledger.check_evidence(ev_pending, passed=False, detail="kosong")
    with pytest.raises(EvidenceGateError):  # failed evidence poisons the run for good
        ledger.complete_run(run_id)
    assert ledger.get_run(run_id).state != "done"

    # The fix is a fresh run, never patching the failed one.
    run_2 = ledger.create_run(cid, v1, at=t0)
    ev_ok = ledger.record_evidence(run_2, kind="artifact", summary="isi ringkasan")
    ledger.check_evidence(ev_ok, passed=True, detail="OK")
    ledger.complete_run(run_2)
    assert ledger.get_run(run_2).state == "done"


# --------------------------------------------------------------------- O3

def test_delivery_is_separate_state(tmp_path):
    ledger = _ledger(tmp_path)
    cid = _commitment(ledger)
    t0 = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
    v1 = _approved(ledger, cid, content="v1", effective_from=t0)

    run_a = ledger.create_run(cid, v1, at=t0)
    ev = ledger.record_evidence(run_a, kind="artifact", summary="hasil")
    ledger.check_evidence(ev, passed=True, detail="OK")
    ledger.complete_run(run_a)
    ledger.mark_delivery_failed(run_a, "token kosong")
    assert ledger.get_run(run_a).state == "delivery_failed"

    run_b = ledger.create_run(cid, v1, at=t0)
    ev_b = ledger.record_evidence(run_b, kind="artifact", summary="hasil")
    ledger.check_evidence(ev_b, passed=True, detail="OK")
    ledger.complete_run(run_b)
    ledger.record_delivery(run_b, {"message_id": 7})
    stored = ledger.get_run(run_b)
    assert stored.state == "done"
    assert stored.delivered_at is not None
    assert json.loads(stored.delivery_receipt or "{}")["message_id"] == 7


def test_due_once_per_day(tmp_path):
    ledger = _ledger(tmp_path)
    cid = _commitment(ledger)  # jadwal 07:30 Asia/Jakarta
    wib = ZoneInfo("Asia/Jakarta")

    before = datetime(2026, 10, 4, 7, 0, tzinfo=wib)
    after = datetime(2026, 10, 4, 7, 31, tzinfo=wib)
    assert ledger.due_commitments(now=before) == []
    assert [c.id for c in ledger.due_commitments(now=after)] == [cid]

    v1 = _approved(ledger, cid, content="v1", effective_from=before)
    ledger.create_run(cid, v1, at=after)
    assert ledger.due_commitments(now=after) == []

    next_day = datetime(2026, 10, 5, 7, 31, tzinfo=wib)
    assert [c.id for c in ledger.due_commitments(now=next_day)] == [cid]


# --------------------------------------------------------- pipeline (offline)

class _FakeSkill:
    name = "fake"

    def execute(self, instruction, context):
        context.artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifact = context.artifacts_dir / "digest.md"
        artifact.write_text("- selesai\n- tertunda\n- prioritas\n", encoding="utf-8")
        facts = context.artifacts_dir / "facts.json"
        facts.write_text("{}", encoding="utf-8")
        return SimpleNamespace(
            summary_text="- selesai\n- tertunda\n- prioritas",
            artifact_path=artifact,
            facts_path=facts,
        )

    def verify(self, instruction, result):
        return True, "OK (fake)"


class _FailingSkill(_FakeSkill):
    def verify(self, instruction, result):
        return False, "hanya 0 baris bullet (<3)"


def _failing_sender(*, channel, text):
    return DeliveryResult(False, channel, error="token kosong (uji)")


def _passing_sender(*, channel, text):
    return DeliveryResult(True, "fake", receipt={"message_id": 42})


def _prepare_run(tmp_path):
    ledger = _ledger(tmp_path)
    cid = _commitment(ledger)
    now = datetime(2026, 10, 4, 7, 40, tzinfo=ZoneInfo("Asia/Jakarta"))
    _approved(ledger, cid, content="v1", effective_from=now)
    return ledger, cid, now


def test_runner_blocks_run_without_instruction(tmp_path):
    ledger = _ledger(tmp_path)
    cid = _commitment(ledger)
    outcome = run_commitment_once(
        ledger, cid, router=None, repo_root=tmp_path,
        outbox_dir=tmp_path / "outbox", skill_override=_FakeSkill(),
    )
    assert outcome.state == "blocked"
    assert outcome.run_id is None


def test_runner_delivery_failure_surfaces_notice(tmp_path):
    ledger, cid, now = _prepare_run(tmp_path)
    outcome = run_commitment_once(
        ledger, cid, router=None, repo_root=tmp_path, outbox_dir=tmp_path / "outbox",
        sender=_failing_sender, skill_override=_FakeSkill(), now=now,
    )
    assert outcome.state == "delivery_failed"
    run = ledger.get_run(outcome.run_id)
    assert run.state == "delivery_failed"
    assert run.delivery_receipt is None  # result produced, delivery failed
    assert outcome.notice_path is not None and outcome.notice_path.exists()
    kinds = [event["kind"] for event in ledger.events()]
    assert "completion_claimed" in kinds  # the result itself was verified
    assert "delivery_failed" in kinds
    assert "fallback_notice" in kinds


def test_runner_success_records_receipt(tmp_path):
    ledger, cid, now = _prepare_run(tmp_path)
    outcome = run_commitment_once(
        ledger, cid, router=None, repo_root=tmp_path, outbox_dir=tmp_path / "outbox",
        sender=_passing_sender, skill_override=_FakeSkill(), now=now,
    )
    assert outcome.state == "done"
    run = ledger.get_run(outcome.run_id)
    assert run.delivered_at is not None
    assert json.loads(run.delivery_receipt or "{}")["message_id"] == 42
    assert outcome.notice_path is None


def test_runner_rejects_failed_evidence(tmp_path):
    ledger, cid, now = _prepare_run(tmp_path)
    outcome = run_commitment_once(
        ledger, cid, router=None, repo_root=tmp_path, outbox_dir=tmp_path / "outbox",
        sender=_passing_sender, skill_override=_FailingSkill(), now=now,
    )
    assert outcome.state == "failed"
    run = ledger.get_run(outcome.run_id)
    assert run.state == "failed"
    assert "evidence check gagal" in (run.error or "")
    assert "completion_claimed" not in [event["kind"] for event in ledger.events()]
    assert outcome.notice_path is not None and outcome.notice_path.exists()