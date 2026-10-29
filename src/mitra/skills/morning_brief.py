"""Morning brief — the ledger's status plus a factual project digest.

This is the skill the owner actually reads at 07:00. It combines two sources
that fail differently:

* the commitment ledger (authoritative for what ran, what has evidence and what
  failed to deliver);
* a deterministic scan of recent repository activity.

The model only turns those facts into prose; ``verify`` checks the shape
against the instruction version that was in force, never against the model's
own claims.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mitra.skills import SkillContext, as_sections
from mitra.skills.daily_digest import DEFAULT_PARAMS, gather_facts

name = "morning_brief"

DEFAULTS: dict[str, Any] = {**DEFAULT_PARAMS, "max_words": 180}


@dataclass
class BriefResult:
    summary_text: str
    artifact_path: Path
    facts_path: Path
    extra: dict[str, Any] = field(default_factory=dict)


def _status_lines(context: SkillContext) -> list[str]:
    if context.ledger is None:
        return ["Ledger unavailable in this context."]
    lines: list[str] = []
    for commitment in context.ledger.list_commitments():
        try:
            version = context.ledger.resolve_instruction(commitment.id)
            version_text = f"v{version.id}"
        except Exception:  # noqa: BLE001
            version_text = "no active instruction"
        latest = context.ledger.latest_run(commitment.id)
        if latest is None:
            lines.append(f"{commitment.title}: no runs yet (instruction {version_text})")
        else:
            lines.append(
                f"{commitment.title}: {latest.state} at "
                f"{datetime.fromtimestamp(latest.run_at, tz=UTC):%Y-%m-%d %H:%M} UTC "
                f"(instruction {version_text})"
            )
    pending = len(context.ledger.proposals(status="pending")) + len(
        context.ledger.approvals(status="pending")
    )
    lines.append(f"Approval inbox: {pending} item(s) waiting")
    usage = context.ledger.usage_summary(days=1)
    lines.append(f"Inference today: {usage['calls']} call(s), ${usage['cost_usd']:.4f}")
    return lines


def execute(instruction: Any, context: SkillContext) -> BriefResult:
    params = {**DEFAULTS, **(instruction.params or {})}
    max_words = int(params.get("max_words", 180))
    context.artifacts_dir.mkdir(parents=True, exist_ok=True)

    facts = gather_facts(
        context.repo_root,
        since_hours=int(params.get("since_hours", 72)),
        max_commits=int(params.get("max_commits", 30)),
    )
    status = _status_lines(context)
    facts["ledger_status"] = status

    run_day = datetime.now(UTC).strftime("%Y-%m-%d")
    facts_path = context.artifacts_dir / f"brief-facts-{run_day}.json"
    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

    if context.router is None:
        raise RuntimeError("no model router available for morning_brief")
    system = (
        "You are Mitra writing the owner's morning brief. Use ONLY the facts. Structure, "
        "exactly:\n- Status: <one sentence about the ledger state, including any failure>\n"
        "- Selesai: <what actually shipped>\n- Tertunda: <what is blocked or open>\n"
        "- Prioritas: <the single most useful next action>\n"
        f"Maximum {max_words} words. No greeting, no closing. If a run failed, say it plainly.\n"
        "The ledger_status list is authoritative for commitments. The repo_scan key "
        "describes the code checkout only: if it reports that it is unavailable, "
        "ignore it — never describe it as a commitment failure."
    )
    user = "Facts (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1)
    completion = context.router.complete(
        purpose="chat",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=700,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    summary = as_sections((completion.choices[0].message.content or "").strip())
    if not summary:
        raise RuntimeError("model returned an empty brief")

    artifact_path = context.artifacts_dir / f"morning-brief-{run_day}.md"
    artifact_path.write_text(
        f"# Morning brief — {run_day}\n\n{summary}\n\n---\n"
        f"Instruction v{instruction.id} | sources: {facts_path.name}\n",
        encoding="utf-8",
    )
    return BriefResult(summary, artifact_path, facts_path)


def verify(instruction: Any, result: BriefResult) -> tuple[bool, str]:
    params = {**DEFAULTS, **(instruction.params or {})}
    max_words = int(params.get("max_words", 180))
    text = (result.summary_text or "").strip()
    bullets = [line for line in text.splitlines() if line.strip().startswith(("-", "•", "*"))]
    words = len(text.split())
    problems: list[str] = []
    if not text:
        problems.append("brief kosong")
    if not result.artifact_path.exists():
        problems.append("artefak hilang")
    if words > max_words:
        problems.append(f"{words} kata > batas {max_words}")
    if len(bullets) < 4:
        problems.append(f"{len(bullets)} bullet (<4)")
    if "status:" not in text.lower():
        problems.append("bagian Status tidak ada")
    if problems:
        return False, "; ".join(problems)
    return True, f"OK: {words} kata, {len(bullets)} bullet, status line present"
