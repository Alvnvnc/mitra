"""The chat agent: bounded memory, governed tools, honest answers.

The loop is intentionally small:

    retrieve (bounded) -> model -> tool calls (policy-checked) -> model -> reply

Chat only *reads* memory. Writes happen through the approval inbox or an
explicit user action, never as a side effect of a sentence. Every tool call is
policy-checked and audited, and every model call is recorded with cost.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from mitra.config import get_settings
from mitra.ledger import Ledger
from mitra.memory.retrieval import build_context
from mitra.memory.selfmodel import SelfModel
from mitra.models.router import BudgetExceeded, ModelRouter
from mitra.tools import ToolBox

MAX_TOOL_ROUNDS = 3
HISTORY_MESSAGES = 8

SYSTEM_TEMPLATE = """You are Mitra, a private, self-hosted personal AI that the user owns.
You are calm, specific and brief. You never perform hidden actions.

HARD RULES
1. Ground every factual claim in LIVE STATE or MEMORY CONTEXT below. If the
   context does not contain the answer, say so plainly and ask one short
   question. Never invent a commitment, a run, a source or a memory.
2. Chat is read-only for memory. If something should be remembered, say it will
   be proposed to the approval inbox; do not claim you already saved it.
3. "Done" requires checked evidence. Do not call a commitment successful from
   the fact that it ran; read its evidence and delivery state.
4. Tool calls are governed. If a tool returns approval_required, tell the user
   which dashboard inbox item needs approval. Never claim the action happened.
5. Never reveal API keys, tokens, or file paths outside the workspace.
6. Reply in the language the user writes in (Indonesian or English). Use short
   paragraphs or bullets. No filler openers.

LIVE STATE (authoritative, read from the ledger now)
{state}

MEMORY CONTEXT (retrieved, bounded; sources are named)
{context}
"""


@dataclass
class ChatReply:
    session_id: str
    text: str
    sources: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "nebius"
    model: str = ""
    cost_usd: float = 0.0
    message_id: int | None = None


def _fmt_run(ledger: Ledger, run: Any) -> str:
    if run is None:
        return "no runs yet"
    when = datetime.fromtimestamp(run.run_at, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    evidence = ledger.evidence_for_run(run.id)
    checks = ", ".join(f"{e.kind}:{e.check_result}" for e in evidence) or "no evidence"
    delivery = "delivered" if run.delivered_at else "not delivered"
    error = f" error={run.error[:80]}" if run.error else ""
    return f"{run.state} at {when} (evidence {checks}; {delivery}){error}"


def state_summary(ledger: Ledger, *, tz_name: str | None = None) -> str:
    """Compact, authoritative snapshot for the prompt (no model involvement)."""
    settings = get_settings()
    tz = ZoneInfo(tz_name or settings.mitra_timezone)
    now = datetime.now(UTC).astimezone(tz)
    lines = [f"now: {now.strftime('%Y-%m-%d %H:%M %Z')}"]
    commitments = ledger.list_commitments(state=None)
    if not commitments:
        lines.append("- no commitments yet")
    for commitment in commitments:
        try:
            version = ledger.resolve_instruction(commitment.id)
            version_text = f"v{version.id} effective {datetime.fromtimestamp(version.effective_from, tz=tz):%Y-%m-%d %H:%M}"
        except Exception:  # noqa: BLE001
            version_text = "no active instruction"
        latest = ledger.latest_run(commitment.id)
        lines.append(
            f"- {commitment.title} [{commitment.state}] schedule {commitment.schedule} "
            f"{commitment.timezone}; skill {commitment.skill}; instruction {version_text}; "
            f"last run: {_fmt_run(ledger, latest)}"
        )
    pending = len(ledger.proposals(status="pending")) + len(ledger.approvals(status="pending"))
    lines.append(f"- approval inbox: {pending} item(s) pending")
    usage = ledger.usage_summary(days=1)
    lines.append(f"- inference today: {usage['calls']} call(s), ${usage['cost_usd']:.4f}")
    return "\n".join(lines)


class ChatAgent:
    def __init__(
        self,
        ledger: Ledger,
        router: ModelRouter,
        selfmodel: SelfModel,
        toolbox: ToolBox,
        *,
        tz_name: str | None = None,
    ) -> None:
        self.ledger = ledger
        self.router = router
        self.selfmodel = selfmodel
        self.toolbox = toolbox
        settings = get_settings()
        self.tz_name = tz_name or settings.mitra_timezone

    # ---------------------------------------------------------------- sessions

    def new_session(self, title: str = "New conversation") -> str:
        session_id = f"ses_{uuid.uuid4().hex[:10]}"
        self.ledger.ensure_session(session_id, title)
        return session_id

    @staticmethod
    def title_for(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return "New conversation"
        return cleaned[:60] + ("…" if len(cleaned) > 60 else "")

    # -------------------------------------------------------------------- loop

    def reply(
        self,
        session_id: str,
        text: str,
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> ChatReply:
        emit = on_event or (lambda _event: None)
        text = (text or "").strip()
        if not text:
            raise ValueError("empty message")
        if self.router.budget_exceeded():
            raise BudgetExceeded(
                f"daily inference budget (${self.router.daily_budget_usd:.2f}) reached"
            )

        self.ledger.ensure_session(session_id, self.title_for(text))
        self.ledger.touch_session(session_id, title=self.title_for(text))
        user_message_id = self.ledger.log_message(session_id, "user", text)

        started = time.perf_counter()
        context = build_context(self.ledger, self.selfmodel, text)
        sources = list(context.sources)
        emit(
            {
                "type": "context",
                "sources": sources,
                "truncated": context.truncated,
                "approx_tokens": context.approx_tokens,
            }
        )
        trace: list[dict[str, Any]] = [
            {
                "stage": "retrieve",
                "label": f"{len(sources)} memory source(s), ~{context.approx_tokens} tokens",
                "ms": int((time.perf_counter() - started) * 1000),
            }
        ]

        system = SYSTEM_TEMPLATE.format(
            state=state_summary(self.ledger, tz_name=self.tz_name),
            context=context.text or "(no memory matched this question)",
        )
        history = list(reversed(self.ledger.messages(session_id, limit=HISTORY_MESSAGES)))
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for message in history:
            if message.role in {"user", "assistant"} and message.content.strip():
                messages.append({"role": message.role, "content": message.content})
        if not history or history[-1].id != user_message_id:
            messages.append({"role": "user", "content": text})

        tool_schemas = self.toolbox.schemas()
        provider = self.router.provider
        model = self.router.model_for("chat") if provider == "nebius" else "mitra/local-demo"
        total_cost = 0.0

        for round_index in range(MAX_TOOL_ROUNDS):
            emit({"type": "stage", "stage": "model", "round": round_index + 1})
            try:
                response = self.router.chat(
                    purpose="chat",
                    messages=messages,
                    tool_schemas=tool_schemas,
                    temperature=0.3,
                    max_tokens=1100,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
            except BudgetExceeded:
                raise
            except Exception as exc:  # noqa: BLE001 — surface, do not fake a reply
                self.ledger.log_event(
                    "chat_error", detail={"session_id": session_id, "error": str(exc)}
                )
                fallback = (
                    "I could not reach the model just now, so I am not going to pretend I "
                    "answered. Your message is saved; retry when the provider is back.\n\n"
                    f"`{type(exc).__name__}: {str(exc)[:180]}`"
                )
                self.ledger.log_message(
                    session_id, "assistant", fallback, meta={"error": type(exc).__name__}
                )
                return ChatReply(session_id, fallback, sources, trace, provider, model)

            provider = response.provider
            model = response.model
            total_cost += response.cost_usd
            trace.append(
                {
                    "stage": "model",
                    "label": f"{response.model} · {response.prompt_tokens}+{response.completion_tokens} tok",
                    "ms": int((time.perf_counter() - started) * 1000),
                }
            )

            if not response.tool_calls:
                final_text = response.content.strip()
                if not final_text:
                    final_text = (
                        "The model returned an empty answer. I would rather say that than "
                        "invent one — try rephrasing, or open the commitment ledger directly."
                    )
                emit({"type": "final", "text": final_text})
                trace.append(
                    {
                        "stage": "done",
                        "label": f"{provider} · ${total_cost:.4f}"
                        if provider == "nebius"
                        else "local demo model · $0.0000",
                        "ms": int((time.perf_counter() - started) * 1000),
                    }
                )
                message_id = self.ledger.log_message(
                    session_id,
                    "assistant",
                    final_text,
                    meta={
                        "provider": provider,
                        "model": model,
                        "cost_usd": total_cost,
                        "sources": sources,
                        "trace": trace,
                    },
                )
                self.ledger.log_event(
                    "chat_reply",
                    detail={"session_id": session_id, "provider": provider, "cost_usd": total_cost},
                )
                return ChatReply(
                    session_id=session_id,
                    text=final_text,
                    sources=sources,
                    trace=trace,
                    provider=provider,
                    model=model,
                    cost_usd=total_cost,
                    message_id=message_id,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.raw_arguments or "{}",
                            },
                        }
                        for call in response.tool_calls
                    ],
                }
            )

            for call in response.tool_calls:
                emit(
                    {
                        "type": "tool",
                        "tool": call.name,
                        "args": call.arguments,
                        "status": "running",
                    }
                )
                tool_started = time.perf_counter()
                result = self.toolbox.execute(call.name, call.arguments, session_id=session_id)
                payload = result.to_dict()
                trace.append(
                    {
                        "stage": "tool",
                        "label": f"{call.name} → {result.status}",
                        "ms": int((time.perf_counter() - tool_started) * 1000),
                        "detail": payload,
                    }
                )
                emit(
                    {
                        "type": "tool",
                        "tool": call.name,
                        "args": call.arguments,
                        "status": result.status,
                        "approval_id": result.approval_id,
                        "preview": _tool_preview(payload),
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": _json_safe(payload),
                    }
                )

        # Tool round budget exhausted: be explicit instead of looping forever.
        final_text = (
            "I stopped after three tool rounds without a final answer. The trace is in the "
            "audit log; ask me to continue and I will narrow the search."
        )
        self.ledger.log_message(
            session_id, "assistant", final_text, meta={"provider": provider, "trace": trace}
        )
        emit({"type": "final", "text": final_text})
        return ChatReply(session_id, final_text, sources, trace, provider, model, total_cost)


def _tool_preview(payload: dict[str, Any]) -> str:
    if payload.get("error"):
        return str(payload["error"])[:180]
    results = payload.get("results")
    if isinstance(results, list) and results:
        return f"{len(results)} result(s)"
    if payload.get("status") == "approval_required":
        return "waiting for approval"
    if payload.get("path"):
        return str(payload["path"])
    if payload.get("commitments") is not None:
        return f"{payload.get('count', 0)} commitment(s)"
    return "ok"


def _json_safe(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, default=str)[:6000]
