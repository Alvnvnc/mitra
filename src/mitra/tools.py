"""Tool registry — the only way Mitra touches the outside world.

Each tool declares its schema, risk level and egress hosts. Execution goes
through :class:`mitra.policy.PolicyEngine`, so a tool call that is not
allowlisted, not approved, or points at an unlisted host cannot run. Results
are plain dictionaries: they go back to the model *and* into the audit log.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mitra.config import get_settings
from mitra.delivery import send_ntfy
from mitra.ledger import Ledger
from mitra.memory.selfmodel import SelfModel
from mitra.policy import Decision, PolicyDenied, PolicyEngine, ToolSpec, safe_child

TAVILY_URL = "https://api.tavily.com/search"

# Enough for a brief plus its facts; a tool result is a context cost, not a file copy.
MAX_ARTIFACT_CHARS = 8000

TOOL_SPECS: dict[str, ToolSpec] = {
    "web_search": ToolSpec(
        name="web_search",
        description=(
            "Search the live web with Tavily. Use for current facts, prices, news or "
            "anything the local memory cannot answer. Returns titles, URLs and snippets."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query, specific and short."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        risk="low",
        egress=("api.tavily.com",),
    ),
    "memory_search": ToolSpec(
        name="memory_search",
        description=(
            "Search Mitra's own memory: self-model pages and past conversation messages. "
            "Read-only. Always prefer this before asking the user to repeat themselves."
        ),
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        risk="low",
    ),
    "commitment_status": ToolSpec(
        name="commitment_status",
        description=(
            "Read the commitment ledger: schedule, current instruction version, last run, "
            "evidence check and delivery state. Read-only and authoritative."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk="low",
    ),
    "artifact_read": ToolSpec(
        name="artifact_read",
        description=(
            "Read what a run actually produced: the brief or digest Markdown and its facts "
            "JSON. Call with no arguments first to list the newest artifacts, then call again "
            "with an exact file name from that list. Never guess a date into a file name. "
            "Read-only and local to this instance."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "File name from the listing, e.g. morning-brief-2026-10-29.md",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
            "additionalProperties": False,
        },
        risk="low",
    ),
    "note_write": ToolSpec(
        name="note_write",
        description=(
            "Save a Markdown note under data/notes. This is a write outside the memory "
            "inbox, so it requires explicit approval in the dashboard."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string", "description": "Markdown body."},
            },
            "required": ["title", "body"],
            "additionalProperties": False,
        },
        risk="medium",
        requires_approval=True,
    ),
    "notify_send": ToolSpec(
        name="notify_send",
        description=(
            "Push a short notification through the ntfy.sh lane. Outbound communication, "
            "so it requires explicit approval."
        ),
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 800}},
            "required": ["text"],
            "additionalProperties": False,
        },
        risk="high",
        requires_approval=True,
        egress=("ntfy.sh",),
    ),
}

DEFAULT_ALLOWED = tuple(TOOL_SPECS)


def _slug(text: str, *, words: int = 6) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return "-".join(cleaned.split("-")[:words]) or "note"


@dataclass
class ToolResult:
    ok: bool
    tool: str
    data: dict[str, Any]
    status: str = "ok"  # ok | approval_required | denied | error
    approval_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "status": self.status,
            "approval_id": self.approval_id,
            **self.data,
        }


class ToolBox:
    def __init__(
        self,
        ledger: Ledger,
        selfmodel: SelfModel,
        *,
        data_dir: str | Path | None = None,
        policy: PolicyEngine | None = None,
    ) -> None:
        settings = get_settings()
        self.ledger = ledger
        self.selfmodel = selfmodel
        self.data_dir = Path(data_dir) if data_dir else Path(settings.mitra_data_dir)
        self.policy = policy or PolicyEngine(ledger, tools=TOOL_SPECS)
        self.settings = settings

    # ------------------------------------------------------------------ schema

    def schemas(self) -> list[dict[str, Any]]:
        return self.policy.tool_schemas()

    # --------------------------------------------------------------- dispatch

    def execute(
        self, name: str, args: dict[str, Any], *, session_id: str | None = None
    ) -> ToolResult:
        decision: Decision = self.policy.authorize(name, args, session_id=session_id)
        if decision.status == "denied":
            return ToolResult(False, name, {"error": decision.reason}, status="denied")
        if decision.status == "approval_required":
            return ToolResult(
                False,
                name,
                {"note": decision.reason, "args": args},
                status="approval_required",
                approval_id=decision.approval_id,
            )
        try:
            handler = getattr(self, f"_tool_{name}")
        except AttributeError:
            return ToolResult(False, name, {"error": "no executor registered"}, status="error")
        started = time.perf_counter()
        try:
            data = handler(args, session_id=session_id)
        except PolicyDenied as exc:
            self.policy.record(
                "tool_exec", target=name, decision="denied", risk="high", detail={"error": str(exc)}
            )
            return ToolResult(False, name, {"error": str(exc)}, status="denied")
        except Exception as exc:  # noqa: BLE001 — tools fail loudly, never silently
            self.policy.record(
                "tool_exec",
                target=name,
                decision="error",
                risk="medium",
                detail={"error": f"{type(exc).__name__}: {exc}"},
            )
            return ToolResult(
                False, name, {"error": f"{type(exc).__name__}: {exc}"}, status="error"
            )
        elapsed = round((time.perf_counter() - started) * 1000)
        self.policy.record(
            "tool_exec",
            target=name,
            decision="executed",
            risk="low",
            detail={"ms": elapsed, "ok": True},
        )
        return ToolResult(True, name, data)

    def execute_approved(self, approval_id: int) -> ToolResult:
        """Run a tool call whose approval was granted (re-checked, not trusted)."""
        pending = {row["id"]: row for row in self.ledger.approvals(status="approved")}
        approval = pending.get(approval_id)
        if approval is None:
            return ToolResult(
                False, "unknown", {"error": "approval not found or not approved"}, status="denied"
            )
        name = approval["tool"]
        decision = self.policy.authorize(
            name, approval["args"], session_id=approval["session_id"], approval_granted=True
        )
        if decision.status == "denied":
            return ToolResult(False, name, {"error": decision.reason}, status="denied")
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolResult(False, name, {"error": "no executor registered"}, status="error")
        try:
            data = handler(approval["args"], session_id=approval["session_id"])
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                False, name, {"error": f"{type(exc).__name__}: {exc}"}, status="error"
            )
        self.policy.record(
            "tool_exec",
            target=name,
            decision="executed",
            risk="medium",
            detail={"approval_id": approval_id, "ok": True},
        )
        self.ledger._conn.execute(
            "UPDATE approvals SET result = ? WHERE id = ?",
            (json.dumps({"ok": True, **data}, ensure_ascii=False), approval_id),
        )
        self.ledger._conn.commit()
        return ToolResult(True, name, data)

    # ------------------------------------------------------------------- tools

    def _tool_web_search(
        self, args: dict[str, Any], *, session_id: str | None = None
    ) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        if not query:
            return {"error": "empty query", "results": []}
        max_results = max(1, min(int(args.get("max_results") or 3), 5))
        api_key = (self.settings.tavily_api_key or "").strip()
        self.ledger.log_event(
            "web_search", detail={"query": query, "lane": "live" if api_key else "cache"}
        )

        if not api_key:
            cached = self._cached_search(query)
            if cached:
                cached["lane"] = "demo-cache"
                cached["note"] = (
                    "Tavily is not configured on this instance; these are cached demo "
                    "results and are labelled as such."
                )
                return cached
            return {
                "query": query,
                "results": [],
                "lane": "unavailable",
                "error": "TAVILY_API_KEY is not configured and no cached demo result matches",
            }

        response = self.policy.http_post(
            TAVILY_URL,
            json_body={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": False,
            },
        )
        if response.status_code != 200:
            return {
                "query": query,
                "results": [],
                "lane": "live",
                "error": f"tavily http {response.status_code}",
            }
        payload = response.json()
        results = [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "score": item.get("score"),
            }
            for item in (payload.get("results") or [])[:max_results]
        ]
        return {"query": query, "results": results, "lane": "live"}

    def _tool_memory_search(
        self, args: dict[str, Any], *, session_id: str | None = None
    ) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        terms = [t for t in re.findall(r"[a-zA-Z0-9_]{3,}", query.lower())][:8]
        pages = []
        for name in self.selfmodel.pages():
            page = self.selfmodel.read(name)
            haystack = f"{name}\n{page.body}".lower()
            if not terms or any(term in haystack for term in terms):
                pages.append(
                    {
                        "page": name,
                        "title": page.frontmatter.get("title", name),
                        "updated": page.frontmatter.get("updated"),
                        "excerpt": page.body.strip()[:600],
                    }
                )
        messages = self.ledger.search_messages(query, limit=6) if query else []
        return {
            "query": query,
            "pages": pages[:5],
            "messages": [
                {"id": m.id, "role": m.role, "content": m.content[:500]} for m in messages
            ],
        }

    def _tool_commitment_status(
        self, args: dict[str, Any], *, session_id: str | None = None
    ) -> dict[str, Any]:
        rows = []
        for commitment in self.ledger.list_commitments():
            latest = self.ledger.latest_run(commitment.id)
            try:
                version = self.ledger.resolve_instruction(commitment.id)
                version_label = f"v{version.id}"
            except Exception:  # noqa: BLE001 — no active version is a valid state
                version_label = "none"
            rows.append(
                {
                    "id": commitment.id,
                    "title": commitment.title,
                    "schedule": f"{commitment.schedule} {commitment.timezone}",
                    "state": commitment.state,
                    "instruction": version_label,
                    "last_run": {
                        "id": latest.id,
                        "state": latest.state,
                        "at": datetime.fromtimestamp(latest.run_at, tz=UTC).isoformat(
                            timespec="minutes"
                        ),
                        "error": latest.error,
                        "delivered_at": latest.delivered_at,
                    }
                    if latest
                    else None,
                }
            )
        return {"commitments": rows, "count": len(rows)}

    def _tool_artifact_read(
        self, args: dict[str, Any], *, session_id: str | None = None
    ) -> dict[str, Any]:
        """Read a run's output, so chat can answer "what did it actually say?"."""
        root = safe_child(self.data_dir, "artifacts")
        if not root.is_dir():
            return {"artifacts": [], "note": "nothing has been produced yet"}

        name = str(args.get("name") or "").strip()
        if not name:
            limit = max(1, min(int(args.get("limit") or 8), 20))
            files = [
                path for path in root.iterdir() if path.is_file() and not path.name.startswith(".")
            ]
            files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            return {
                "artifacts": [
                    {
                        "name": path.name,
                        "bytes": path.stat().st_size,
                        "modified": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(
                            timespec="minutes"
                        ),
                    }
                    for path in files[:limit]
                ],
                "count": len(files),
                "hint": "Read one by exact name; the first row is the most recent file.",
            }

        path = safe_child(root, name)
        if not path.is_file():
            # Suggest by the leading segments of the requested stem, so
            # "morning-brief.md" still finds "morning-brief-2026-10-29.md".
            tokens = [part for part in name.rsplit(".", 1)[0].lower().split("-") if part][:3]
            matches = sorted(
                candidate.name
                for candidate in root.iterdir()
                if candidate.is_file() and all(token in candidate.name.lower() for token in tokens)
            )[:5]
            newest = sorted(
                (candidate for candidate in root.iterdir() if candidate.is_file()),
                key=lambda candidate: candidate.stat().st_mtime,
                reverse=True,
            )[:6]
            return {
                "error": f"no artifact named {name!r}",
                "did_you_mean": matches,
                "available": [candidate.name for candidate in newest],
                "hint": "Read one of these exact names, or call with no arguments to list.",
            }

        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            "name": path.name,
            "bytes": len(text.encode("utf-8")),
            "truncated": len(text) > MAX_ARTIFACT_CHARS,
            "text": text[:MAX_ARTIFACT_CHARS],
        }

    def _tool_note_write(
        self, args: dict[str, Any], *, session_id: str | None = None
    ) -> dict[str, Any]:
        title = str(args.get("title") or "Untitled note").strip()
        body = str(args.get("body") or "").strip()
        if not body:
            return {"error": "empty note body"}
        notes_dir = safe_child(self.data_dir, "notes")
        notes_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{_slug(title)}.md"
        path = safe_child(notes_dir, filename)
        path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        note_id = self.ledger.add_note(title=title, body=body, path=str(path), tags=["chat"])
        self.ledger.log_event("note_written", detail={"note_id": note_id, "path": str(path)})
        return {"note_id": note_id, "path": str(path), "title": title}

    def _tool_notify_send(
        self, args: dict[str, Any], *, session_id: str | None = None
    ) -> dict[str, Any]:
        text = str(args.get("text") or "").strip()
        if not text:
            return {"error": "empty notification"}
        result = send_ntfy(text, title="Mitra")
        if not result.ok:
            return {"error": result.error or "ntfy delivery failed"}
        return {"receipt": result.receipt, "lane": result.lane}

    # ------------------------------------------------------------------ cache

    def _cached_search(self, query: str) -> dict[str, Any] | None:
        cache_dir = self.data_dir / "search_cache"
        if not cache_dir.exists():
            return None
        candidates = [cache_dir / f"{_slug(query, words=4)}.json", cache_dir / "default.json"]
        for path in candidates:
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(payload, dict) and payload.get("results"):
                    return payload
        return None
