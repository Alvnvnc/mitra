"""Mitra web dashboard — FastAPI app + JSON API.

The dashboard is the judges' surface and the owner's control room:

    Today        what ran, what failed, what needs a decision
    Chat         persistent sessions, retrieved sources, tool trace
    Commitments  instruction versions, runs, evidence, delivery
    Memory       self-model pages + the approval inbox
    Skills       declarative registry + governed tools
    Audit        every tool decision, model call and intervention
    Stats        cost/latency by purpose, reliability, net-benefit counters

One process, one SQLite file, no external queue. That is the point: it is a
personal system the owner can read, copy and run.
"""

from __future__ import annotations

import hmac
import json
import queue
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from mitra import __version__
from mitra.agent import ChatAgent, state_summary
from mitra.config import REPO_ROOT, Settings, get_settings
from mitra.consolidation import decide_proposal, run_consolidation
from mitra.ledger import Ledger, NotFoundError, iso
from mitra.memory.selfmodel import DEFAULT_PAGES, SelfModel
from mitra.models.router import ModelRouter
from mitra.policy import EGRESS_ALLOWLIST
from mitra.runner import run_commitment_once
from mitra.scheduler import tick
from mitra.tools import TOOL_SPECS, ToolBox

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
ALLOWED_PAGES = set(DEFAULT_PAGES) | {"context.md"}


# --------------------------------------------------------------------- runtime


class Runtime:
    """One process, one ledger, one router. Everything the dashboard needs."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.settings: Settings = get_settings()
        self.data_dir = Path(data_dir) if data_dir else Path(self.settings.mitra_data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.data_dir / "ledger.db")
        self.selfmodel = SelfModel(self.data_dir / "self_model")
        created = self.selfmodel.ensure_defaults()
        self.router = ModelRouter(ledger=self.ledger)
        self.router.probe()
        self.toolbox = ToolBox(self.ledger, self.selfmodel, data_dir=self.data_dir)
        self.agent = ChatAgent(self.ledger, self.router, self.selfmodel, self.toolbox)
        self.started_at = time.time()
        self._stop = threading.Event()
        self._scheduler: threading.Thread | None = None
        self._started_pages = created

    # ------------------------------------------------------------------ reset

    def reset_demo(self) -> None:
        """Reseed the demo instance in place, leaving every live reference fresh.

        The ledger is closed and rebuilt, so every component that captured the
        old connection has to be rebuilt too — otherwise the next chat turn or
        tool call hits a closed database.
        """
        from mitra.demo_data import seed

        self.ledger.close()
        seed(self.data_dir, fresh=True)
        self.ledger = Ledger(self.data_dir / "ledger.db")
        self.selfmodel = SelfModel(self.data_dir / "self_model")
        self.selfmodel.ensure_defaults()
        self.router.ledger = self.ledger
        self.toolbox = ToolBox(self.ledger, self.selfmodel, data_dir=self.data_dir)
        self.agent = ChatAgent(self.ledger, self.router, self.selfmodel, self.toolbox)

    # ------------------------------------------------------------- scheduler

    def start_scheduler(self, interval_s: int = 60) -> None:
        if self._scheduler is not None:
            return

        def loop() -> None:
            while not self._stop.wait(interval_s):
                try:
                    for outcome in tick(
                        self.ledger,
                        router=self.router,
                        repo_root=REPO_ROOT,
                        outbox_dir=self.data_dir / "outbox",
                    ):
                        self.ledger.log_event(
                            "scheduled_run",
                            commitment_id=outcome.commitment_id,
                            run_id=outcome.run_id,
                            detail={"state": outcome.state, "detail": outcome.detail},
                        )
                except Exception as exc:  # noqa: BLE001 — keep the loop alive
                    self.ledger.log_event("scheduler_error", detail=f"{type(exc).__name__}: {exc}")

        self._scheduler = threading.Thread(target=loop, name="mitra-scheduler", daemon=True)
        self._scheduler.start()

    def stop(self) -> None:
        self._stop.set()
        self.ledger.close()

    # ---------------------------------------------------------------- payloads

    def run_payload(self, run: Any, *, evidence: bool = True) -> dict[str, Any] | None:
        if run is None:
            return None
        items = self.ledger.evidence_for_run(run.id) if evidence else []
        return {
            "id": run.id,
            "state": run.state,
            "at": iso(run.run_at),
            "at_local": _local(run.run_at),
            "instruction_version_id": run.instruction_version_id,
            "error": run.error,
            "delivered_at": iso(run.delivered_at) if run.delivered_at else None,
            "delivery_receipt": json.loads(run.delivery_receipt) if run.delivery_receipt else None,
            "evidence": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "summary": item.summary,
                    "check_result": item.check_result,
                    "check_detail": item.check_detail,
                    "path": item.path,
                    "sha256": item.sha256,
                    "created_at": iso(item.created_at),
                }
                for item in items
            ],
        }

    def commitment_payload(self, commitment: Any, *, full: bool = False) -> dict[str, Any]:
        versions = self.ledger.list_instruction_versions(commitment.id)
        now = time.time()
        active = None
        for version in versions:
            if version.state == "approved" and version.effective_from <= now:
                active = version
        upcoming = [
            version
            for version in versions
            if version.state == "approved" and version.effective_from > now
        ]
        latest = self.ledger.latest_run(commitment.id)
        runs = self.ledger.runs_for(commitment.id, limit=12 if full else 3)
        payload: dict[str, Any] = {
            "id": commitment.id,
            "title": commitment.title,
            "schedule": commitment.schedule,
            "timezone": commitment.timezone,
            "skill": commitment.skill,
            "delivery_channel": commitment.delivery_channel,
            "state": commitment.state,
            "created_at": iso(commitment.created_at),
            "version_count": len(versions),
            "active_version": {
                "id": active.id,
                "content": active.content,
                "params": active.params,
                "effective_from": iso(active.effective_from),
                "approved_by": active.approved_by,
            }
            if active
            else None,
            "upcoming_version": {
                "id": upcoming[0].id,
                "content": upcoming[0].content,
                "effective_from": iso(upcoming[0].effective_from),
            }
            if upcoming
            else None,
            "latest_run": self.run_payload(latest),
            "runs": [self.run_payload(run, evidence=False) for run in runs],
            "run_count_7d": self.ledger.run_count_since(commitment.id, now - 7 * 86400),
            "reliability": self.ledger.run_stats_for(commitment.id, days=28),
        }
        if full:
            payload["versions"] = [
                {
                    "id": version.id,
                    "content": version.content,
                    "params": version.params,
                    "effective_from": iso(version.effective_from),
                    "approved_by": version.approved_by,
                    "approved_at": iso(version.approved_at),
                    "supersedes_id": version.supersedes_id,
                    "state": version.state,
                    "is_future": version.effective_from > now,
                }
                for version in reversed(versions)
            ]
            payload["runs"] = [self.run_payload(run) for run in runs]
        return payload

    def bootstrap(self) -> dict[str, Any]:
        commitments = self.ledger.list_commitments(state=None)
        usage = self.ledger.usage_summary(days=7)
        today = self.ledger.usage_summary(days=1)
        stats = self.ledger.run_stats(days=7)
        since = time.time() - 7 * 86400
        interventions = self.ledger.intervention_counts(since=since)
        pages = []
        for name in self.selfmodel.pages():
            page = self.selfmodel.read(name)
            pages.append(
                {
                    "name": name,
                    "title": page.frontmatter.get("title", name),
                    "updated": page.frontmatter.get("updated"),
                    "excerpt": page.body.strip()[:180],
                    "chars": len(page.body),
                }
            )
        return {
            "app": {
                "name": "Mitra",
                "version": __version__,
                "now": datetime.now(UTC).isoformat(timespec="seconds"),
                "now_local": _local(time.time()),
                "timezone": self.settings.mitra_timezone,
                "demo_mode": bool(self.settings.mitra_demo_mode),
                "uptime_s": int(time.time() - self.started_at),
                "owner": self.selfmodel.read("people.md").frontmatter.get("owner", "there"),
            },
            "router": self.router.status(),
            "commitments": [self.commitment_payload(c) for c in commitments],
            "proposals": self.ledger.proposals(status="pending"),
            "approvals": self.ledger.approvals(status="pending"),
            "sessions": self.ledger.list_sessions(limit=20),
            "pages": pages,
            "audit": self.ledger.audit_log(limit=14),
            "events": self.ledger.events(limit=14),
            "usage": usage,
            "today": today,
            "stats": stats,
            "interventions": interventions,
            "notices": self.notices(),
            "notes": self.ledger.notes(limit=8),
            "skills": SKILLS,
            "tools": [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "risk": spec.risk,
                    "requires_approval": spec.requires_approval,
                    "egress": list(spec.egress),
                }
                for spec in TOOL_SPECS.values()
            ],
            "policy": {
                "egress_allowlist": sorted(EGRESS_ALLOWLIST),
                "tool_allowlist": sorted(self.toolbox.policy.allowed_tools),
            },
            "state_summary": state_summary(self.ledger, tz_name=self.settings.mitra_timezone),
            "tavily": bool((self.settings.tavily_api_key or "").strip()),
            "ntfy": bool((self.settings.ntfy_topic or "").strip()),
        }

    def notices(self) -> list[dict[str, Any]]:
        outbox = self.data_dir / "outbox"
        if not outbox.exists():
            return []
        items = []
        for path in sorted(outbox.glob("NOTICE-*.md"), reverse=True)[:8]:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fields: dict[str, str] = {}
            for line in text.splitlines():
                if line.startswith("- ") and ": " in line:
                    key, _, value = line[2:].partition(": ")
                    fields[key.strip()] = value.strip()
            items.append(
                {
                    "name": path.name,
                    "at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(
                        timespec="seconds"
                    ),
                    "body": text[:1200],
                    "commitment": fields.get("komitmen") or fields.get("commitment"),
                    "stage": fields.get("tahap") or fields.get("stage"),
                    "error": fields.get("error"),
                }
            )
        return items


SKILLS: list[dict[str, Any]] = [
    {
        "name": "daily_digest",
        "title": "Daily digest",
        "description": (
            "Scans a repo deterministically, summarizes the facts with Nemotron, then "
            "checks word count and bullet shape before claiming done."
        ),
        "tools": ["git (local)"],
        "checks": ["artifact exists", "≤ max_words", "≥ 3 bullets"],
        "status": "stable",
    },
    {
        "name": "morning_brief",
        "title": "Morning brief",
        "description": (
            "Combines the commitment ledger's real status with the daily digest. Never "
            "claims success without evidence; lists what needs a decision."
        ),
        "tools": ["ledger", "git (local)"],
        "checks": ["artifact exists", "status section present", "≥ 3 bullets"],
        "status": "stable",
    },
    {
        "name": "commitment_followup",
        "title": "Commitment follow-up",
        "description": (
            "Deterministic sweep for failed and undelivered runs. Produces a short report "
            "with the exact run ids, so nothing depends on a model noticing a failure."
        ),
        "tools": ["ledger"],
        "checks": ["report exists", "every listed run id resolves", "counts match ledger"],
        "status": "stable",
    },
    {
        "name": "research_digest",
        "title": "Research digest",
        "description": (
            "Calls Tavily through the policy-checked tool layer, summarizes with Nemotron, "
            "and refuses to claim a finding without at least two sources."
        ),
        "tools": ["web_search (Tavily)"],
        "checks": ["artifact exists", "≥ 2 sources", "URLs present"],
        "status": "beta",
    },
]


def _local(ts: float) -> str:
    settings = get_settings()
    return (
        datetime.fromtimestamp(ts, tz=UTC)
        .astimezone(ZoneInfo(settings.mitra_timezone))
        .isoformat(timespec="minutes")
    )


def _env_flag(name: str, *, default: bool = False) -> bool:
    import os

    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ------------------------------------------------------------------- security


class DemoGuard:
    """Layered in-memory limiter for a public demo that spends a real API key.

    Three layers, because each one alone is easy to defeat:

    * per-client cooldown — stops a loop hammering chat from one address;
    * per-client windows — one visitor cannot consume the whole allowance;
    * global windows — a crowd, or a botnet cycling through addresses, still
      meets a ceiling that does not depend on how many identities it can mint.

    Single-process and in-memory by design: this is a demo, not a billing
    system. The hard money ceiling is ``MITRA_DAILY_BUDGET_USD`` in the router;
    these limits exist so the budget is spent on visitors rather than on one
    script.
    """

    def __init__(
        self,
        *,
        chats_per_hour: int = 8,
        chats_per_day: int = 30,
        global_chats_per_day: int = 60,
        chat_cooldown_s: float = 4.0,
        writes_per_minute: int = 20,
        global_writes_per_minute: int = 60,
    ) -> None:
        self.chats_per_hour = chats_per_hour
        self.chats_per_day = chats_per_day
        self.global_chats_per_day = global_chats_per_day
        self.chat_cooldown_s = chat_cooldown_s
        self.writes_per_minute = writes_per_minute
        self.global_writes_per_minute = global_writes_per_minute
        self._chats: dict[str, list[float]] = defaultdict(list)
        self._writes: dict[str, list[float]] = defaultdict(list)
        self._global_chats: list[float] = []
        self._global_writes: list[float] = []
        self._last_chat: dict[str, float] = {}

    @staticmethod
    def _trim(bucket: list[float], now: float, window: float) -> None:
        cutoff = now - window
        bucket[:] = [stamp for stamp in bucket if stamp > cutoff]

    def retry_after(self, key: str, kind: str) -> float:
        """Seconds until this client is allowed again (0 when allowed now)."""
        now = time.time()
        if kind != "chat":
            return 0.0
        last = self._last_chat.get(key)
        if last is None:
            return 0.0
        return max(0.0, self.chat_cooldown_s - (now - last))

    def allow(self, key: str, kind: str) -> bool:
        now = time.time()
        if kind == "chat":
            self._trim(self._global_chats, now, 86400)
            if len(self._global_chats) >= self.global_chats_per_day:
                return False
            last = self._last_chat.get(key)
            if last is not None and now - last < self.chat_cooldown_s:
                return False
            bucket = self._chats[key]
            self._trim(bucket, now, 86400)
            if len(bucket) >= self.chats_per_day:
                return False
            self._trim(bucket, now, 3600)
            if len(bucket) >= self.chats_per_hour:
                return False
            bucket.append(now)
            self._last_chat[key] = now
            self._global_chats.append(now)
            return True

        self._trim(self._global_writes, now, 60)
        if len(self._global_writes) >= self.global_writes_per_minute:
            return False
        bucket = self._writes[key]
        self._trim(bucket, now, 60)
        if len(bucket) >= self.writes_per_minute:
            return False
        bucket.append(now)
        self._global_writes.append(now)
        return True


# ------------------------------------------------------------------ app factory


def create_app(
    data_dir: str | Path | None = None, *, start_scheduler: bool | None = None
) -> FastAPI:
    runtime = Runtime(data_dir)
    settings = runtime.settings
    guard = DemoGuard(
        chats_per_hour=settings.mitra_chat_per_hour,
        chats_per_day=settings.mitra_chat_per_day,
        global_chats_per_day=settings.mitra_global_chats_per_day,
        chat_cooldown_s=settings.mitra_chat_cooldown_s,
        writes_per_minute=settings.mitra_writes_per_minute,
        global_writes_per_minute=settings.mitra_global_writes_per_minute,
    )
    docs_url = "/api/docs" if settings.mitra_enable_docs else None

    app = FastAPI(title="Mitra", version=__version__, docs_url=docs_url, redoc_url=None)
    app.state.runtime = runtime
    app.state.guard = guard

    if start_scheduler is None:
        start_scheduler = _env_flag("MITRA_ENABLE_SCHEDULER", default=False)
    if start_scheduler:
        runtime.start_scheduler()

    # ------------------------------------------------------------- middleware

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # ?admin=<secret> trades the secret in the URL for an HttpOnly cookie and
        # immediately redirects, so it never ends up in a bookmark or referrer.
        admin_token = (runtime.settings.mitra_admin_token or "").strip()
        if admin_token and request.query_params.get("admin") is not None:
            supplied = (request.query_params.get("admin") or "").strip()
            if hmac.compare_digest(supplied, admin_token):
                clean = request.url.path
                rest = {k: v for k, v in request.query_params.items() if k != "admin"}
                if rest:
                    clean += "?" + urlencode(rest)
                response = RedirectResponse(clean, status_code=303)
                response.set_cookie(
                    "mitra_admin",
                    admin_token,
                    httponly=True,
                    samesite="strict",
                    secure=True,
                    max_age=7 * 86400,
                )
                return response

        token = (runtime.settings.mitra_dashboard_token or "").strip()
        if token:
            supplied = (
                request.cookies.get("mitra_token")
                or request.headers.get("x-mitra-token")
                or request.query_params.get("token")
            )
            if supplied != token and request.url.path not in {"/healthz", "/api/health"}:
                if request.method == "GET" and request.url.path == "/":
                    return JSONResponse(
                        {"error": "access token required", "hint": "append ?token=…"},
                        status_code=401,
                    )
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            if request.query_params.get("token") == token:
                response = await call_next(request)
                response.set_cookie(
                    "mitra_token", token, httponly=True, samesite="strict", max_age=86400
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=()")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif request.url.path == "/" or request.url.path.startswith(
            ("/static/js/", "/static/css/")
        ):
            # The shell and its code must revalidate on every load. A CDN that
            # caches them per content-encoding will happily serve last deploy's
            # JavaScript otherwise, and the UI silently stops matching the API.
            response.headers["Cache-Control"] = "no-cache"
        elif request.url.path.startswith("/static/fonts/"):
            # Fonts are content-addressed by name and never change.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        # Cloudflare injects its RUM beacon into proxied HTML. It is the one
        # third-party script allowed; drop this host if you disable RUM in the
        # Cloudflare dashboard. Everything else stays first-party.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://static.cloudflareinsights.com; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
            "connect-src 'self' https://cloudflareinsights.com; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'",
        )
        return response

    def is_admin(request: Request) -> bool:
        """Does this request carry the admin secret?

        Admin rights are granted by a cookie (set when the page is opened with
        ``?admin=…``) or by the ``x-mitra-admin`` header, so the secret never
        sits in a bookmarked URL.
        """
        token = (runtime.settings.mitra_admin_token or "").strip()
        if not token:
            return False
        supplied = request.cookies.get("mitra_admin") or request.headers.get("x-mitra-admin") or ""
        return hmac.compare_digest(supplied.strip(), token)

    def client_ip(request: Request) -> str:
        """The address to meter.

        Behind Cloudflare the socket peer is the tunnel, so every visitor would
        share one bucket. CF-Connecting-IP is only believed when the operator
        declares the port is loopback-bound (``MITRA_TRUST_PROXY=1``); with a
        public port the header is attacker-controlled and must be ignored.
        """
        if runtime.settings.mitra_trust_proxy:
            forwarded = (request.headers.get("cf-connecting-ip") or "").strip()
            if forwarded:
                return forwarded
        return request.client.host if request.client else "anonymous"

    @app.middleware("http")
    async def limit_middleware(request: Request, call_next):
        if request.method == "POST":
            length = int(request.headers.get("content-length") or 0)
            if length > 200_000:
                return JSONResponse({"error": "payload too large"}, status_code=413)
            key = client_ip(request)
            kind = "chat" if request.url.path == "/api/chat/stream" else "write"
            if not guard.allow(key, kind):
                wait = guard.retry_after(key, kind)
                if kind == "chat":
                    detail = (
                        "This shared demo limits chat turns so the API key cannot be "
                        "spent by one visitor. Try again in a few seconds, or use the "
                        "seeded conversations and the rest of the dashboard."
                    )
                else:
                    detail = "Too many actions from this address — wait a minute and retry."
                return JSONResponse(
                    {
                        "error": detail,
                        "retry_after_s": round(wait, 1),
                        "limited": kind,
                    },
                    status_code=429,
                    headers={"Retry-After": str(max(1, int(wait)))},
                )
        return await call_next(request)

    # ----------------------------------------------------------------- routes

    def asset_version(rel: str) -> str:
        """Cache-buster from the file itself, so a deploy cannot be masked by a CDN.

        Cloudflare caches per content-encoding, and a stale brotli variant of
        app.js once shipped an old UI against a new API. The query string is
        derived from mtime+size, so the URL changes exactly when the file does.
        """
        try:
            stat = (STATIC_DIR / rel).stat()
        except OSError:  # pragma: no cover - file is part of the image
            return "0"
        return f"{int(stat.st_mtime)}-{stat.st_size}"

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        for rel in ("css/app.css", "js/app.js"):
            html = html.replace(
                f"/static/{rel}",
                f"/static/{rel}?v={asset_version(rel)}",
            )
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "version": __version__,
            "provider": runtime.router.provider,
            "uptime_s": int(time.time() - runtime.started_at),
        }

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/api/bootstrap")
    def bootstrap(request: Request) -> dict[str, Any]:
        payload = runtime.bootstrap()
        payload["app"]["is_admin"] = is_admin(request)
        return payload

    @app.get("/api/commitments/{commitment_id}")
    def commitment_detail(commitment_id: str) -> dict[str, Any]:
        try:
            commitment = runtime.ledger.get_commitment(commitment_id)
        except NotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return runtime.commitment_payload(commitment, full=True)

    @app.get("/api/sessions/{session_id}/messages")
    def session_messages(session_id: str) -> dict[str, Any]:
        messages = runtime.ledger.messages(session_id, limit=100)
        return {
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "at": iso(m.created_at),
                    "meta": m.meta,
                }
                for m in reversed(messages)
            ],
        }

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, Any]:
        try:
            run = runtime.ledger.get_run(run_id)
        except NotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        commitment = runtime.ledger.get_commitment(run.commitment_id)
        payload = runtime.run_payload(run)
        artifact = None
        for item in runtime.ledger.evidence_for_run(run_id):
            if item.kind == "artifact" and item.path:
                path = Path(item.path).resolve()
                if runtime.data_dir.resolve() in path.parents and path.exists():
                    artifact = path.read_text(encoding="utf-8", errors="replace")[:20000]
                break
        return {
            "run": payload,
            "commitment": {
                "id": commitment.id,
                "title": commitment.title,
                "schedule": commitment.schedule,
                "timezone": commitment.timezone,
                "channel": commitment.delivery_channel,
            },
            "artifact": artifact,
        }

    @app.post("/api/sessions")
    def new_session(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        session_id = runtime.agent.new_session(str(payload.get("title") or "New conversation"))
        return {"session_id": session_id}

    @app.post("/api/chat/stream")
    def chat_stream(payload: dict[str, Any] = Body(...)) -> StreamingResponse:
        message = str(payload.get("message") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        if not message:
            raise HTTPException(422, "message is required")
        if len(message) > 6000:
            raise HTTPException(413, "message too long")
        if not session_id:
            session_id = runtime.agent.new_session(runtime.agent.title_for(message))
        events: queue.Queue[dict[str, Any] | None] = queue.Queue()

        def on_event(event: dict[str, Any]) -> None:
            events.put(event)

        def work() -> None:
            try:
                reply = runtime.agent.reply(session_id, message, on_event=on_event)
                events.put(
                    {
                        "type": "done",
                        "session_id": reply.session_id,
                        "provider": reply.provider,
                        "model": reply.model,
                        "cost_usd": reply.cost_usd,
                        "sources": reply.sources,
                        "trace": reply.trace,
                    }
                )
            except Exception as exc:  # noqa: BLE001 — the SSE stream must close cleanly
                events.put({"type": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            finally:
                events.put(None)

        threading.Thread(target=work, name="mitra-chat", daemon=True).start()

        def stream():
            while True:
                item = events.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/commitments/{commitment_id}/run")
    def run_now(commitment_id: str) -> dict[str, Any]:
        try:
            commitment = runtime.ledger.get_commitment(commitment_id)
        except NotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        runtime.ledger.record_audit(
            action="manual_run",
            target=commitment_id,
            decision="executed",
            risk="low",
            actor="user",
        )
        outcome = run_commitment_once(
            runtime.ledger,
            commitment_id,
            router=runtime.router,
            repo_root=REPO_ROOT,
            outbox_dir=runtime.data_dir / "outbox",
            toolbox=runtime.toolbox,
        )
        return {
            "outcome": {
                "run_id": outcome.run_id,
                "state": outcome.state,
                "detail": outcome.detail,
                "notice": str(outcome.notice_path) if outcome.notice_path else None,
            },
            "commitment": runtime.commitment_payload(commitment, full=True),
        }

    @app.post("/api/commitments/{commitment_id}/state")
    def set_state(commitment_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        state = str(payload.get("state") or "")
        if state not in {"active", "paused", "retired"}:
            raise HTTPException(422, "state must be active|paused|retired")
        try:
            runtime.ledger.get_commitment(commitment_id)
        except NotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        runtime.ledger._conn.execute(
            "UPDATE commitments SET state = ? WHERE id = ?", (state, commitment_id)
        )
        runtime.ledger._conn.commit()
        runtime.ledger.log_event(
            "commitment_state", commitment_id=commitment_id, detail={"state": state}
        )
        runtime.ledger.record_audit(
            action="commitment_state",
            target=commitment_id,
            decision="executed",
            risk="low",
            actor="user",
            detail={"state": state},
        )
        return runtime.commitment_payload(runtime.ledger.get_commitment(commitment_id), full=True)

    @app.post("/api/commitments")
    def create_commitment(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        content = str(payload.get("instruction") or "").strip()
        schedule = str(payload.get("schedule") or "07:00").strip()
        skill = str(payload.get("skill") or "daily_digest")
        if not title or not content:
            raise HTTPException(422, "title and instruction are required")
        commitment_id = runtime.ledger.add_commitment(
            title=title,
            skill=skill,
            schedule=schedule,
            timezone_name=str(payload.get("timezone") or runtime.settings.mitra_timezone),
            delivery_channel=str(payload.get("delivery_channel") or "outbox"),
        )
        runtime.ledger.add_instruction_version(
            commitment_id,
            content=content,
            params=payload.get("params") or {},
            effective_from=payload.get("effective_from"),
        )
        runtime.ledger.record_audit(
            action="commitment_created",
            target=commitment_id,
            decision="executed",
            risk="low",
            actor="user",
            detail={"title": title, "schedule": schedule},
        )
        return runtime.commitment_payload(runtime.ledger.get_commitment(commitment_id), full=True)

    @app.post("/api/commitments/{commitment_id}/instructions")
    def add_instruction(commitment_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        content = str(payload.get("content") or "").strip()
        if not content:
            raise HTTPException(422, "content is required")
        try:
            runtime.ledger.get_commitment(commitment_id)
        except NotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        effective_from = payload.get("effective_from")
        version_id = runtime.ledger.add_instruction_version(
            commitment_id,
            content=content,
            params=payload.get("params") or {},
            effective_from=effective_from,
            approved_by="user",
        )
        runtime.ledger.record_audit(
            action="instruction_version",
            target=commitment_id,
            decision="executed",
            risk="medium",
            actor="user",
            detail={"version_id": version_id, "effective_from": effective_from},
        )
        return runtime.commitment_payload(runtime.ledger.get_commitment(commitment_id), full=True)

    @app.post("/api/proposals/{proposal_id}/decide")
    def decide(proposal_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        decision = str(payload.get("decision") or "")
        if decision not in {"approved", "rejected"}:
            raise HTTPException(422, "decision must be approved|rejected")
        try:
            proposal = decide_proposal(
                runtime.ledger, runtime.selfmodel, proposal_id, decision=decision
            )
        except (NotFoundError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"proposal": proposal, "pages": runtime.bootstrap()["pages"]}

    @app.post("/api/approvals/{approval_id}/decide")
    def decide_tool(approval_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        decision = str(payload.get("decision") or "")
        if decision not in {"approved", "denied"}:
            raise HTTPException(422, "decision must be approved|denied")
        runtime.ledger.decide_approval(approval_id, decision=decision)
        result = None
        if decision == "approved":
            result = runtime.toolbox.execute_approved(approval_id).to_dict()
        return {"approval_id": approval_id, "decision": decision, "result": result}

    @app.post("/api/consolidate")
    def consolidate(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        hours = int(payload.get("since_hours") or 24)
        result = run_consolidation(
            runtime.ledger, runtime.selfmodel, runtime.router, since_hours=hours
        )
        runtime.ledger.record_audit(
            action="consolidation",
            decision="executed",
            risk="low",
            actor="user",
            detail={"window": result.window_messages, "created": len(result.created)},
        )
        return {
            "window_messages": result.window_messages,
            "created": result.created,
            "skipped": result.skipped,
            "method": result.method,
            "proposals": runtime.ledger.proposals(status="pending"),
        }

    @app.get("/api/memory/{page}")
    def read_page(page: str) -> dict[str, Any]:
        if page not in ALLOWED_PAGES:
            raise HTTPException(404, "unknown memory page")
        data = runtime.selfmodel.read(page)
        return {
            "name": page,
            "frontmatter": data.frontmatter,
            "body": data.body,
            "path": str(runtime.selfmodel.root / page),
        }

    @app.put("/api/memory/{page}")
    def write_page(page: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        if page not in ALLOWED_PAGES:
            raise HTTPException(404, "unknown memory page")
        body = str(payload.get("body") or "")
        if len(body) > 60_000:
            raise HTTPException(413, "page too large")
        existing = runtime.selfmodel.read(page)
        path = runtime.selfmodel.write(page, body, frontmatter=existing.frontmatter)
        runtime.ledger.log_event("memory_user_edit", detail={"page": page})
        runtime.ledger.record_audit(
            action="memory_edit",
            target=page,
            decision="executed",
            risk="medium",
            actor="user",
            detail={"chars": len(body)},
        )
        return {"name": page, "body": body, "path": str(path)}

    @app.get("/api/audit")
    def audit(limit: int = 80, decision: str | None = None) -> dict[str, Any]:
        limit = max(1, min(limit, 400))
        return {
            "audit": runtime.ledger.audit_log(limit=limit, decision=decision),
            "calls": runtime.ledger.model_calls(limit=limit),
        }

    @app.get("/api/stats")
    def stats(days: int = 7) -> dict[str, Any]:
        days = max(1, min(days, 90))
        usage = runtime.ledger.usage_summary(days=days)
        runs = runtime.ledger.run_stats(days=days)
        interventions = runtime.ledger.intervention_counts(since=time.time() - days * 86400)
        return {"usage": usage, "runs": runs, "interventions": interventions}

    @app.get("/api/export")
    def export() -> JSONResponse:
        """Portability: the whole ledger as JSON, owned by the user."""
        payload = runtime.bootstrap()
        payload["audit_full"] = runtime.ledger.audit_log(limit=400)
        payload["model_calls"] = runtime.ledger.model_calls(limit=400)
        payload["all_proposals"] = runtime.ledger.proposals(status=None, limit=200)
        payload["notes"] = runtime.ledger.notes(limit=200)
        return JSONResponse(
            payload,
            headers={"Content-Disposition": 'attachment; filename="mitra-export.json"'},
        )

    @app.post("/api/demo/reset")
    def demo_reset(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        if not runtime.settings.mitra_demo_mode:
            raise HTTPException(403, "reset is only available with MITRA_DEMO_MODE=1")
        if not is_admin(request):
            raise HTTPException(403, "admin token required")
        runtime.reset_demo()
        return runtime.bootstrap()

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main() -> None:  # pragma: no cover - CLI entry
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "mitra.web.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=int(__import__("os").environ.get("PORT", "8080")),
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    main()
