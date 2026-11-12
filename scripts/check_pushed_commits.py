#!/usr/bin/env python3
"""Fail if the commits being pushed add a personal identifier (ADR 0032).

Run by ``scripts/hooks/pre-push``, which gives it the lines git sends to a pre-push hook on stdin.
It reads what each pushed commit publishes (the lines it adds, its author and committer, its
message) and checks it against the vault's ``private/pii-terms.json``, case-insensitively and for
every term. In a finding for a commit, line 1 is the author, line 2 the committer and the rest the
message. It can also be run by hand on any
range before pushing::

    python scripts/check_pushed_commits.py --range origin/main..HEAD

Findings are ``path:line (category)`` or ``commit <sha>:line (category)``; the matching text is
never printed. Like the commit-time
scan, it does nothing, exit 0, when there is no vault or no terms file (CI, a fresh clone).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jobomatic import paths
from jobomatic.privacy.diff_audit import (
    COMMIT_FORMAT,
    AddedLine,
    PushedUpdate,
    added_lines,
    audit_added_lines,
    commit_texts,
    pushed_updates,
)
from jobomatic.privacy.scan import load_terms

ALLOWLIST = ROOT / "scripts" / "pii-allowlist.txt"
# Where a branch new to the remote started: the first of these that exists.
BASE_REFS = ("origin/main", "main")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def _has_commit(sha: str) -> bool:
    return _git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def revisions_for(update: PushedUpdate) -> list[str]:
    """What to give ``git log`` to list the commits this update would publish."""
    if update.remote_sha is not None and _has_commit(update.remote_sha):
        return [f"{update.remote_sha}..{update.local_sha}"]
    for base in BASE_REFS:
        merged = _git("merge-base", base, update.local_sha)
        if merged.returncode == 0 and merged.stdout.strip():
            return [f"{merged.stdout.strip()}..{update.local_sha}"]
    # Nothing to compare with: audit the commit's whole history, which is slower but cannot miss
    # a line.
    return [update.local_sha]


def _log(*args: str) -> str:
    result = _git("-c", "core.quotepath=false", "log", "--no-color", "--no-ext-diff", *args)
    if result.returncode != 0:
        raise RuntimeError(f"git log {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def audit_inputs(revisions: list[str]) -> list[AddedLine]:
    """Everything the commits publish: each commit's own added lines (not the net change, so a
    value added in one commit and removed in the next still counts), its author, committer and
    message. A merge is compared with its first parent."""
    patches = _log("--format=", "-p", "-m", "--first-parent", "--unified=0", *revisions)
    texts = _log(f"--format={COMMIT_FORMAT}", *revisions)
    return [*added_lines(patches), *commit_texts(texts)]


def _revisions(argv_range: str | None, stdin_lines: Iterable[str]) -> list[list[str]]:
    if argv_range:
        return [[argv_range]]
    return [revisions_for(update) for update in pushed_updates(stdin_lines)]


def main(argv: list[str] | None = None, stdin: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit the commits being pushed for personal identifiers."
    )
    parser.add_argument(
        "--range", help="audit this revision range instead of reading the push from stdin"
    )
    parser.add_argument(
        "remote", nargs="*", help="the remote's name and URL, passed by git; unused"
    )
    args = parser.parse_args(argv)

    try:
        # A variable that was renamed (ADR 0030) raises the same error as a missing vault. Ask first,
        # so that a stale variable is an error and not a quiet reason to skip the audit.
        paths.reject_retired_variables()
    except paths.VaultError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        terms_path = paths.private_dir() / "pii-terms.json"
    except paths.VaultError:
        print("check_pushed_commits: no vault, so the leak audit of the push is skipped")
        return 0
    if not terms_path.is_file():
        print("check_pushed_commits: no private/pii-terms.json, so the leak audit is skipped")
        return 0
    try:
        terms = load_terms(terms_path)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not args.range and stdin is None and sys.stdin.isatty():
        print("ERROR: give --range, or run this from the pre-push hook.", file=sys.stderr)
        return 1
    lines = (sys.stdin if stdin is None else stdin) if not args.range else ()
    try:
        ranges = _revisions(args.range, lines)
        added = [item for revisions in ranges for item in audit_inputs(revisions)]
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    allow = (
        {p for p in ALLOWLIST.read_text(encoding="utf-8").splitlines() if p.strip()}
        if ALLOWLIST.is_file()
        else set()
    )
    findings = audit_added_lines(terms, added, allow)
    if findings:
        print("Personal identifiers are in the commits being pushed:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "Remove them from the commits (amend or rebase) before pushing; the repository is "
            "public. Paths exempt from the check are listed in scripts/pii-allowlist.txt.",
            file=sys.stderr,
        )
        return 1
    print(f"check_pushed_commits: clean ({len(added)} lines in {len(ranges)} range(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
