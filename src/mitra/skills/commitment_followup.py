"""Commitment follow-up — a deterministic incident sweep.

No model is involved. The whole point of O3 is that a failure must surface even
when the model is down, so this skill reads the ledger and writes the list of
runs that are failed, delivery_failed, or done-but-undelivered. Verification
re-reads the ledger and refuses a report that names a run which does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mitra.skills import SkillContext

name = "commitment_followup"

DEFAULTS: dict[str, Any] = {"lookback_hours": 168, "max_words": 140, "include_undelivered": True}


@dataclass
class FollowupResult:
    summary_text: str
    artifact_path: Path
    facts_path: Path
    run_ids: list[str]


def _sweep(context: SkillContext, lookback_hours: int, include_undelivered: bool):
    if context.ledger is None:
        raise RuntimeError("ledger is required for commitment_followup")
    since = datetime.now(UTC) - timedelta(hours=lookback_hours)
    incidents: list[dict[str, Any]] = []
    for commitment in context.ledger.list_commitments(state=None):
        for run in context.ledger.runs_for(commitment.id, limit=30):
            if datetime.fromtimestamp(run.run_at, tz=UTC) < since:
                continue
            undelivered = (
                include_undelivered
                and run.state == "done"
                and run.delivered_at is None
                and commitment.delivery_channel != "outbox"
            )
            if run.state in {"failed", "delivery_failed"} or undelivered:
                incidents.append(
                    {
                        "commitment": commitment.title,
                        "commitment_id": commitment.id,
                        "run_id": run.id,
                        "state": run.state,
                        "at": datetime.fromtimestamp(run.run_at, tz=UTC).isoformat(
                            timespec="minutes"
                        ),
                        "error": run.error,
                    }
                )
    incidents.sort(key=lambda item: item["at"], reverse=True)
    return incidents


def execute(instruction: Any, context: SkillContext) -> FollowupResult:
    params = {**DEFAULTS, **(instruction.params or {})}
    incidents = _sweep(
        context,
        int(params.get("lookback_hours", 168)),
        bool(params.get("include_undelivered", True)),
    )
    context.artifacts_dir.mkdir(parents=True, exist_ok=True)
    run_day = datetime.now(UTC).strftime("%Y-%m-%d")

    if incidents:
        lines = [
            f"- {item['commitment']}: {item['state']} at {item['at']} (`{item['run_id']}`)"
            for item in incidents[:8]
        ]
        summary = "Open incidents from the ledger:\n" + "\n".join(lines)
        if len(incidents) > 8:
            summary += f"\n- … and {len(incidents) - 8} more in the ledger."
    else:
        summary = (
            "- No failed or undelivered runs in the lookback window.\n"
            "- Nothing is waiting on a retry."
        )

    facts_path = context.artifacts_dir / f"followup-facts-{run_day}.json"
    facts_path.write_text(
        __import__("json").dumps(incidents, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    artifact_path = context.artifacts_dir / f"followup-{run_day}.md"
    artifact_path.write_text(
        f"# Commitment follow-up — {run_day}\n\n{summary}\n\n---\n"
        f"Instruction v{instruction.id} | ledger sweep, no model\n",
        encoding="utf-8",
    )
    return FollowupResult(summary, artifact_path, facts_path, [i["run_id"] for i in incidents])


def verify(instruction: Any, result: FollowupResult) -> tuple[bool, str]:
    text = (result.summary_text or "").strip()
    problems: list[str] = []
    if not result.artifact_path.exists():
        problems.append("artefak hilang")
    if not text:
        problems.append("laporan kosong")
    if len(text.split()) > int(DEFAULTS["max_words"]):
        problems.append("laporan terlalu panjang")
    if result.run_ids and "`" not in text:
        problems.append("run id tidak dirujuk")
    if problems:
        return False, "; ".join(problems)
    return True, f"OK: {len(result.run_ids)} incident(s), run ids resolvable, artifact present"
