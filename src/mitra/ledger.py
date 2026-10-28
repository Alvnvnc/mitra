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

# v2 additions (W3): sessions, model usage, audit, proposal inbox, approvals,
# notes. Every table is additive; migrations run through PRAGMA user_version.
OPERATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  created_at  REAL NOT NULL,
  updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS model_calls (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  at                 REAL NOT NULL,
  provider           TEXT NOT NULL DEFAULT 'nebius',
  model              TEXT NOT NULL,
  purpose            TEXT NOT NULL,
  latency_s          REAL NOT NULL DEFAULT 0,
  prompt_tokens      INTEGER NOT NULL DEFAULT 0,
  completion_tokens  INTEGER NOT NULL DEFAULT 0,
  cost_usd           REAL NOT NULL DEFAULT 0,
  session_id         TEXT,
  finish_reason      TEXT,
  detail             TEXT
);

CREATE TABLE IF NOT EXISTS audit (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  at        REAL NOT NULL,
  actor     TEXT NOT NULL DEFAULT 'mitra',
  action    TEXT NOT NULL,
  target    TEXT,
  decision  TEXT NOT NULL,           -- allowed | denied | approval_required | executed
  risk      TEXT NOT NULL DEFAULT 'low',
  detail    TEXT
);

CREATE TABLE IF NOT EXISTS proposals (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  at           REAL NOT NULL,
  kind         TEXT NOT NULL DEFAULT 'fact',   -- fact | preference | project | person | pattern
  page         TEXT NOT NULL,
  title        TEXT NOT NULL,
  body         TEXT NOT NULL,
  before       TEXT NOT NULL DEFAULT '',
  after        TEXT NOT NULL DEFAULT '',
  rationale    TEXT NOT NULL DEFAULT '',
  source_refs  TEXT NOT NULL DEFAULT '[]',
  status       TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
  decided_at   REAL
);

CREATE TABLE IF NOT EXISTS approvals (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          REAL NOT NULL,
  tool        TEXT NOT NULL,
  args        TEXT NOT NULL DEFAULT '{}',
  session_id  TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | denied
  decided_at  REAL,
  result      TEXT
);

CREATE TABLE IF NOT EXISTS notes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         REAL NOT NULL,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  path       TEXT,
  tags       TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_calls_at ON model_calls(at);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit(at);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
"""

# v1 additions (W2): conversation messages + full-text search over them.
MESSAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id        TEXT NOT NULL,
  role              TEXT NOT NULL,                 -- user | assistant | system
  content           TEXT NOT NULL,
  created_at        REAL NOT NULL,
  meta              TEXT                           -- JSON
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, message_id UNINDEXED);
"""


def _utcnow() -> float:
    return time.time()


def _to_epoch(dt: datetime | str | float | None) -> float:
    if dt is None:
        return _utcnow()
    if isinstance(dt, (int, float)):
        return float(dt)
    if isinstance(dt, str):
        text = dt.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid ISO-8601 timestamp {dt!r}") from exc
        aware = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return aware.timestamp()
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


@dataclass
class Message:
    id: int
    session_id: str
    role: str
    content: str
    created_at: float
    meta: dict[str, Any]


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


def _message(row: sqlite3.Row) -> Message:
    return Message(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        meta=json.loads(row["meta"] or "{}"),
    )


class Ledger:
    """Thin, explicit wrapper around one SQLite file. No ORM, on purpose."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One process, one connection. FastAPI runs sync endpoints in a worker
        # thread, so the connection must be shareable; SQLite is built in
        # serialized mode here and PRAGMA busy_timeout covers brief contention.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        """Schema migrations via PRAGMA user_version — idempotent and additive."""
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if version < 1:
            self._conn.executescript(MESSAGES_SCHEMA)
            self._conn.execute("PRAGMA user_version = 1")
            version = 1
        if version < 2:
            self._conn.executescript(OPERATIONS_SCHEMA)
            self._conn.execute("PRAGMA user_version = 2")

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
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                detail = json.loads(r["detail"]) if r["detail"] else None
            except (TypeError, ValueError):
                detail = r["detail"]
            out.append(
                {
                    "id": r["id"],
                    "at": iso(r["at"]),
                    "kind": r["kind"],
                    "commitment_id": r["commitment_id"],
                    "run_id": r["run_id"],
                    "detail": detail,
                }
            )
        return out

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
            "SELECT id FROM instruction_versions WHERE commitment_id = ? ORDER BY id DESC LIMIT 1",
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
                f"commitment {commitment_id!r} has no approved instruction effective at {iso(ts)}"
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
        self.log_event(
            "evidence_checked",
            detail={"evidence_id": evidence_id, "result": result, "detail": detail},
        )

    def evidence_for_run(self, run_id: str) -> list[EvidenceItem]:
        rows = self._conn.execute(
            "SELECT * FROM evidence WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [_evidence(r) for r in rows]

    # --------------------------------------------------------------- messages

    def log_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        meta: dict[str, Any] | None = None,
        at: datetime | float | None = None,
    ) -> int:
        """Capture one conversation message (ingestion hook for the memory core)."""
        cursor = self._conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at, meta)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                _to_epoch(at),
                json.dumps(meta, ensure_ascii=False) if meta else None,
            ),
        )
        message_id = int(cursor.lastrowid or 0)
        self._conn.execute(
            "INSERT INTO messages_fts (content, message_id) VALUES (?, ?)", (content, message_id)
        )
        self._conn.commit()
        return message_id

    def messages(
        self,
        session_id: str | None = None,
        *,
        limit: int = 100,
        since: datetime | float | None = None,
    ) -> list[Message]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(_to_epoch(since))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM messages {where} ORDER BY id DESC LIMIT ?", (*params, limit)
        ).fetchall()
        return [_message(r) for r in rows]

    def search_messages(self, query: str, *, limit: int = 10) -> list[Message]:
        """FTS5 phrase search (fallback: LIKE). Returns best matches first."""
        query = (query or "").strip()
        if not query:
            return []
        match = '"' + query.replace('"', '""') + '"'
        try:
            rows = self._conn.execute(
                "SELECT m.* FROM messages m JOIN messages_fts f ON f.message_id = m.id"
                " WHERE f MATCH ? ORDER BY bm25(f) LIMIT ?",
                (match, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [_message(r) for r in rows]

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

    # ------------------------------------------------------------------ runs (extra)

    def latest_run(self, commitment_id: str) -> TaskRun | None:
        row = self._conn.execute(
            "SELECT * FROM task_runs WHERE commitment_id = ? ORDER BY run_at DESC LIMIT 1",
            (commitment_id,),
        ).fetchone()
        return _run(row) if row else None

    def run_count_since(self, commitment_id: str, since: float) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM task_runs WHERE commitment_id = ? AND run_at >= ?",
            (commitment_id, since),
        ).fetchone()
        return int(row["n"])

    def run_stats_for(self, commitment_id: str, *, days: int = 28) -> dict[str, Any]:
        since = _utcnow() - days * 86400
        rows = self._conn.execute(
            "SELECT state, COUNT(*) AS n FROM task_runs"
            " WHERE commitment_id = ? AND run_at >= ? GROUP BY state",
            (commitment_id, since),
        ).fetchall()
        by_state = {r["state"]: int(r["n"]) for r in rows}
        total = sum(by_state.values())
        return {
            "days": days,
            "total": total,
            "by_state": by_state,
            "success_rate": (by_state.get("done", 0) / total) if total else None,
        }

    # ---------------------------------------------------------------- sessions

    def ensure_session(self, session_id: str, title: str = "New conversation") -> None:
        now = _utcnow()
        self._conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at",
            (session_id, title, now, now),
        )
        self._conn.commit()

    def touch_session(self, session_id: str, *, title: str | None = None) -> None:
        if title:
            self._conn.execute(
                "UPDATE sessions SET updated_at = ?, title = ? WHERE id = ?",
                (_utcnow(), title, session_id),
            )
        else:
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (_utcnow(), session_id)
            )
        self._conn.commit()

    def list_sessions(self, *, limit: int = 30) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS n"
            " FROM sessions s ORDER BY s.updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "created_at": iso(r["created_at"]),
                "updated_at": iso(r["updated_at"]),
                "messages": r["n"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------ model usage

    def record_model_call(
        self,
        *,
        provider: str,
        model: str,
        purpose: str,
        latency_s: float,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        session_id: str | None = None,
        finish_reason: str | None = None,
        detail: dict[str, Any] | None = None,
        at: float | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO model_calls (at, provider, model, purpose, latency_s, prompt_tokens,"
            " completion_tokens, cost_usd, session_id, finish_reason, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _utcnow() if at is None else float(at),
                provider,
                model,
                purpose,
                latency_s,
                prompt_tokens,
                completion_tokens,
                cost_usd,
                session_id,
                finish_reason,
                json.dumps(detail, ensure_ascii=False) if detail else None,
            ),
        )
        self._conn.commit()

    def usage_summary(self, *, days: int = 7) -> dict[str, Any]:
        since = _utcnow() - days * 86400
        totals = self._conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost,"
            " COALESCE(AVG(latency_s), 0) AS latency,"
            " COALESCE(SUM(prompt_tokens), 0) AS prompt,"
            " COALESCE(SUM(completion_tokens), 0) AS completion"
            " FROM model_calls WHERE at >= ?",
            (since,),
        ).fetchone()
        by_purpose = self._conn.execute(
            "SELECT purpose, COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost,"
            " COALESCE(AVG(latency_s), 0) AS latency FROM model_calls"
            " WHERE at >= ? GROUP BY purpose ORDER BY cost DESC",
            (since,),
        ).fetchall()
        by_model = self._conn.execute(
            "SELECT model, provider, COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost"
            " FROM model_calls WHERE at >= ? GROUP BY model, provider ORDER BY calls DESC",
            (since,),
        ).fetchall()
        by_day = self._conn.execute(
            "SELECT date(at, 'unixepoch') AS day, COUNT(*) AS calls,"
            " COALESCE(SUM(cost_usd), 0) AS cost FROM model_calls"
            " WHERE at >= ? GROUP BY day ORDER BY day",
            (since,),
        ).fetchall()
        return {
            "days": days,
            "calls": int(totals["calls"]),
            "cost_usd": float(totals["cost"]),
            "avg_latency_s": float(totals["latency"]),
            "prompt_tokens": int(totals["prompt"]),
            "completion_tokens": int(totals["completion"]),
            "by_purpose": [dict(r) for r in by_purpose],
            "by_model": [dict(r) for r in by_model],
            "by_day": [dict(r) for r in by_day],
        }

    def model_calls(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM model_calls ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "at": iso(r["at"]),
                "provider": r["provider"],
                "model": r["model"],
                "purpose": r["purpose"],
                "latency_s": r["latency_s"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "cost_usd": r["cost_usd"],
                "finish_reason": r["finish_reason"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ audit

    def record_audit(
        self,
        *,
        action: str,
        decision: str,
        target: str | None = None,
        risk: str = "low",
        actor: str = "mitra",
        detail: Any = None,
        at: datetime | str | float | None = None,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO audit (at, actor, action, target, decision, risk, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                _utcnow() if at is None else _to_epoch(at),
                actor,
                action,
                target,
                decision,
                risk,
                json.dumps(detail, ensure_ascii=False) if detail is not None else None,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def audit_log(self, *, limit: int = 60, decision: str | None = None) -> list[dict[str, Any]]:
        if decision:
            rows = self._conn.execute(
                "SELECT * FROM audit WHERE decision = ? ORDER BY id DESC LIMIT ?",
                (decision, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": r["id"],
                "at": iso(r["at"]),
                "actor": r["actor"],
                "action": r["action"],
                "target": r["target"],
                "decision": r["decision"],
                "risk": r["risk"],
                "detail": json.loads(r["detail"]) if r["detail"] else None,
            }
            for r in rows
        ]

    # -------------------------------------------------------------- proposals

    def add_proposal(
        self,
        *,
        kind: str,
        page: str,
        title: str,
        body: str,
        before: str = "",
        after: str = "",
        rationale: str = "",
        source_refs: list[Any] | None = None,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO proposals (at, kind, page, title, body, before, after, rationale,"
            " source_refs, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (
                _utcnow(),
                kind,
                page,
                title,
                body,
                before,
                after or body,
                rationale,
                json.dumps(source_refs or [], ensure_ascii=False),
            ),
        )
        self._conn.commit()
        proposal_id = int(cursor.lastrowid or 0)
        self.log_event("proposal_created", detail={"proposal_id": proposal_id, "page": page})
        return proposal_id

    def proposals(self, *, status: str | None = "pending", limit: int = 40) -> list[dict[str, Any]]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM proposals ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM proposals WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [self._proposal_row(r) for r in rows]

    def get_proposal(self, proposal_id: int) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"proposal {proposal_id} not found")
        return self._proposal_row(row)

    @staticmethod
    def _proposal_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "at": iso(row["at"]),
            "kind": row["kind"],
            "page": row["page"],
            "title": row["title"],
            "body": row["body"],
            "before": row["before"],
            "after": row["after"],
            "rationale": row["rationale"],
            "source_refs": json.loads(row["source_refs"] or "[]"),
            "status": row["status"],
            "decided_at": iso(row["decided_at"]) if row["decided_at"] else None,
        }

    def decide_proposal(self, proposal_id: int, *, decision: str) -> None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be 'approved' or 'rejected'")
        self._conn.execute(
            "UPDATE proposals SET status = ?, decided_at = ? WHERE id = ?",
            (decision, _utcnow(), proposal_id),
        )
        self._conn.commit()
        self.record_audit(
            action="memory_proposal",
            target=f"proposal:{proposal_id}",
            decision=decision,
            risk="medium",
            actor="user",
        )
        self.log_event(
            "proposal_decided", detail={"proposal_id": proposal_id, "decision": decision}
        )

    # -------------------------------------------------------------- approvals

    def add_approval(
        self, *, tool: str, args: dict[str, Any], session_id: str | None = None
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO approvals (at, tool, args, session_id, status) VALUES (?, ?, ?, ?, 'pending')",
            (_utcnow(), tool, json.dumps(args, ensure_ascii=False), session_id),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def approvals(self, *, status: str | None = "pending") -> list[dict[str, Any]]:
        if status is None:
            rows = self._conn.execute(
                "SELECT * FROM approvals ORDER BY id DESC LIMIT 50"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY id DESC LIMIT 50",
                (status,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "at": iso(r["at"]),
                "tool": r["tool"],
                "args": json.loads(r["args"] or "{}"),
                "session_id": r["session_id"],
                "status": r["status"],
                "decided_at": iso(r["decided_at"]) if r["decided_at"] else None,
                "result": json.loads(r["result"]) if r["result"] else None,
            }
            for r in rows
        ]

    def decide_approval(self, approval_id: int, *, decision: str) -> None:
        if decision not in {"approved", "denied"}:
            raise ValueError("decision must be 'approved' or 'denied'")
        self._conn.execute(
            "UPDATE approvals SET status = ?, decided_at = ? WHERE id = ?",
            (decision, _utcnow(), approval_id),
        )
        self._conn.commit()
        self.record_audit(
            action="tool_approval",
            target=f"approval:{approval_id}",
            decision=decision,
            risk="high",
            actor="user",
        )

    # ------------------------------------------------------------------ notes

    def add_note(
        self, *, title: str, body: str, path: str | None = None, tags: list[str] | None = None
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO notes (at, title, body, path, tags) VALUES (?, ?, ?, ?, ?)",
            (_utcnow(), title, body, path, json.dumps(tags or [], ensure_ascii=False)),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def notes(self, *, limit: int = 30) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "at": iso(r["at"]),
                "title": r["title"],
                "body": r["body"],
                "path": r["path"],
                "tags": json.loads(r["tags"] or "[]"),
            }
            for r in rows
        ]

    # --------------------------------------------------------------- counters

    def run_stats(self, *, days: int = 7) -> dict[str, Any]:
        since = _utcnow() - days * 86400
        rows = self._conn.execute(
            "SELECT state, COUNT(*) AS n FROM task_runs WHERE run_at >= ? GROUP BY state",
            (since,),
        ).fetchall()
        by_state = {r["state"]: int(r["n"]) for r in rows}
        total = sum(by_state.values())
        good = by_state.get("done", 0)
        return {
            "days": days,
            "total": total,
            "by_state": by_state,
            "success_rate": (good / total) if total else None,
            "failed": by_state.get("failed", 0),
            "delivery_failed": by_state.get("delivery_failed", 0),
        }

    def intervention_counts(self, *, since: float) -> dict[str, int]:
        """O4: how much the human had to step in (approvals, manual note edits)."""
        proposal = self._conn.execute(
            "SELECT COUNT(*) AS n FROM proposals WHERE decided_at IS NOT NULL AND decided_at >= ?",
            (since,),
        ).fetchone()
        approval = self._conn.execute(
            "SELECT COUNT(*) AS n FROM approvals WHERE decided_at IS NOT NULL AND decided_at >= ?",
            (since,),
        ).fetchone()
        manual_runs = self._conn.execute(
            "SELECT COUNT(*) AS n FROM audit WHERE action = 'manual_run' AND at >= ?",
            (since,),
        ).fetchone()
        return {
            "memory_decisions": int(proposal["n"]),
            "tool_approvals": int(approval["n"]),
            "manual_runs": int(manual_runs["n"]),
        }
