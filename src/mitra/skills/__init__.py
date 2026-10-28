"""Skill registry for Mitra.

A skill is a small, inspectable unit: an ``execute(instruction, context)`` that
produces artifacts, and a ``verify(instruction, result)`` that runs the
deterministic checks. The model writes prose; the code owns the rules.

Four skills ship: ``daily_digest`` (repo activity), ``morning_brief`` (ledger
state + digest), ``commitment_followup`` (failed and undelivered runs) and
``research_digest`` (governed web search + synthesis).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class SkillContext:
    """Everything a skill may use at run time (no hidden state)."""

    router: Any  # ModelRouter | None (None means "no model available")
    repo_root: Path
    artifacts_dir: Path
    ledger: Any = None  # Ledger | None — read-only for status skills
    tools: Any = None  # ToolBox | None — governed egress only
    data_dir: Path | None = None


class Skill(Protocol):
    name: str

    def execute(self, instruction: Any, context: SkillContext) -> Any: ...

    def verify(self, instruction: Any, result: Any) -> tuple[bool, str]: ...


def get_skill(name: str) -> Skill:
    from mitra.skills import commitment_followup, daily_digest, morning_brief, research_digest

    registry: dict[str, Skill] = {
        "daily_digest": daily_digest,
        "morning_brief": morning_brief,
        "commitment_followup": commitment_followup,
        "research_digest": research_digest,
    }
    try:
        return registry[name]
    except KeyError as exc:
        raise KeyError(f"unknown skill {name!r}; known: {sorted(registry)}") from exc
