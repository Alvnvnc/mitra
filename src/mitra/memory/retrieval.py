"""Retrieval v1: bounded, deterministic context assembly (no embeddings yet).

One function (`build_context`) so it can be unit tested and tuned; the agent
never gets "all memory" dumped into its prompt (ARCHITECTURE §4). Strategy:

1. Pinned pages first (priorities, preferences) — always relevant.
2. Other self-model pages that match the query terms (simple occurrence score).
3. Messages: FTS5 best matches, else the most recent ones.

Everything is assembled inside a character budget with a truncation flag, so
the caller can show "context truncated" instead of silently dropping memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mitra.ledger import Ledger
from mitra.memory.selfmodel import SelfModel

PINNED_PAGES: tuple[str, ...] = ("priorities.md", "preferences.md")
DEFAULT_BUDGET_CHARS = 4000  # ≈ 1000 tokens
_TERM_RE = re.compile(r"[a-zA-Z0-9_]{3,}")


@dataclass
class ContextBundle:
    text: str
    sources: list[str] = field(default_factory=list)
    budget_chars: int = DEFAULT_BUDGET_CHARS
    truncated: bool = False

    @property
    def approx_tokens(self) -> int:
        return len(self.text) // 4


def _terms(query: str) -> list[str]:
    seen: list[str] = []
    for term in _TERM_RE.findall((query or "").lower()):
        if term not in seen:
            seen.append(term)
    return seen[:16]


def _page_score(body: str, terms: list[str]) -> int:
    lowered = body.lower()
    return sum(lowered.count(term) for term in terms)


def build_context(
    ledger: Ledger,
    selfmodel: SelfModel,
    query: str,
    *,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
    k_messages: int = 6,
) -> ContextBundle:
    terms = _terms(query)

    items: list[tuple[str, str]] = []

    # 1) pinned pages — always first
    for name in PINNED_PAGES:
        page = selfmodel.read(name)
        if page.body.strip():
            items.append((name, page.body.strip()))

    # 2) other pages with at least one query-term hit
    for name in selfmodel.pages():
        if name in PINNED_PAGES:
            continue
        page = selfmodel.read(name)
        body = page.body.strip()
        if body and terms and _page_score(body, terms) > 0:
            items.append((name, body))

    # 3) messages — FTS matches first; otherwise most recent
    messages = ledger.search_messages(query, limit=k_messages)
    if not messages:
        messages = ledger.messages(limit=k_messages)
    for message in reversed(messages):  # oldest → newest within the selection
        items.append((f"message:{message.session_id}#{message.id}", f"[{message.role}] {message.content}"))

    # assemble within budget
    blocks: list[str] = []
    included: list[str] = []
    remaining = max(int(budget_chars), 0)
    truncated = False

    for source, text in items:
        if remaining <= 0:
            truncated = True
            break
        header = f"### {source}\n"
        room = remaining - len(header)
        if room <= 0:
            truncated = True
            break
        chunk = text if len(text) <= room else text[:room]
        if len(chunk) < len(text):
            truncated = True
        block = header + chunk
        blocks.append(block)
        included.append(source)
        remaining -= len(block) + 2

    return ContextBundle(
        text="\n\n".join(blocks),
        sources=included,
        budget_chars=budget_chars,
        truncated=truncated,
    )