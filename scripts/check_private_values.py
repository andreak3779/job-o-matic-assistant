#!/usr/bin/env python3
"""Fail if a private value is restated in any tracked file.

Two checks over every git-tracked text file, both run by the pre-commit hook:

* the salary minimums in the vault's ``private/search-constraints.json``;
* the personal identifiers in the vault's ``private/pii-terms.json`` (name, email, phone,
  employers, share-link IDs), except in the paths listed in ``scripts/pii-allowlist.txt``,
  which is the shrinking list of files still waiting for their scrub.

Either check is skipped, exit 0, when its vault file is absent or when there is no vault at all (CI,
a fresh clone, a contributor who has only the code).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jobomatic import paths
from jobomatic.fit.constraints import load_constraints
from jobomatic.privacy.private_values import find_leaks
from jobomatic.privacy.scan import find_pii, load_terms

_SKIP_SUFFIXES = (".pdf", ".html", ".docx", ".png", ".jpg", ".lock")
_SKIP_NAMES = {"package-lock.json", "requirements-lock.txt"}


ALLOWLIST = ROOT / "scripts" / "pii-allowlist.txt"


def _tracked_texts() -> dict[str, str]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    files: dict[str, str] = {}
    for name in tracked:
        path = ROOT / name
        if (
            not name
            or name.endswith(_SKIP_SUFFIXES)
            or path.name in _SKIP_NAMES
            or (name.startswith("private/") and ".example." in name)
            or not path.is_file()
        ):
            continue
        try:
            files[name] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return files


def _check_salary(files: dict[str, str]) -> int:
    try:
        constraints = load_constraints()
    except paths.VaultError:
        # A fresh clone, CI, or a contributor with only the code: nothing private to look for.
        print("check_private_values: no vault — salary check skipped")
        return 0
    except ValueError as exc:
        print(f"ERROR: private/search-constraints.json is invalid: {exc}", file=sys.stderr)
        return 1
    if constraints is None:
        print("check_private_values: no private/search-constraints.json — salary check skipped")
        return 0
    leaks = find_leaks(constraints, files)
    if leaks:
        print("A private salary minimum is written in tracked files:", file=sys.stderr)
        for leak in leaks:
            print(f"  {leak}", file=sys.stderr)
        print(
            "Remove it: read it from `python -m jobomatic constraints show` instead.",
            file=sys.stderr,
        )
        return 1
    return 0


def _check_pii(files: dict[str, str], *, refresh_allowlist: bool) -> int:
    try:
        terms_path = paths.private_dir() / "pii-terms.json"
    except paths.VaultError:
        print("check_private_values: no vault — identifier check skipped")
        return 0
    if not terms_path.is_file():
        print("check_private_values: no private/pii-terms.json — identifier check skipped")
        return 0
    try:
        terms = load_terms(terms_path)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if refresh_allowlist:
        offenders = sorted({f.split(":")[0] for f in find_pii(terms, files)})
        ALLOWLIST.write_text("\n".join(offenders) + ("\n" if offenders else ""), encoding="utf-8")
        print(f"check_private_values: allowlist rewritten ({len(offenders)} paths)")
        return 0
    allow = (
        {p for p in ALLOWLIST.read_text(encoding="utf-8").splitlines() if p.strip()}
        if ALLOWLIST.is_file()
        else set()
    )
    findings = find_pii(terms, files, allow)
    if findings:
        print("Personal identifiers are written in tracked files:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "Replace them with a fictional value or read them from the vault. Paths awaiting "
            "scrub are listed in scripts/pii-allowlist.txt.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        # A variable that was renamed (ADR 0030) raises the same error as a missing vault, which
        # both checks below treat as "nothing to check". Ask first, so a stale variable is an error.
        paths.reject_retired_variables()
    except paths.VaultError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    files = _tracked_texts()
    status = _check_salary(files)
    status |= _check_pii(files, refresh_allowlist="--refresh-allowlist" in argv)
    if status == 0:
        print(f"check_private_values: clean ({len(files)} tracked files scanned)")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
