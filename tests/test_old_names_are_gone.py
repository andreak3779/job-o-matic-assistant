"""The names from before the rename do not come back (ADR 0030).

``claude-jobs`` (the command), ``CLAUDE_JOBS_*`` (the variables; the pattern is case-blind, so
it catches ``claude_jobs`` and ``CLAUDE_JOBS`` too), ``claude-projects`` (the old
checkout) and "project-1" (an old docstring) appear in a short list of places only: the ADRs and
two history documents, the one map that rejects the old variable names, the tests of that map, and
the MCP README note that tells a Desktop user what to rename.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

OLD_NAMES = re.compile(r"claude-jobs|claude_jobs|claude-projects|project-1", re.IGNORECASE)

# Prefixes (folders end in "/") and exact paths where an old name is allowed, and why.
ALLOWED = (
    "docs/adr/",  # ADRs are history and are not rewritten
    "docs/HOW_THIS_WAS_BUILT.md",  # the project's history
    "docs/Fit-Calibration-Plan.md",  # cites an ADR that lives in the old checkout
    "src/jobomatic/paths.py",  # RETIRED_VARIABLES: delete it before 1.0
    "src/jobomatic/interfaces/mcp/README.md",  # tells a Desktop user what to rename
    "tests/test_retired_variables.py",  # tests of RETIRED_VARIABLES
    "tests/test_check_private_values_script.py",  # strips both prefixes from the environment
    "tests/test_old_names_are_gone.py",  # this file
)


def _tracked_files() -> list[Path]:
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(
        [git, "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    return [ROOT / name for name in out.split("\0") if name]


def _text(path: Path) -> str | None:
    """The file's text, or ``None`` for a symlink, a folder or a binary file."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def test_old_names_appear_only_where_they_are_allowed() -> None:
    found: list[str] = []
    for path in _tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(ALLOWED):
            continue
        text = _text(path)
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if OLD_NAMES.search(line):
                found.append(f"{relative}:{number}: {line.strip()[:100]}")
    assert not found, "an old name is back:\n" + "\n".join(found)


def test_the_allowlist_has_no_dead_entries() -> None:
    tracked = {p.relative_to(ROOT).as_posix() for p in _tracked_files()}
    for entry in ALLOWED:
        assert any(name.startswith(entry) for name in tracked), f"{entry} is not tracked"
