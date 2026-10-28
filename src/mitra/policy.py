"""Policy engine — our replacement for an agent shell's permission layer.

Everything a tool may do is declared up front:

* an explicit tool allowlist (unknown tool = deny);
* an egress allowlist enforced by one HTTP wrapper (HTTPS + exact host match);
* approval gates for risky actions (writes outside the memory inbox, outbound
  notifications), with deny-on-timeout semantics;
* an audit row for every decision, allowed or denied;
* secret hygiene — keys are read at call time and never placed in prompts.

The engine is deliberately small and synchronous. A policy that cannot be
explained in one screen is a policy nobody will audit.
"""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from mitra.ledger import Ledger

# Exact host match, HTTPS only (ARCHITECTURE §7).
EGRESS_ALLOWLIST: frozenset[str] = frozenset(
    {
        "api.tokenfactory.nebius.com",
        "api.tavily.com",
        "ntfy.sh",
        "api.telegram.org",
    }
)

MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_TIMEOUT_S = 25.0


class PolicyDenied(Exception):
    """A tool call was refused by policy."""


class EgressDenied(PolicyDenied):
    """A URL was outside the declared egress allowlist."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: str = "low"  # low | medium | high
    requires_approval: bool = False
    egress: tuple[str, ...] = field(default_factory=tuple)

    def schema(self) -> dict[str, Any]:
        """OpenAI tool definition (function calling)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class Decision:
    status: str  # allowed | approval_required | denied
    tool: str
    reason: str = ""
    approval_id: int | None = None

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


class PolicyEngine:
    def __init__(
        self,
        ledger: Ledger,
        *,
        tools: dict[str, ToolSpec],
        allowed_tools: set[str] | None = None,
        egress_allowlist: frozenset[str] = EGRESS_ALLOWLIST,
    ) -> None:
        self.ledger = ledger
        self.tools = tools
        self.allowed_tools = set(allowed_tools or tools.keys())
        self.egress_allowlist = egress_allowlist

    def spec(self, name: str) -> ToolSpec:
        return self.tools[name]

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [
            self.tools[name].schema() for name in sorted(self.allowed_tools) if name in self.tools
        ]

    def authorize(
        self,
        tool: str,
        args: dict[str, Any],
        *,
        session_id: str | None = None,
        approval_granted: bool = False,
    ) -> Decision:
        if tool not in self.tools:
            reason = f"unknown tool {tool!r}"
            self.ledger.record_audit(
                action="tool_call",
                target=tool,
                decision="denied",
                risk="high",
                detail={"reason": reason, "args": _redact(args)},
            )
            return Decision("denied", tool, reason)
        if tool not in self.allowed_tools:
            reason = f"tool {tool!r} is not in this session's allowlist"
            self.ledger.record_audit(
                action="tool_call",
                target=tool,
                decision="denied",
                risk="high",
                detail={"reason": reason},
            )
            return Decision("denied", tool, reason)

        spec = self.tools[tool]
        if spec.requires_approval and not approval_granted:
            approval_id = self.ledger.add_approval(tool=tool, args=args, session_id=session_id)
            self.ledger.record_audit(
                action="tool_call",
                target=tool,
                decision="approval_required",
                risk=spec.risk,
                detail={"args": _redact(args), "approval_id": approval_id},
            )
            return Decision(
                "approval_required",
                tool,
                f"{tool} writes outside the memory inbox and needs approval",
                approval_id=approval_id,
            )

        self.ledger.record_audit(
            action="tool_call",
            target=tool,
            decision="allowed",
            risk=spec.risk,
            detail={"args": _redact(args), "approval_granted": approval_granted},
        )
        return Decision("allowed", tool)

    # ------------------------------------------------------------------ egress

    def check_url(self, url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            raise EgressDenied(f"egress denied: {url} (HTTPS required)")
        if host not in self.egress_allowlist:
            raise EgressDenied(f"egress denied: {host} is not in the allowlist")
        if _is_private_host(host):
            raise EgressDenied(f"egress denied: {host} resolves to a private address")
        return host

    def http_post(
        self,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> httpx.Response:
        host = self.check_url(url)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.post(url, json=json_body, content=content, headers=headers)
        if len(response.content) > max_response_bytes:
            raise EgressDenied(f"egress denied: response from {host} exceeds size cap")
        return response

    def http_get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> httpx.Response:
        self.check_url(url)
        return httpx.get(url, headers=headers, timeout=timeout, follow_redirects=False)

    # ------------------------------------------------------------------ audit

    def record(
        self,
        action: str,
        *,
        target: str | None = None,
        decision: str = "executed",
        risk: str = "low",
        detail: Any = None,
        actor: str = "mitra",
    ) -> None:
        self.ledger.record_audit(
            action=action, target=target, decision=decision, risk=risk, detail=detail, actor=actor
        )


def safe_child(root: str | Path, relative: str) -> Path:
    """Resolve ``relative`` under ``root``, refusing traversal and symlink escapes."""
    root_path = Path(root).resolve()
    candidate = (root_path / relative).resolve()
    if root_path != candidate and root_path not in candidate.parents:
        raise PolicyDenied(f"path {relative!r} escapes {root_path}")
    return candidate


def _is_private_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
    return False


def _redact(args: dict[str, Any]) -> dict[str, Any]:
    """Never persist obvious secrets in the audit log."""
    redacted: dict[str, Any] = {}
    for key, value in (args or {}).items():
        if any(token in key.lower() for token in ("key", "token", "secret", "password")):
            redacted[key] = "***"
        else:
            redacted[key] = value
    return json.loads(json.dumps(redacted, ensure_ascii=False, default=str))
