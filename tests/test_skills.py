"""Skill shape normalisation — the gate must stay about structure, not dashes."""

from __future__ import annotations

from types import SimpleNamespace

from mitra.skills import as_sections, morning_brief


def test_labelled_prose_becomes_the_bullet_shape_the_gate_counts():
    """Live models write "Status: …"; the local model writes "- Status: …"."""
    text = "Status: one brief failed.\nSelesai: the follow-up shipped.\nTertunda: the scan.\nPrioritas: retry it."
    normalised = as_sections(text)
    bullets = [line for line in normalised.splitlines() if line.startswith("- ")]
    assert len(bullets) == 4
    assert bullets[0] == "- Status: one brief failed."


def test_a_missing_section_still_fails_the_gate():
    text = "Status: fine.\nSelesai: shipped.\nTertunda: nothing."
    normalised = as_sections(text)
    bullets = [line for line in normalised.splitlines() if line.startswith("- ")]
    assert len(bullets) == 3


def test_unlabelled_prose_does_not_become_bullets():
    """Otherwise a rambling paragraph would pass a four-bullet gate."""
    normalised = as_sections("Here is a paragraph.\nIt has two lines and no sections.")
    assert not any(line.startswith("- ") for line in normalised.splitlines())


def test_code_fences_are_dropped():
    normalised = as_sections("```markdown\nStatus: ok\n```\nSelesai: yes")
    assert "```" not in normalised


def test_morning_brief_gate_rejects_a_short_brief(tmp_path):
    artifact = tmp_path / "brief.md"
    artifact.write_text("# x\n", encoding="utf-8")
    result = morning_brief.BriefResult(
        summary_text="- Status: only one section",
        artifact_path=artifact,
        facts_path=tmp_path / "facts.json",
    )
    ok, detail = morning_brief.verify(SimpleNamespace(params={}, id=1), result)
    assert ok is False
    assert "bullet" in detail


def test_morning_brief_gate_accepts_a_normalised_four_section_brief(tmp_path):
    artifact = tmp_path / "brief.md"
    artifact.write_text("# x\n", encoding="utf-8")
    summary = as_sections(
        "Status: one run failed.\nSelesai: the follow-up shipped.\n"
        "Tertunda: the digest.\nPrioritas: retry the digest tomorrow."
    )
    result = morning_brief.BriefResult(
        summary_text=summary,
        artifact_path=artifact,
        facts_path=tmp_path / "facts.json",
    )
    ok, detail = morning_brief.verify(SimpleNamespace(params={}, id=2), result)
    assert ok is True, detail
