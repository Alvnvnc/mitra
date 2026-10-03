"""Daily project digest — the one complete flow of the vertical slice.

Pipeline (deliberately boring and inspectable):

    facts (deterministic git scan)  ->  summary (Nemotron chat)
    ->  artifacts (files on disk)   ->  verify (against the instruction version)

The model writes prose. The code decides whether the result is acceptable,
using parameters taken from the *instruction version in force* (max_words, ...).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mitra.skills import SkillContext

name = "daily_digest"

DEFAULT_PARAMS: dict[str, Any] = {
    "max_words": 150,
    "since_hours": 72,
    "max_commits": 30,
}


@dataclass
class DigestResult:
    summary_text: str
    artifact_path: Path
    facts_path: Path
    extra: dict[str, Any] = field(default_factory=dict)


def _git(repo_root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"__git_error__:{type(exc).__name__}"
    if proc.returncode != 0:
        return f"__git_error__:{proc.stderr.strip()[:200]}"
    return proc.stdout.strip()


def gather_facts(repo_root: Path, *, since_hours: int, max_commits: int) -> dict[str, Any]:
    """Deterministic snapshot of recent activity — the only source the model gets."""
    facts: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "repo": str(repo_root),
        "since_hours": since_hours,
    }
    if shutil.which("git") is None:
        facts["error"] = "git not available"
        return facts

    log = _git(
        repo_root,
        "log",
        f"--since={since_hours} hours ago",
        f"-n{max_commits}",
        "--date=format:%Y-%m-%d %H:%M",
        "--pretty=format:%h | %ad | %s",
    )
    commits = [line for line in log.splitlines() if line and not line.startswith("__git_error__")]
    facts["commits"] = commits

    names = _git(
        repo_root,
        "log",
        f"--since={since_hours} hours ago",
        f"-n{max_commits}",
        "--name-only",
        "--pretty=format:",
    )
    files = sorted({line.strip() for line in names.splitlines() if line.strip()})
    facts["files_touched"] = files[:25]

    status = _git(repo_root, "status", "--short")
    facts["working_tree"] = [
        line for line in status.splitlines() if line and not line.startswith("__git_error__")
    ][:25]

    if not commits:
        facts["note"] = (
            f"Tidak ada commit dalam {since_hours} jam terakhir — katakan itu apa adanya."
        )
    return facts


def _build_messages(facts: dict[str, Any], max_words: int) -> list[dict[str, str]]:
    system = (
        "Kamu adalah Mitra, asisten proyek pribadi. Tulis ringkasan progres proyek "
        "dalam Bahasa Indonesia. ATURAN FORMAT (wajib): setiap baris konten adalah "
        "bullet yang diawali '- '; minimal 3 bullet — satu '- Selesai: ...', satu "
        "'- Tertunda: ...', dan satu '- Prioritas: ...' untuk 3 langkah berikutnya. "
        f"Maksimal {max_words} kata total. Hanya berdasarkan fakta yang diberikan — "
        "jangan mengarang. Tanpa salam pembuka atau penutup."
    )
    user = "Fakta aktivitas repo (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def execute(instruction: Any, context: SkillContext) -> DigestResult:
    """Run the digest for one instruction version. May raise; the runner records it."""
    params = {**DEFAULT_PARAMS, **(instruction.params or {})}
    max_words = int(params.get("max_words", 150))
    since_hours = int(params.get("since_hours", 72))
    max_commits = int(params.get("max_commits", 30))

    context.artifacts_dir.mkdir(parents=True, exist_ok=True)
    facts = gather_facts(context.repo_root, since_hours=since_hours, max_commits=max_commits)

    run_day = datetime.now(UTC).strftime("%Y-%m-%d")
    facts_path = context.artifacts_dir / f"facts-{run_day}.json"
    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

    if context.router is None:
        raise RuntimeError("no model router available for daily_digest")
    completion = context.router.complete(
        purpose="chat",
        messages=_build_messages(facts, max_words),
        temperature=0.2,
        max_tokens=800,
        # Nemotron on Token Factory emits a separate reasoning field by default
        # (finish_reason "length" eats the budget before the answer). Disabling
        # thinking keeps routine digests clean and cheap — verified 2026-10-03.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    summary = (completion.choices[0].message.content or "").strip()
    if not summary:
        raise RuntimeError("model returned an empty summary")

    artifact_path = context.artifacts_dir / f"digest-{run_day}.md"
    artifact_path.write_text(
        f"# Ringkasan proyek — {run_day} (UTC)\n\n{summary}\n\n"
        f"---\nSumber fakta: {facts_path.name} | instruksi v{instruction.id}\n",
        encoding="utf-8",
    )
    return DigestResult(summary_text=summary, artifact_path=artifact_path, facts_path=facts_path)


def verify(instruction: Any, result: DigestResult) -> tuple[bool, str]:
    """Deterministic check of the result against the instruction in force."""
    params = {**DEFAULT_PARAMS, **(instruction.params or {})}
    max_words = int(params.get("max_words", 150))

    problems: list[str] = []
    text = (result.summary_text or "").strip()
    words = len(text.split())
    bullets = [line for line in text.splitlines() if line.strip().startswith(("-", "•", "*"))]

    if not text:
        problems.append("ringkasan kosong")
    if not result.artifact_path.exists():
        problems.append(f"artefak hilang: {result.artifact_path}")
    if words > max_words:
        problems.append(f"{words} kata > batas {max_words}")
    if len(bullets) < 3:
        problems.append(f"hanya {len(bullets)} baris bullet (<3)")

    if problems:
        return False, "; ".join(problems)
    return True, f"OK: {words} kata, {len(bullets)} bullet (batas {max_words})"