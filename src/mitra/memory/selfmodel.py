"""Self-model store: human-readable Markdown pages with YAML frontmatter.

The self-model is the semantic memory layer — what Mitra believes about the
user's world (people, projects, priorities, preferences, patterns). It is
plain Markdown so the user can read and edit it.

Write discipline (ARCHITECTURE §2): chat only *reads* this store. Writes come
from explicit user action or from consolidation proposals that were approved
in the inbox. All writes are atomic (tmp file + rename).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PAGES: tuple[str, ...] = (
    "people.md",
    "projects.md",
    "priorities.md",
    "preferences.md",
    "patterns.md",
)

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}\.md$")


@dataclass
class Page:
    name: str
    frontmatter: dict[str, Any]
    body: str


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            raw = text[4:end]
            body = text[end + 4 :].lstrip("\n")
            try:
                parsed = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                parsed = {}
            return (parsed if isinstance(parsed, dict) else {}), body
    return {}, text


class SelfModel:
    """A directory of Markdown pages; names are validated, writes are atomic."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not _NAME_RE.match(name):
            raise ValueError(
                f"invalid page name {name!r}: lowercase [a-z0-9_-], must end in .md"
            )
        return self.root / name

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def read(self, name: str) -> Page:
        path = self._path(name)
        if not path.exists():
            return Page(name=name, frontmatter={}, body="")
        frontmatter, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        return Page(name=name, frontmatter=frontmatter, body=body)

    def write(
        self, name: str, body: str, *, frontmatter: dict[str, Any] | None = None
    ) -> Path:
        path = self._path(name)
        metadata = dict(frontmatter or {})
        metadata.setdefault("updated", datetime.now(UTC).isoformat(timespec="seconds"))
        header = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
        text = (
            f"---\n{header}\n---\n\n{body.rstrip()}\n"
            if body.strip()
            else f"---\n{header}\n---\n"
        )
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)  # atomic on POSIX
        return path

    def pages(self) -> list[str]:
        return sorted(
            child.name
            for child in self.root.iterdir()
            if child.is_file() and _NAME_RE.match(child.name)
        )

    def snapshot(self) -> dict[str, Page]:
        return {name: self.read(name) for name in self.pages()}

    def ensure_defaults(self) -> list[str]:
        """Create missing default pages (empty body). Returns created names."""
        created: list[str] = []
        for name in DEFAULT_PAGES:
            if not self.exists(name):
                title = name.removesuffix(".md").replace("_", " ").title()
                self.write(name, "", frontmatter={"title": title})
                created.append(name)
        return created