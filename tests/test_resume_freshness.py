"""Unit tests for src/jobomatic/presence/resume_freshness.py — the mtime-based resume
freshness check shared by the Jobgether and Indeed/ZipRecruiter profile-update
generators. Always points at a tmp_path root, never the real repo, since the
real resume DOCX lives in a gitignored outputs/ folder anyway."""

from __future__ import annotations

import os
import time
from pathlib import Path

from jobomatic.presence.resume_freshness import resume_freshness_lines


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_missing_resume_reports_not_found(tmp_path: Path) -> None:
    lines = resume_freshness_lines(tmp_path)
    assert any("not found" in line for line in lines)
    assert any("fullstack_net_profile_resume" in line for line in lines)


def test_fresh_resume_reports_current(tmp_path: Path) -> None:
    resume_path = tmp_path / "outputs" / "templates" / "resume.docx"
    _write(tmp_path / "project-2-profile-learning-hub" / "identity.yaml")
    _write(tmp_path / "project-2-profile-learning-hub" / "roles.yaml")
    _write(tmp_path / "project-2-profile-learning-hub" / "skills.yaml")
    # Resume written after the sources — filesystem mtime resolution can be
    # coarse, so nudge sources' mtimes into the past explicitly rather than
    # relying on write ordering alone.
    past = time.time() - 100
    for name in ("identity.yaml", "roles.yaml", "skills.yaml"):
        p = tmp_path / "project-2-profile-learning-hub" / name
        os.utime(p, (past, past))
    _write(resume_path)

    lines = resume_freshness_lines(tmp_path)
    assert any("current" in line for line in lines)
    assert not any("STALE" in line for line in lines)


def test_stale_resume_reports_stale_sources(tmp_path: Path) -> None:
    resume_path = tmp_path / "outputs" / "templates" / "resume.docx"
    _write(resume_path)
    past = time.time() - 100
    os.utime(resume_path, (past, past))

    _write(tmp_path / "project-2-profile-learning-hub" / "identity.yaml")
    _write(tmp_path / "project-2-profile-learning-hub" / "roles.yaml")
    _write(tmp_path / "project-2-profile-learning-hub" / "skills.yaml")

    lines = resume_freshness_lines(tmp_path)
    assert any("STALE" in line for line in lines)
    assert any("identity.yaml" in line for line in lines)
    assert any("roles.yaml" in line for line in lines)
    assert any("skills.yaml" in line for line in lines)


def test_missing_source_files_are_skipped_not_fatal(tmp_path: Path) -> None:
    resume_path = tmp_path / "outputs" / "templates" / "resume.docx"
    _write(resume_path)
    # No project-2-profile-learning-hub directory at all.
    lines = resume_freshness_lines(tmp_path)
    assert any("current" in line for line in lines)


def test_resume_is_found_by_glob_whatever_the_candidates_name(tmp_path: Path) -> None:
    """The file name starts with the candidate's name (read from the profile), so the
    check matches on the suffix instead of a fixed name."""
    _write(tmp_path / "outputs" / "templates" / "resume-2026.docx")
    lines = resume_freshness_lines(tmp_path)
    assert not any("not found" in line for line in lines)
