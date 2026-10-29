"""Skill registry for Mitra.

A skill is a small, inspectable unit: an ``execute(instruction, context)`` that
produces artifacts, and a ``verify(instruction, result)`` that runs the
deterministic checks. The model writes prose; the code owns the rules.

Four skills ship: ``daily_digest`` (repo activity), ``morning_brief`` (ledger
state + digest), ``commitment_followup`` (failed and undelivered runs) and
``research_digest`` (governed web search + synthesis).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

# A section a skill's contract names explicitly. The evidence gate counts these,
# so a missing section still fails regardless of how the model formatted it.
SECTION_LABELS = (
    "status",
    "selesai",
    "tertunda",
    "prioritas",
    "priorities",
    "pending",
    "done",
    "blocked",
)

_MARKER = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+")
_LABEL = re.compile(
    r"^\s*(?:\*\*)?(?:" + "|".join(SECTION_LABELS) + r")\b",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^```.*$", re.MULTILINE)


def as_sections(text: str) -> str:
    """Normalise a model's prose into the bullet shape the gate counts.

    Live models drift between ``- Status: …`` and ``Status: …``. The gate is
    about structure — which sections exist and how long the text is — not about
    a leading dash, so only *labelled* lines get a marker. Unlabelled prose is
    left alone, which means a model that skips a section still fails: the gate
    counts real sections, not line breaks.
    """
    lines = _FENCE.sub("", text or "").splitlines()
    out: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        body = _MARKER.sub("", line)
        if _LABEL.match(body):
            out.append("- " + body.strip())
        else:
            out.append(line)
    return "\n".join(out)


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
