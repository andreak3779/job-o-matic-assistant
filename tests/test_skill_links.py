"""``.claude/skills`` is only a layer of links for Claude Code over ``skills/`` (ADR 0031).

``skills/`` is the one source; the MCP server and the presence generators read it directly. These
tests keep the links honest from both sides: every tracked link points at the skill of the same
name, and every skill is either linked or named here as deliberately not offered to Claude Code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
LINKS = ROOT / ".claude" / "skills"

# Skills that Claude Code is deliberately not offered (skills/README.md says why). A new skill
# with no link must be added here on purpose; a skill listed here that gains a link must leave.
NOT_LINKED = {
    "update_job_board_profiles",
    "update_jobgether_profile",
    "update_pluralsight_profile",
}


def _tracked_links() -> list[str]:
    """Names of the tracked entries in ``.claude/skills``. Untracked ones (the author's local
    link to a skill that lives in the private vault) are not the repository's business."""
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(
        [git, "ls-files", "-z", "--", ".claude/skills"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    return sorted(Path(name).name for name in out.split("\0") if name)


def _skill_folders() -> set[str]:
    return {p.parent.name for p in SKILLS.glob("*/SKILL.md")}


def test_every_tracked_link_points_at_the_skill_of_the_same_name() -> None:
    problems = []
    for name in _tracked_links():
        link = LINKS / name
        if not link.is_symlink():
            problems.append(f"{name}: is not a symlink (a copy that lost its links?)")
        elif os.readlink(link) != f"../../skills/{name}":
            problems.append(f"{name}: points at {os.readlink(link)}")
        elif not (SKILLS / name / "SKILL.md").is_file():
            problems.append(f"{name}: skills/{name}/SKILL.md does not exist")
    assert not problems, "\n".join(problems)


def test_every_skill_is_linked_or_named_as_not_linked() -> None:
    unlinked = _skill_folders() - set(_tracked_links())
    assert unlinked == NOT_LINKED, (
        f"skills with no link and no entry in NOT_LINKED: {sorted(unlinked - NOT_LINKED)}; "
        f"entries in NOT_LINKED that are linked or gone: {sorted(NOT_LINKED - unlinked)}"
    )


def test_a_link_has_no_skill_folder_missing() -> None:
    assert set(_tracked_links()) <= _skill_folders()
