"""Nightly consolidation: window -> candidate facts -> approval inbox.

The write path is deliberately narrow (ARCHITECTURE §2): a model may *propose*
memory, never apply it. Proposals land in the inbox and only an explicit user
decision changes a Markdown page. Corrections from the user always win because
their message is the source reference attached to the proposal.

When Token Factory is unavailable the deterministic extractor below still runs,
so the nightly job never silently does nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from mitra.ledger import Ledger
from mitra.memory.selfmodel import SelfModel
from mitra.models.router import ModelRouter

MAX_WINDOW_MESSAGES = 60
ALLOWED_PAGES = {"people.md", "projects.md", "priorities.md", "preferences.md", "patterns.md"}

SYSTEM = """You consolidate one day of a user's conversation into durable memory proposals.
Return STRICT JSON only, shape:
{"facts":[{"page":"preferences.md","kind":"preference","title":"short label",
"body":"one factual sentence in the user's own language","rationale":"why this is durable",
"source_message_ids":[1,2]}]}

Rules:
- Only durable facts, preferences, people, projects or recurring patterns. No tasks,
  no moods, no guesses, no secrets.
- page must be one of people.md, projects.md, priorities.md, preferences.md, patterns.md.
- Prefer nothing over speculation. An empty list is a valid answer.
- Each body is one sentence, <=240 characters, and must be supported by message ids."""


@dataclass
class ConsolidationResult:
    window_messages: int
    created: list[int]
    skipped: int
    method: str


def _window(ledger: Ledger, since_hours: int) -> list[Any]:
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    return list(reversed(ledger.messages(limit=MAX_WINDOW_MESSAGES, since=since)))


def _page_body(selfmodel: SelfModel, page: str) -> str:
    try:
        return selfmodel.read(page).body.strip()
    except ValueError:
        return ""


def _already_known(selfmodel: SelfModel, page: str, body: str) -> bool:
    haystack = _page_body(selfmodel, page).lower()
    needle = re.sub(r"\s+", " ", body.lower()).strip()
    return bool(needle) and needle[:80] in haystack


def _dedupe_pending(ledger: Ledger, page: str, body: str) -> bool:
    needle = re.sub(r"\s+", " ", body.lower()).strip()[:80]
    for proposal in ledger.proposals(status="pending", limit=100):
        if proposal["page"] == page and needle in proposal["body"].lower():
            return True
    return False


def _apply(ledger: Ledger, selfmodel: SelfModel, proposal: dict[str, Any]) -> None:
    page = proposal["page"]
    existing = selfmodel.read(page)
    body = existing.body.rstrip()
    bullet = proposal["body"].strip()
    new_body = f"{body}\n- {bullet}\n" if body else f"- {bullet}\n"
    sources = ", ".join(f"message #{ref}" for ref in proposal.get("source_refs") or [])
    frontmatter = dict(existing.frontmatter or {})
    frontmatter["sources"] = sources or frontmatter.get("sources", "")
    selfmodel.write(page, new_body, frontmatter=frontmatter)
    ledger.log_event(
        "memory_applied",
        detail={"proposal_id": proposal["id"], "page": page, "body": bullet},
    )


def decide_proposal(
    ledger: Ledger, selfmodel: SelfModel, proposal_id: int, *, decision: str
) -> dict[str, Any]:
    proposal = ledger.get_proposal(proposal_id)
    if proposal["status"] != "pending":
        return proposal
    if decision == "approved":
        if proposal["page"] not in ALLOWED_PAGES:
            raise ValueError(f"refusing to write to non-memory page {proposal['page']!r}")
        _apply(ledger, selfmodel, proposal)
    ledger.decide_proposal(proposal_id, decision=decision)
    return ledger.get_proposal(proposal_id)


def _heuristic(ledger: Ledger, messages: list[Any]) -> list[dict[str, Any]]:
    """Deterministic fallback: explicit first-person statements only."""
    patterns = [
        (
            r"\b(i prefer|i always|i never|saya lebih suka|saya selalu|saya tidak pernah)\b",
            "preferences.md",
            "preference",
        ),
        (r"^(my name is|call me|nama saya|panggil saya)\b", "people.md", "person"),
        (
            r"\b(i work on|i'm building|saya sedang mengerjakan|proyek saya)\b",
            "projects.md",
            "project",
        ),
        (r"\b(remember that|ingat bahwa|catat bahwa)\b", "preferences.md", "fact"),
    ]
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for message in messages:
        if message.role != "user":
            continue
        text = re.sub(r"\s+", " ", message.content).strip()
        for pattern, page, kind in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            sentence = text[match.start() :]
            sentence = re.split(r"(?<=[.!?])\s+", sentence)[0][:240].strip()
            key = sentence.lower()[:80]
            if key in seen or _already_known_by_text(ledger, page, sentence):
                continue
            seen.add(key)
            found.append(
                {
                    "page": page,
                    "kind": kind,
                    "title": sentence[:48],
                    "body": sentence,
                    "rationale": "explicit first-person statement; user correction wins",
                    "source_message_ids": [message.id],
                }
            )
            break
    return found


def _already_known_by_text(ledger: Ledger, page: str, body: str) -> bool:
    needle = body.lower()[:80]
    for proposal in ledger.proposals(status=None, limit=200):
        if proposal["page"] == page and needle in proposal["body"].lower():
            return True
    return False


def _parse_model_json(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except ValueError:
        return []
    facts = payload.get("facts")
    return [fact for fact in facts if isinstance(fact, dict)] if isinstance(facts, list) else []


def run_consolidation(
    ledger: Ledger,
    selfmodel: SelfModel,
    router: ModelRouter,
    *,
    since_hours: int = 24,
) -> ConsolidationResult:
    messages = _window(ledger, since_hours)
    if not messages:
        return ConsolidationResult(0, [], 0, "no-window")

    current = {page: _page_body(selfmodel, page) for page in sorted(ALLOWED_PAGES)}
    transcript = "\n".join(
        f"[{m.id}] {m.role}: {m.content[:700]}" for m in messages if m.role in {"user", "assistant"}
    )
    method = "model"
    facts: list[dict[str, Any]] = []
    try:
        response = router.chat(
            purpose="fast",
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        "CURRENT PAGES (Markdown bodies):\n"
                        + json.dumps(current, ensure_ascii=False, indent=1)
                        + "\n\nWINDOW TRANSCRIPT:\n"
                        + transcript
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=900,
            response_format={"type": "json_object"},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        if response.provider == "demo":
            method = "deterministic"
            facts = _heuristic(ledger, messages)
        else:
            facts = _parse_model_json(response.content)
            if not facts:
                method = "deterministic"
                facts = _heuristic(ledger, messages)
    except Exception as exc:  # noqa: BLE001 — never let storage fail silently
        ledger.log_event("consolidation_model_error", detail=str(exc))
        method = "deterministic"
        facts = _heuristic(ledger, messages)

    created: list[int] = []
    skipped = 0
    for fact in facts:
        page = str(fact.get("page") or "preferences.md")
        body = re.sub(r"\s+", " ", str(fact.get("body") or "")).strip()
        if page not in ALLOWED_PAGES or not body:
            skipped += 1
            continue
        if _already_known(selfmodel, page, body) or _dedupe_pending(ledger, page, body):
            skipped += 1
            continue
        refs = [int(r) for r in fact.get("source_message_ids") or [] if str(r).isdigit()]
        before = _page_body(selfmodel, page)
        after = f"{before}\n- {body}\n" if before else f"- {body}\n"
        proposal_id = ledger.add_proposal(
            kind=str(fact.get("kind") or "fact"),
            page=page,
            title=str(fact.get("title") or body[:48]),
            body=body,
            before=before,
            after=after,
            rationale=str(fact.get("rationale") or "consolidated from the last window"),
            source_refs=refs,
        )
        created.append(proposal_id)

    ledger.log_event(
        "consolidation_run",
        detail={
            "window_messages": len(messages),
            "created": created,
            "skipped": skipped,
            "method": method,
        },
    )
    return ConsolidationResult(len(messages), created, skipped, method)
