"""The commitment run pipeline: resolve -> execute -> evidence -> deliver.

This is the code that must hold the three promises from ``ledger.py``:

    O1  resolve the instruction version in force at run time (never a superseded one)
    O2  reach "done" only through the evidence gate
    O3  keep delivery state separate and surface failures (fallback notice)

Model output never decides whether a promise held — checks are deterministic
code taken from the instruction version that was in force.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mitra.config import REPO_ROOT
from mitra.delivery import deliver
from mitra.ledger import Ledger, NoActiveInstructionError
from mitra.skills import SkillContext, get_skill


@dataclass
class RunOutcome:
    run_id: str | None
    commitment_id: str
    instruction_version_id: int | None
    state: str  # blocked | failed | done | delivery_failed
    detail: str = ""
    notice_path: Path | None = None


def _write_notice(
    ledger: Ledger,
    outbox: Path,
    commitment_title: str,
    commitment_id: str,
    run_id: str,
    *,
    stage: str,
    error: str,
    artifact: Path | None = None,
) -> Path:
    """O3 fallback lane: a failure must leave a visible trace without being asked for."""
    outbox.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC)
    path = outbox / f"NOTICE-{ts:%Y%m%d-%H%M%S}-{run_id[-6:]}.md"
    lines = [
        "# Gangguan komitmen",
        "",
        f"- komitmen: {commitment_title} (`{commitment_id}`)",
        f"- run: `{run_id}`",
        f"- tahap: {stage}",
        f"- waktu: {ts.isoformat(timespec='seconds')}",
        f"- error: {error}",
    ]
    if artifact is not None:
        lines.append(f"- hasil (tetap tersimpan): `{artifact}`")
    lines += [
        "",
        "Aksi: periksa lalu jalankan ulang komitmen ini.",
        "Catatan: kegagalan pengiriman tidak membatalkan hasil yang sudah terverifikasi.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ledger.log_event(
        "fallback_notice",
        commitment_id=commitment_id,
        run_id=run_id,
        detail={"stage": stage, "notice": str(path)},
    )
    return path


def _delivery_text(result: object) -> str:
    return getattr(result, "summary_text", None) or str(result)


def run_commitment_once(
    ledger: Ledger,
    commitment_id: str,
    *,
    router: object | None = None,
    repo_root: str | Path | None = None,
    outbox_dir: str | Path | None = None,
    sender: object | None = None,
    skill_override: object | None = None,
    now: datetime | None = None,
) -> RunOutcome:
    commitment = ledger.get_commitment(commitment_id)

    # O1 — resolve the version in force. No version, no run.
    try:
        instruction = ledger.resolve_instruction(commitment_id, at=now)
    except NoActiveInstructionError as exc:
        ledger.log_event("run_blocked", commitment_id=commitment_id, detail=str(exc))
        return RunOutcome(None, commitment_id, None, "blocked", str(exc))

    run_id = ledger.create_run(commitment_id, instruction.id, at=now)
    ledger.mark_run_running(run_id)

    data_dir = ledger.path.parent
    outbox = Path(outbox_dir) if outbox_dir else data_dir / "outbox"
    skill = skill_override or get_skill(commitment.skill)
    context = SkillContext(
        router=router,
        repo_root=Path(repo_root) if repo_root else REPO_ROOT,
        artifacts_dir=data_dir / "artifacts",
    )

    # --- execute (process stage) -------------------------------------------
    try:
        result = skill.execute(instruction, context)
    except Exception as exc:  # noqa: BLE001 — any failure here is a process failure
        error = f"exec error: {type(exc).__name__}: {exc}"
        ledger.fail_run(run_id, error)
        notice = _write_notice(
            ledger, outbox, commitment.title, commitment_id, run_id,
            stage="process", error=error,
        )
        return RunOutcome(run_id, commitment_id, instruction.id, "failed", error, notice)

    # --- evidence + deterministic check (O2 gate) ---------------------------
    ev_facts = ledger.record_evidence(
        run_id,
        kind="facts",
        path=getattr(result, "facts_path", None),
        summary="fakta aktivitas (sumber ringkasan)",
    )
    ev_artifact = ledger.record_evidence(
        run_id,
        kind="artifact",
        path=getattr(result, "artifact_path", None),
        summary="hasil ringkasan",
    )
    passed, check_detail = skill.verify(instruction, result)
    for evidence_id in (ev_facts, ev_artifact):
        ledger.check_evidence(evidence_id, passed=passed, detail=check_detail)
    if not passed:
        error = f"evidence check gagal: {check_detail}"
        ledger.fail_run(run_id, error)
        notice = _write_notice(
            ledger, outbox, commitment.title, commitment_id, run_id,
            stage="evidence", error=error,
            artifact=getattr(result, "artifact_path", None),
        )
        return RunOutcome(run_id, commitment_id, instruction.id, "failed", error, notice)

    ledger.complete_run(run_id)  # raises if evidence gate is not satisfied

    # --- delivery (separate stage, O3) --------------------------------------
    delivery = deliver(commitment.delivery_channel, _delivery_text(result), sender=sender)
    if delivery.ok:
        ledger.record_delivery(run_id, delivery.receipt or {"lane": delivery.lane})
        return RunOutcome(
            run_id, commitment_id, instruction.id, "done",
            f"terkirim via {delivery.lane}: {delivery.receipt or {}}",
        )

    error = delivery.error or "delivery failed (unknown reason)"
    ledger.mark_delivery_failed(run_id, error)
    notice = _write_notice(
        ledger, outbox, commitment.title, commitment_id, run_id,
        stage="delivery", error=error,
        artifact=getattr(result, "artifact_path", None),
    )
    return RunOutcome(run_id, commitment_id, instruction.id, "delivery_failed", error, notice)