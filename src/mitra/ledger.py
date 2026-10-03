"""Commitment ledger: the state machine behind Mitra.

SQLite (WAL). The instance ledger lives in ``data/ledger.db``.

The ledger enforces three invariants that map 1:1 to the locked problem
(docs/PROBLEM_STATEMENT.md, O1-O3) and the architecture (docs/ARCHITECTURE.md §4):

1. O1 — instruction truth: a run always resolves the latest *approved*
   instruction version that is effective at run time; the version actually used
   is snapshotted on the run. Superseded (older) versions are never selected.
2. O2 — evidence gate: a run may only reach ``done`` when it has at least one
   piece of evidence and every recorded evidence item passed its check.
3. O3 — delivery is a separate state: ``done`` means "result produced with
   evidence", not "delivered". Failed delivery becomes ``delivery_failed`` and
   callers must surface it (fallback notice + event).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


class LedgerError(Exception):
    """Base class for ledger errors."""


class NoActiveInstructionError(LedgerError):
    """No approved instruction version is effective at the given time."""


class EvidenceGateError(LedgerError):
    """A completion claim was attempted without passed evidence (O2)."""


class NotFoundError(LedgerError):
    """Requested row does not exist."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS commitments (
  id                TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  schedule          TEXT NOT NULL,                 -- v1: daily "HH:MM" local time
  timezone          TEXT NOT NULL DEFAULT 'Asia/Jakarta',
  skill             TEXT NOT NULL,
  delivery_channel  TEXT NOT NULL DEFAULT 'telegram',
  state             TEXT NOT NULL DEFAULT 'active', -- active | paused | retired
  created_at        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS instruction_versions (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  commitment_id     TEXT NOT NULL REFERENCES commitments(id),
  content           TEXT NOT NULL,
  params            TEXT NOT NULL DEFAULT '{}',    -- JSON (max_words, since_hours, ...)
  effective_from    REAL NOT NULL,                 -- epoch seconds
  approved_by       TEXT NOT NULL DEFAULT 'user',
  approved_at       REAL NOT NULL,
  supersedes_id     INTEGER,
  state             TEXT NOT NULL DEFAULT 'approved' -- approved | proposed | retired
);

CREATE TABLE IF NOT EXISTS task_runs (
  id                      TEXT PRIMARY KEY,
  commitment_id           TEXT NOT NULL REFERENCES commitments(id),
  instruction_version_id  INTEGER NOT NULL,        -- snapshot of the version used (O1)
  run_at                  REAL NOT NULL,
  state                   TEXT NOT NULL,           -- queued | running | done | failed | delivery_failed
  error                   TEXT,
  evidence_id             INTEGER,
  delivered_at            REAL,
  delivery_receipt        TEXT                     -- JSON
);

CREATE TABLE IF NOT EXISTS evidence (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id            TEXT NOT NULL REFERENCES task_runs(id),
  kind              TEXT NOT NULL,                 -- facts | artifact | receipt
  path              TEXT,
  sha256            TEXT,
  summary           TEXT NOT NULL DEFAULT '',
  check_result      TEXT NOT NULL DEFAULT 'pending', -- pending | passed | failed
  check_detail      TEXT NOT NULL DEFAULT '',
  created_at        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  at                REAL NOT NULL,
  kind              TEXT NOT NULL,
  commitment_id     TEXT,
  run_id            TEXT,
  detail            TEXT
);

CREATE INDEX IF NOT EXISTS idx_iv_commitment ON instruction_versions(commitment_id);
CREATE INDEX IF NOT EXISTS idx_runs_commitment ON task_runs(commitment_id, run_at);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id);
"""


def _utcnow() -> float:
    return time.time()


def _to_epoch(dt: datetime | None) -> float:
    if dt is None:
        return _utcnow()
    aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return aware.timestamp()


def iso(ts: float | None) -> str:
    """Epoch -> ISO-8601 UTC string (display helper)."""
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


@dataclass
class Commitment:
    id: str
    title: str
    schedule: str
    timezone: str
    skill: str
    delivery_channel: str
    state: str
    created_at: float


@dataclass
class InstructionVersion:
    id: int
    commitment_id: str
    content: str
    params: dict[str, Any]
    effective_from: float
    approved_by: str
    approved_at: float
    supersedes_id: int | None
    state: str


@dataclass
class TaskRun:
    id: str
    commitment_id: str
    instruction_version_id: int
    run_at: float
    state: str
    error: str | None
    evidence_id: int | None
    delivered_at: float | None
    delivery_receipt: str | None


@dataclass
class EvidenceItem:
    id: int
    run_id: str
    kind: str
    path: str | None
    sha256: str | None
    summary: str
    check_result: str
    check_detail: str
    created_at: float


def _commitment(row: sqlite3.Row) -> Commitment:
    return Commitment(
        id=row["id"],
        title=row["title"],
        schedule=row["schedule"],
        timezone=row["timezone"],
        skill=row["skill"],
        delivery_channel=row["delivery_channel"],
        state=row["state"],
        created_at=row["created_at"],
    )


def _instruction(row: sqlite3.Row) -> InstructionVersion:
    return InstructionVersion(
        id=row["id"],
        commitment_id=row["commitment_id"],
        content=row["content"],
        params=json.loads(row["params"] or "{}"),
        effective_from=row["effective_from"],
        approved_by=row["approved_by"],
        approved_at=row["approved_at"],
        supersedes_id=row["supersedes_id"],
        state=row["state"],
    )


def _run(row: sqlite3.Row) -> TaskRun:
    return TaskRun(
        id=row["id"],
        commitment_id=row["commitment_id"],
        instruction_version_id=row["instruction_version_id"],
        run_at=row["run_at"],
        state=row["state"],
        error=row["error"],
        evidence_id=row["evidence_id"],
        delivered_at=row["delivered_at"],
        delivery_receipt=row["delivery_receipt"],
    )


def _evidence(row: sqlite3.Row) -> EvidenceItem:
    return EvidenceItem(
        id=row["id"],
        run_id=row["run_id"],
        kind=row["kind"],
        path=row["path"],
        sha256=row["sha256"],
        summary=row["summary"],
        check_result=row["check_result"],
        check_detail=row["check_detail"],
        created_at=row["created_at"],
    )


class Ledger:
    """Thin, explicit wrapper around one SQLite file. No ORM, on purpose."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ events

    def log_event(
        self,
        kind: str,
        *,
        commitment_id: str | None = None,
        run_id: str | None = None,
        detail: Any = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO events (at, kind, commitment_id, run_id, detail) VALUES (?, ?, ?, ?, ?)",
            (
                _utcnow(),
                kind,
                commitment_id,
                run_id,
                json.dumps(detail, ensure_ascii=False) if detail is not None else None,
            ),
        )
        self._conn.commit()

    def events(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "at": iso(r["at"]),
                "kind": r["kind"],
                "commitment_id": r["commitment_id"],
                "run_id": r["run_id"],
                "detail": r["detail"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------- commitments

    def add_commitment(
        self,
        *,
        title: str,
        skill: str,
        schedule: str,
        timezone_name: str = "Asia/Jakarta",
        delivery_channel: str = "telegram",
    ) -> str:
        commitment_id = f"cmt_{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            "INSERT INTO commitments (id, title, schedule, timezone, skill, delivery_channel,"
            " state, created_at) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (commitment_id, title, schedule, timezone_name, skill, delivery_channel, _utcnow()),
        )
        self._conn.commit()
        self.log_event("commitment_created", commitment_id=commitment_id, detail={"title": title})
        return commitment_id

    def get_commitment(self, commitment_id: str) -> Commitment:
        row = self._conn.execute(
            "SELECT * FROM commitments WHERE id = ?", (commitment_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"commitment {commitment_id!r} not found")
        return _commitment(row)

    def list_commitments(self, state: str | None = "active") -> list[Commitment]:
        if state is None:
            rows = self._conn.execute("SELECT * FROM commitments ORDER BY created_at").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM commitments WHERE state = ? ORDER BY created_at", (state,)
            ).fetchall()
        return [_commitment(r) for r in rows]

    # ------------------------------------------------------------- instructions

    def add_instruction_version(
        self,
        commitment_id: str,
        *,
        content: str,
        params: dict[str, Any] | None = None,
        effective_from: datetime | float | None = None,
        approved_by: str = "user",
        state: str = "approved",
    ) -> int:
        """Append a new instruction version.

        ``effective_from`` is when the wording takes effect ("mulai besok 08.00"
        is a future timestamp — until then the previous version stays active).
        """
        effective_ts = (
            effective_from
            if isinstance(effective_from, (int, float))
            else _to_epoch(effective_from)
        )
        previous = self._conn.execute(
            "SELECT id FROM instruction_versions WHERE commitment_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (commitment_id,),
        ).fetchone()
        cursor = self._conn.execute(
            "INSERT INTO instruction_versions (commitment_id, content, params, effective_from,"
            " approved_by, approved_at, supersedes_id, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                commitment_id,
                content,
                json.dumps(params or {}, ensure_ascii=False),
                effective_ts,
                approved_by,
                _utcnow(),
                previous["id"] if previous else None,
                state,
            ),
        )
        self._conn.commit()
        version_id = int(cursor.lastrowid or 0)
        self.log_event(
            "instruction_added",
            commitment_id=commitment_id,
            detail={
                "version_id": version_id,
                "effective_from": iso(effective_ts),
                "supersedes_id": previous["id"] if previous else None,
            },
        )
        return version_id

    def list_instruction_versions(self, commitment_id: str) -> list[InstructionVersion]:
        rows = self._conn.execute(
            "SELECT * FROM instruction_versions WHERE commitment_id = ? ORDER BY id",
            (commitment_id,),
        ).fetchall()
        return [_instruction(r) for r in rows]

    def resolve_instruction(
        self, commitment_id: str, *, at: datetime | float | None = None
    ) -> InstructionVersion:
        """O1: the latest approved version effective at ``at`` (default: now)."""
        ts = at if isinstance(at, (int, float)) else _to_epoch(at)
        row = self._conn.execute(
            "SELECT * FROM instruction_versions WHERE commitment_id = ? AND state = 'approved'"
            " AND effective_from <= ? ORDER BY effective_from DESC, id DESC LIMIT 1",
            (commitment_id, ts),
        ).fetchone()
        if row is None:
            raise NoActiveInstructionError(
                f"commitment {commitment_id!r} has no approved instruction effective"
                f" at {iso(ts)}"
            )
        return _instruction(row)

    # -------------------------------------------------------------------- runs

    def create_run(
        self,
        commitment_id: str,
        instruction_version_id: int,
        *,
        at: datetime | float | None = None,
    ) -> str:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            "INSERT INTO task_runs (id, commitment_id, instruction_version_id, run_at, state)"
            " VALUES (?, ?, ?, ?, 'queued')",
            (run_id, commitment_id, instruction_version_id, _to_epoch(at)),
        )
        self._conn.commit()
        self.log_event(
            "run_created",
            commitment_id=commitment_id,
            run_id=run_id,
            detail={"instruction_version_id": instruction_version_id},
        )
        return run_id

    def mark_run_running(self, run_id: str) -> None:
        self._conn.execute("UPDATE task_runs SET state = 'running' WHERE id = ?", (run_id,))
        self._conn.commit()
        self.log_event("run_running", run_id=run_id)

    def get_run(self, run_id: str) -> TaskRun:
        row = self._conn.execute("SELECT * FROM task_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"run {run_id!r} not found")
        return _run(row)

    def runs_for(self, commitment_id: str, *, limit: int = 10) -> list[TaskRun]:
        rows = self._conn.execute(
            "SELECT * FROM task_runs WHERE commitment_id = ? ORDER BY run_at DESC LIMIT ?",
            (commitment_id, limit),
        ).fetchall()
        return [_run(r) for r in rows]

    def complete_run(self, run_id: str) -> None:
        """O2 gate: refuse to claim "done" without passed evidence."""
        items = self.evidence_for_run(run_id)
        if not items:
            raise EvidenceGateError(f"run {run_id!r}: no evidence recorded — cannot claim done")
        not_passed = [e for e in items if e.check_result != "passed"]
        if not_passed:
            summary = ", ".join(f"#{e.id}:{e.kind}={e.check_result}" for e in not_passed)
            raise EvidenceGateError(
                f"run {run_id!r}: {len(not_passed)} evidence item(s) not passed ({summary})"
            )
        passed_ids = [e.id for e in items if e.check_result == "passed"]
        self._conn.execute(
            "UPDATE task_runs SET state = 'done', evidence_id = ? WHERE id = ?",
            (max(passed_ids), run_id),
        )
        self._conn.commit()
        self.log_event("completion_claimed", run_id=run_id, detail={"evidence_ids": passed_ids})

    def fail_run(self, run_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE task_runs SET state = 'failed', error = ? WHERE id = ?", (error, run_id)
        )
        self._conn.commit()
        self.log_event("run_failed", run_id=run_id, detail={"error": error})

    # ---------------------------------------------------------------- delivery

    def mark_delivery_failed(self, run_id: str, error: str) -> None:
        """O3: delivery failure is its own state, distinct from result production."""
        self._conn.execute(
            "UPDATE task_runs SET state = 'delivery_failed', error = ? WHERE id = ?",
            (error, run_id),
        )
        self._conn.commit()
        self.log_event("delivery_failed", run_id=run_id, detail={"error": error})

    def record_delivery(self, run_id: str, receipt: dict[str, Any]) -> None:
        self._conn.execute(
            "UPDATE task_runs SET state = 'done', delivered_at = ?, delivery_receipt = ?"
            " WHERE id = ?",
            (_utcnow(), json.dumps(receipt, ensure_ascii=False), run_id),
        )
        self._conn.commit()
        self.log_event("delivered", run_id=run_id, detail=receipt)

    # ---------------------------------------------------------------- evidence

    def record_evidence(
        self,
        run_id: str,
        *,
        kind: str,
        path: str | Path | None = None,
        summary: str = "",
        sha256: str | None = None,
    ) -> int:
        path_str = str(path) if path else None
        if sha256 is None and path_str:
            sha256 = _sha256_file(Path(path_str))
        cursor = self._conn.execute(
            "INSERT INTO evidence (run_id, kind, path, sha256, summary, check_result, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (run_id, kind, path_str, sha256, summary, _utcnow()),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def check_evidence(self, evidence_id: int, *, passed: bool, detail: str = "") -> None:
        result = "passed" if passed else "failed"
        self._conn.execute(
            "UPDATE evidence SET check_result = ?, check_detail = ? WHERE id = ?",
            (result, detail, evidence_id),
        )
        self._conn.commit()
        self.log_event("evidence_checked", detail={"evidence_id": evidence_id, "result": result,
                                                   "detail": detail})

    def evidence_for_run(self, run_id: str) -> list[EvidenceItem]:
        rows = self._conn.execute(
            "SELECT * FROM evidence WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [_evidence(r) for r in rows]

    # --------------------------------------------------------------- scheduling

    def due_commitments(self, *, now: datetime | None = None) -> list[Commitment]:
        """Active commitments whose daily time has passed and that have no run yet.

        v1 scope: one daily "HH:MM" schedule per commitment, evaluated in the
        commitment's timezone; a run started at/after today's due point counts
        as coverage for the day.
        """
        now_utc = now.astimezone(UTC) if now else datetime.now(UTC)
        due: list[Commitment] = []
        for commitment in self.list_commitments():
            try:
                hour, minute = (int(part) for part in commitment.schedule.split(":", 1))
                tz = ZoneInfo(commitment.timezone)
            except (ValueError, KeyError):
                continue
            local = now_utc.astimezone(tz)
            due_today = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if local < due_today:
                continue
            due_ts = due_today.timestamp()
            row = self._conn.execute(
                "SELECT MAX(run_at) AS last_run FROM task_runs WHERE commitment_id = ?",
                (commitment.id,),
            ).fetchone()
            if row["last_run"] is not None and row["last_run"] >= due_ts:
                continue
            due.append(commitment)
        return due