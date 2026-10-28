"""Deterministic local model — the demo/offline fallback.

Mitra's inference target is NVIDIA Nemotron on Nebius Token Factory. A live demo
must not depend on network reachability or a valid key at the moment a judge
clicks something, so the router can fall back to this local model. It is not a
language model: it composes answers from the *real* state in the prompt
(commitments, runs, retrieved memory, tool output) with fixed rules. Responses
are labelled ``demo`` everywhere, and the UI shows that label, so no one can
mistake this for a Nemotron generation.

Two other call sites depend on a chat-completion-shaped result:

* the digest skill (``purpose="chat"``, facts in the prompt) — we write the
  three required bullets from the facts instead of calling out;
* consolidation (``purpose="fast"``, JSON contract) — handled by the
  consolidation job's deterministic extractor, not here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

MODEL_ID = "mitra/local-demo"

_ID_WORDS = {
    "aku",
    "saya",
    "kamu",
    "yang",
    "dan",
    "untuk",
    "dengan",
    "tidak",
    "sudah",
    "apa",
    "bagaimana",
    "hari",
    "ini",
    "besok",
    "tolong",
    "bisa",
    "ada",
    "dari",
    "itu",
    "atau",
    "juga",
    "masih",
    "belum",
    "kenapa",
    "kapan",
}
_EN_WORDS = {
    "the",
    "what",
    "how",
    "when",
    "why",
    "you",
    "your",
    "and",
    "for",
    "with",
    "please",
    "today",
    "tomorrow",
    "about",
    "show",
    "tell",
    "give",
    "have",
}

_TOOL_HINTS = (
    "search",
    "research",
    "look up",
    "latest",
    "news",
    "find out",
    "cari",
    "telusuri",
    "riset",
    "terbaru",
    "berita",
    "cek harga",
    "sumber",
)
_STATUS_HINTS = (
    "status",
    "commitment",
    "run",
    "today",
    "brief",
    "schedule",
    "failed",
    "delivered",
    "komitmen",
    "jadwal",
    "hari ini",
    "gagal",
    "terkirim",
    "laporan",
)
_MEMORY_HINTS = (
    "remember",
    "memory",
    "prefer",
    "about me",
    "profile",
    "ingat",
    "memori",
    "preferensi",
    "tentang saya",
    "siapa saya",
    "kebiasaan",
)


def detect_language(text: str) -> str:
    words = set(re.findall(r"[a-zA-Z]+", (text or "").lower()))
    id_hits = len(words & _ID_WORDS)
    en_hits = len(words & _EN_WORDS)
    return "id" if id_hits > en_hits else "en"


@dataclass
class DemoReply:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"


def _blocks(text: str, marker: str) -> str:
    """Return the text between ``marker`` and the next blank-line-separated block."""
    idx = text.find(marker)
    if idx == -1:
        return ""
    rest = text[idx + len(marker) :]
    stops = [
        pos
        for pos in (rest.find("\n\n###"), rest.find("\n\n---"), rest.find("\n\nMEMORY CONTEXT"))
        if pos != -1
    ]
    stop = min(stops) if stops else -1
    return rest if stop == -1 else rest[:stop]


def _state_lines(system: str) -> list[str]:
    block = _blocks(system, "LIVE STATE (authoritative")
    return [ln.strip() for ln in block.splitlines() if ln.strip().startswith(("-", "*"))]


def _context_block(system: str) -> str:
    return _blocks(system, "MEMORY CONTEXT").strip()


def _bulletize(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(f"- {ln.lstrip('- ').strip()}" for ln in lines[:5])


def _short(text: str, n: int = 160) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


class DemoModel:
    """Rule-based composer over the prompt's live state. Deterministic."""

    provider = "demo"
    model = MODEL_ID

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]] | None = None,
        purpose: str = "chat",
    ) -> DemoReply:
        system = "\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system"
        )
        user_msgs = [m for m in messages if m.get("role") == "user"]
        last_user = str(user_msgs[-1].get("content") or "") if user_msgs else ""
        tool_msgs = [m for m in messages if m.get("role") == "tool"]

        if tool_msgs:
            return DemoReply(self._after_tool(tool_msgs[-1], last_user))

        if tool_schemas and self._wants_search(last_user) and not self._already_searched(messages):
            query = self._search_query(last_user)
            return DemoReply(
                content="",
                tool_calls=[
                    {
                        "id": "call_demo_search",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": json.dumps({"query": query, "max_results": 3}),
                        },
                    }
                ],
                finish_reason="tool_calls",
            )

        return DemoReply(self._answer(system, last_user))

    # ------------------------------------------------------------------ shapes

    def _answer(self, system: str, question: str) -> str:
        lang = detect_language(question)
        q = question.lower()
        state = _state_lines(system)
        context = _context_block(system)

        if any(h in q for h in _STATUS_HINTS) and state:
            head = (
                "From the ledger — result state and delivery state are separate:"
                if lang == "en"
                else "Dari ledger — status hasil dan status pengiriman terpisah:"
            )
            bullets = []
            extras = []
            for line in state:
                body = line.lstrip("- ").strip()
                if "[" in body and "schedule" in body and "last run:" in body:
                    title = body.split(" [", 1)[0]
                    lifecycle = re.search(r"\[(active|paused|retired)\]", body)
                    last = re.search(r"last run: (\w+)", body)
                    version = re.search(r"instruction v(\d+)", body)
                    delivered = "not delivered" not in body and (
                        "delivered)" in body or "; delivered" in body
                    )
                    error = re.search(r"error=([^)]+?)(?:\)|$)", body)
                    state_word = last.group(1) if last else "no run"
                    bits = [
                        f"**{title}**",
                        state_word,
                        "delivered" if delivered else "not delivered",
                    ]
                    if version:
                        bits.append(f"instruction v{version.group(1)}")
                    if lifecycle and lifecycle.group(1) != "active":
                        bits.append(lifecycle.group(1))
                    suffix = (
                        f" _(error: {_short(error.group(1), 70)})_"
                        if error and not delivered
                        else ""
                    )
                    bullets.append("- " + " · ".join(bits) + suffix)
                elif "approval inbox" in body or "inference today" in body:
                    extras.append(body)
            if not bullets:
                return head + "\n\n" + "\n".join(state)
            tail = (
                "\n\nThe first two are the decision points: the failed delivery kept its verified "
                "result, and the paused review did not silently re-run. Open a commitment to inspect "
                "the evidence and the exact instruction version used."
                if lang == "en"
                else "\n\nDua hal pertama butuh keputusan: pengiriman yang gagal tetap menyimpan hasil "
                "terverifikasi, dan review yang di-pause tidak berjalan diam-diam. Buka komitmen untuk "
                "memeriksa bukti dan versi instruksi yang dipakai."
            )
            extra_text = ("\n\n" + " · ".join(extras)) if extras else ""
            return head + "\n\n" + "\n".join(bullets) + extra_text + tail

        if any(h in q for h in _MEMORY_HINTS):
            if context:
                head = (
                    "This comes from the memory I can actually read, with the source named:"
                    if lang == "en"
                    else "Ini berasal dari memori yang benar-benar bisa saya baca, dengan sumbernya:"
                )
                body = _bulletize(context)
                note = (
                    "\n\nMemory is only written through the approval inbox — chat itself is read-only."
                    if lang == "en"
                    else "\n\nMemori hanya ditulis lewat approval inbox — percakapan sendiri bersifat baca-saja."
                )
                return head + "\n\n" + body + note
            return (
                "I don't have a memory page that answers that, and I won't invent one. "
                "Tell me and I can propose it for the inbox."
                if lang == "en"
                else "Tidak ada halaman memori yang menjawab itu, dan saya tidak akan mengarang. "
                "Beri tahu saya, nanti saya usulkan ke inbox."
            )

        if any(h in q for h in ("hi", "hello", "halo", "hey")) and len(q) < 40:
            return (
                "Ready. I can summarize today's commitments, search the web, or look up memory. "
                "Everything I do is written to the audit log."
                if lang == "en"
                else "Siap. Saya bisa merangkum komitmen hari ini, mencari di web, atau membuka memori. "
                "Semua tindakan tercatat di audit log."
            )

        # General answer grounded in the retrieved memory (still no invented facts).
        opening = (
            "Short answer from the context I have:"
            if lang == "en"
            else "Jawaban singkat dari konteks yang saya punya:"
        )
        points: list[str] = []
        if context:
            first = [ln.strip() for ln in context.splitlines() if ln.strip()][:3]
            points.extend(_short(ln, 180) for ln in first)
        if state:
            points.extend(state[:2])
        if not points:
            points = [
                "I don't have enough context saved for that yet."
                if lang == "en"
                else "Konteks tersimpan untuk itu belum cukup."
            ]
        closing = (
            "\n\nWant me to turn this into a recurring commitment? That needs an explicit "
            "instruction version and your approval, not a side effect of chat."
            if lang == "en"
            else "\n\nMau saya jadikan komitmen berulang? Itu butuh versi instruksi eksplisit "
            "dan persetujuanmu — bukan efek samping percakapan."
        )
        return opening + "\n\n" + "\n".join(f"- {p}" for p in points) + closing

    def _after_tool(self, tool_msg: dict[str, Any], question: str) -> str:
        lang = detect_language(question)
        raw = str(tool_msg.get("content") or "")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"raw": raw}
        results = payload.get("results") or []
        if not results:
            reason = payload.get("error") or payload.get("note") or "no results returned"
            return (
                f"The web search tool returned no usable results ({reason}). "
                "I won't fill the gap with invented sources."
                if lang == "en"
                else f"Tool pencarian tidak mengembalikan hasil yang bisa dipakai ({reason}). "
                "Saya tidak akan mengisi kekosongan dengan sumber karangan."
            )
        lane = payload.get("lane", "live")
        head = (
            f"Found {len(results)} source(s) via Tavily ({lane}). What they actually say:"
            if lang == "en"
            else f"Menemukan {len(results)} sumber via Tavily ({lane}). Isinya:"
        )
        lines = []
        for item in results[:3]:
            title = _short(str(item.get("title") or "Untitled"), 90)
            snippet = _short(str(item.get("content") or item.get("snippet") or ""), 220)
            url = item.get("url") or ""
            lines.append(f"- **{title}** — {snippet}" + (f" ({url})" if url else ""))
        tail = (
            "\n\nI can save this as a note, but that needs your approval in the inbox."
            if lang == "en"
            else "\n\nSaya bisa menyimpannya sebagai catatan, tapi itu butuh persetujuanmu di inbox."
        )
        return head + "\n\n" + "\n".join(lines) + tail

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _wants_search(text: str) -> bool:
        q = text.lower()
        return any(h in q for h in _TOOL_HINTS)

    @staticmethod
    def _already_searched(messages: list[dict[str, Any]]) -> bool:
        return any(m.get("role") == "assistant" and m.get("tool_calls") for m in messages)

    @staticmethod
    def _search_query(text: str) -> str:
        cleaned = re.sub(
            r"(?i)^(please\s+)?(can you\s+)?(search|look up|cari|telusuri|riset)\s*",
            "",
            text.strip(),
        )
        cleaned = re.sub(r"(?i)\b(and|then|please|for me|untuk saya)\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")
        return (cleaned or text.strip())[:180]

    # ------------------------------------------- OpenAI-shaped completion API

    def completion(
        self,
        *,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        purpose: str = "chat",
    ) -> Any:
        """``complete()`` compatibility: digest + consolidation call sites."""
        system = "\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system"
        )
        user = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "user")
        if "Fakta aktivitas repo (JSON):" in user:
            content = self._digest(user, max_tokens=max_tokens)
        elif "morning brief" in system.lower() and "Facts (JSON):" in user:
            content = self._morning_brief(user)
        elif "Summarize research sources" in system and "Sources (JSON):" in user:
            content = self._research(user)
        elif "JSON" in system and "proposal" in system.lower():
            content = self._consolidation(system, user)
        else:
            content = self._answer(system, user)
        n_prompt = max(1, (len(system) + len(user)) // 4)
        n_completion = max(1, len(content) // 4)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, tool_calls=None), finish_reason="stop"
                )
            ],
            usage=SimpleNamespace(prompt_tokens=n_prompt, completion_tokens=n_completion),
        )

    @staticmethod
    def _digest(user: str, *, max_tokens: int | None) -> str:
        facts: dict[str, Any] = {}
        try:
            facts = json.loads(user.split("Fakta aktivitas repo (JSON):", 1)[1].strip())
        except (IndexError, ValueError):
            pass
        commits = facts.get("commits") or []
        files = facts.get("files_touched") or []
        working = facts.get("working_tree") or []
        done = _short(commits[0], 150) if commits else "No commits in the window"
        if len(commits) > 1:
            done += f"; plus {len(commits) - 1} more commit(s)"
        pending = (
            f"{len(working)} uncommitted change(s), including {_short(working[0], 80)}"
            if working
            else "Working tree is clean"
        )
        priorities = (
            "Ship the demo dashboard, record the 3-minute walkthrough, submit on Devpost"
            if not files
            else f"Review {_short(files[0], 60)}, then finish verification and submit"
        )
        return f"- Selesai: {done}.\n- Tertunda: {pending}.\n- Prioritas: {priorities}."

    @staticmethod
    def _morning_brief(user: str) -> str:
        facts: dict[str, Any] = {}
        try:
            facts = json.loads(user.split("Facts (JSON):", 1)[1].strip())
        except (IndexError, ValueError):
            pass
        status_lines = facts.get("ledger_status") or []
        problem = next((line for line in status_lines if "failed" in line.lower()), None)
        if problem:
            status = _short(problem, 170)
        else:
            status = "All active commitments have a verified last result; nothing needs a retry."
        commits = facts.get("commits") or []
        done = _short(commits[0], 140) if commits else "No commits in the scan window"
        working = facts.get("working_tree") or []
        pending = (
            f"{len(working)} uncommitted change(s), starting with {_short(working[0], 70)}"
            if working
            else "Working tree clean; the open item is the AgriSens dataset reply"
        )
        return (
            f"- Status: {status}\n"
            f"- Selesai: {done}.\n"
            f"- Tertunda: {pending}.\n"
            "- Prioritas: review today's approval inbox, then record the demo walkthrough."
        )

    @staticmethod
    def _research(user: str) -> str:
        payload: dict[str, Any] = {}
        try:
            raw = user.split("Sources (JSON):", 1)[1].strip()
            payload = json.loads(raw)
        except (IndexError, ValueError):
            payload = {}
        sources = payload if isinstance(payload, list) else payload.get("results") or []
        lines = []
        for item in sources[:3]:
            title = _short(str(item.get("title") or "Source"), 70)
            snippet = _short(str(item.get("content") or ""), 150)
            lines.append(f"- **{title}** — {snippet} (method and limitation need the full text)")
        if not lines:
            return "- No usable sources were returned, so there is no finding to report."
        return "\n".join(lines)

    @staticmethod
    def _consolidation(system: str, user: str) -> str:
        # The deterministic extractor in mitra.consolidation owns this path; the
        # model-shaped result keeps callers honest when the demo model is wired.
        return json.dumps({"facts": [], "note": "demo model: extractor handles this path"})
