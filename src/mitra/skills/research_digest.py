"""Research digest — Tavily through the governed tool layer.

This is the skill that earns the "real runtime action" claim: it calls the live
web through ``ToolBox`` (egress allowlist, audit row), asks Nemotron to separate
method from limitation, and refuses to pass verification with fewer than two
sources carrying URLs.

Tavily results are *not* saved as memory by this skill; the artifact is evidence
for the run, and a note can be queued through the approval inbox separately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mitra.skills import SkillContext

name = "research_digest"

DEFAULTS: dict[str, Any] = {
    "max_words": 220,
    "min_sources": 2,
    "max_results": 3,
    "query": "Sentinel-2 nitrogen estimation oil palm",
}


@dataclass
class ResearchResult:
    summary_text: str
    artifact_path: Path
    facts_path: Path
    sources: list[dict[str, Any]]
    lane: str


def _query(params: dict[str, Any], instruction: Any) -> str:
    if params.get("query"):
        return str(params["query"])
    text = str(getattr(instruction, "content", "") or "").strip()
    return text[:200] or str(DEFAULTS["query"])


def execute(instruction: Any, context: SkillContext) -> ResearchResult:
    if context.tools is None:
        raise RuntimeError("research_digest needs the governed tool layer (web_search)")
    params = {**DEFAULTS, **(instruction.params or {})}
    query = _query(params, instruction)
    tool_result = context.tools.execute(
        "web_search", {"query": query, "max_results": int(params.get("max_results", 3))}
    )
    payload = tool_result.to_dict()
    sources = [s for s in payload.get("results") or [] if s.get("url")]
    lane = str(payload.get("lane") or "unavailable")
    if not sources:
        raise RuntimeError(
            f"web_search returned no usable sources ({payload.get('error') or payload.get('note')})"
        )

    context.artifacts_dir.mkdir(parents=True, exist_ok=True)
    run_day = datetime.now(UTC).strftime("%Y-%m-%d")
    facts_path = context.artifacts_dir / f"research-facts-{run_day}.json"
    facts_path.write_text(
        json.dumps(
            {"query": query, "lane": lane, "results": sources}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )

    if context.router is None:
        raise RuntimeError("no model router available for research_digest")
    system = (
        "You are Mitra. Summarize research sources for a researcher who hates hype. "
        "Output 2-4 bullets. Each bullet: finding, then method, then limitation. "
        "Name the source in parentheses. If the sources disagree, say so. "
        "Use only the supplied snippets and never invent a citation. "
        f"Maximum {int(params.get('max_words', 220))} words. No preamble."
    )
    completion = context.router.complete(
        purpose="reasoning" if len(sources) > 2 else "chat",
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Query: {query}\nSources (JSON):\n"
                + json.dumps(sources, ensure_ascii=False, indent=1),
            },
        ],
        temperature=0.2,
        max_tokens=900,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    summary = (completion.choices[0].message.content or "").strip()
    if not summary:
        raise RuntimeError("model returned an empty research digest")

    artifact_path = context.artifacts_dir / f"research-{run_day}.md"
    links = "\n".join(f"- [{s.get('title')}]({s.get('url')})" for s in sources)
    artifact_path.write_text(
        f"# Research digest — {query}\n\n{summary}\n\n## Sources ({lane})\n{links}\n\n---\n"
        f"Instruction v{instruction.id}\n",
        encoding="utf-8",
    )
    return ResearchResult(summary, artifact_path, facts_path, sources, lane)


def verify(instruction: Any, result: ResearchResult) -> tuple[bool, str]:
    params = {**DEFAULTS, **(instruction.params or {})}
    min_sources = int(params.get("min_sources", 2))
    max_words = int(params.get("max_words", 220))
    text = (result.summary_text or "").strip()
    words = len(text.split())
    problems: list[str] = []
    if not result.artifact_path.exists():
        problems.append("artefak hilang")
    if not text:
        problems.append("ringkasan kosong")
    if words > max_words:
        problems.append(f"{words} kata > batas {max_words}")
    if len(result.sources) < min_sources:
        problems.append(f"{len(result.sources)} sumber < minimum {min_sources}")
    if not all(s.get("url") for s in result.sources):
        problems.append("ada sumber tanpa URL")
    if problems:
        return False, "; ".join(problems)
    return True, f"OK: {words} kata, {len(result.sources)} sumber ber-URL ({result.lane})"
