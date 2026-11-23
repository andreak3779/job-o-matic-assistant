"""Has the code on disk changed since this server process started?

A server started by Claude Desktop keeps running for days, and Python reads its code once, at
start. After the assistant is updated (a merge, a branch switch, a pull) the running process still
holds the old code, so it can reject a vault that the new code accepts: a profile field added in
the update shows up as "Extra inputs are not permitted". That error points at the vault, which is
fine. This module lets the server say what is really wrong: it needs a restart.

The fingerprint is the number of ``.py`` files under the package and the newest modification time
among them. Both change on a merge, a checkout of another branch, an edit or a deleted module.
Pure apart from reading file metadata; it never imports or reads the files.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]  # src/jobomatic

RESTART_MESSAGE = (
    "job-o-matic was updated on disk after this server started, so this server is still running "
    "the old code and would give wrong answers (for example, rejecting profile fields the new code "
    "accepts). Nothing was run. Fully quit Claude Desktop (not just the window) and open it "
    "again, then repeat the request."
)

Fingerprint = tuple[int, int]


def fingerprint(package: Path = PACKAGE) -> Fingerprint:
    """(number of .py files, newest modification time in ns) under ``package``."""
    count = newest = 0
    for path in package.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:  # removed while scanning: the count changes, which is the signal
            continue
        count += 1
        newest = max(newest, mtime)
    return count, newest


def is_stale(started_with: Fingerprint, package: Path = PACKAGE) -> bool:
    """True when the code on disk is not the code this process loaded."""
    return fingerprint(package) != started_with
