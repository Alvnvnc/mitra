"""Unit tests for the W2 memory core: self-model, messages, retrieval (no network)."""

from __future__ import annotations

import pytest

from mitra.ledger import Ledger
from mitra.memory import DEFAULT_PAGES, SelfModel, build_context


def _setup(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    selfmodel = SelfModel(tmp_path / "self_model")
    return ledger, selfmodel


# ------------------------------------------------------------- self-model

def test_selfmodel_roundtrip(tmp_path):
    selfmodel = SelfModel(tmp_path / "sm")
    selfmodel.write("projects.md", "# Proyek\n\n- Mitra: hackathon", frontmatter={"title": "Projects"})

    page = selfmodel.read("projects.md")
    assert page.frontmatter["title"] == "Projects"
    assert "updated" in page.frontmatter  # auto-stamped
    assert "Mitra: hackathon" in page.body


def test_selfmodel_rejects_bad_names(tmp_path):
    selfmodel = SelfModel(tmp_path / "sm")
    for bad in ("../secrets.md", "a/b.md", "Notes.MD", "x.txt", "s p a c e.md"):
        with pytest.raises(ValueError):
            selfmodel.read(bad)


def test_selfmodel_ensure_defaults_is_idempotent(tmp_path):
    selfmodel = SelfModel(tmp_path / "sm")
    created = selfmodel.ensure_defaults()
    assert sorted(created) == sorted(DEFAULT_PAGES)
    assert selfmodel.ensure_defaults() == []  # second call: no-op
    assert all(selfmodel.exists(name) for name in DEFAULT_PAGES)


def test_selfmodel_overwrite_is_complete(tmp_path):
    selfmodel = SelfModel(tmp_path / "sm")
    selfmodel.write("priorities.md", "isi lama")
    selfmodel.write("priorities.md", "isi baru")
    assert selfmodel.read("priorities.md").body.strip() == "isi baru"
    # no stray tmp files left behind
    assert not any(p.name.endswith(".tmp") for p in selfmodel.root.iterdir())


# ------------------------------------------------------------- messages

def test_messages_log_and_session_filter(tmp_path):
    ledger, _ = _setup(tmp_path)
    ledger.log_message("s1", "user", "ingatkan menyiram tanaman besok")
    ledger.log_message("s1", "assistant", "baik, dicatat")
    ledger.log_message("s2", "user", "bagaimana progres proyek mitra hari ini?")

    s1 = ledger.messages("s1", limit=10)
    assert len(s1) == 2
    assert all(m.session_id == "s1" for m in s1)


def test_messages_fts_search(tmp_path):
    ledger, _ = _setup(tmp_path)
    ledger.log_message("s1", "user", "ingatkan menyiram tanaman besok")
    ledger.log_message("s1", "assistant", "baik, dicatat")
    target = ledger.log_message("s2", "user", "bagaimana progres proyek mitra hari ini?")

    hits = ledger.search_messages("proyek mitra")
    assert [m.id for m in hits] == [target]

    assert ledger.search_messages("") == []
    assert ledger.search_messages("kata-yang-tidak-ada") == []


# ------------------------------------------------------------- retrieval

def test_build_context_pins_priorities_and_finds_query_match(tmp_path):
    ledger, selfmodel = _setup(tmp_path)
    selfmodel.ensure_defaults()
    selfmodel.write("priorities.md", "- Fokus: validasi Mitra minggu ini")
    selfmodel.write("projects.md", "- Kebun sawit: riset citra satelit")
    ledger.log_message("s1", "user", "bagaimana riset citra satelit berjalan?")

    bundle = build_context(ledger, selfmodel, "citra satelit", budget_chars=2000)

    assert "priorities.md" in bundle.sources
    assert "projects.md" in bundle.sources
    assert any(source.startswith("message:") for source in bundle.sources)
    assert len(bundle.text) <= 2000
    assert bundle.truncated is False


def test_build_context_respects_budget_and_flags_truncation(tmp_path):
    ledger, selfmodel = _setup(tmp_path)
    selfmodel.write("priorities.md", "x" * 5000)

    bundle = build_context(ledger, selfmodel, "apa saja", budget_chars=300)

    assert len(bundle.text) <= 300
    assert bundle.truncated is True
    assert bundle.sources == ["priorities.md"]  # pinned first, cut to fit