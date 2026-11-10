"""Shared CLI helpers for project-1 generator scripts."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jobomatic.documents.service import DocumentError
from jobomatic.fit.terms import extract_skill_terms
from jobomatic.paths import VaultError
from jobomatic.profile.model import Profile
from jobomatic.profile.service import ProfileError


def story_mentions(text: str, term: str) -> bool:
    """True when a story's ``text`` names the skill ``term``, ignoring case and treating ``-``,
    ``/`` and spaces alike, so the posting's "CI/CD" finds a story tagged "ci-cd". A row such as
    "CI/CD with GitHub Actions" also counts when the story names any skill inside it."""

    def flat(value: str) -> str:
        return re.sub(r"[-/\s]+", " ", value.lower())

    haystack = flat(text)
    wanted = [term, *extract_skill_terms(term)]
    return any(flat(w) in haystack for w in wanted)


def require_path(path: Path, label: str = "File") -> Path:
    """Return ``path`` if it exists, otherwise raise FileNotFoundError."""
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def load_profile_or_none(root: Path | None = None) -> Profile | None:
    """Load the profile, printing a clean ERROR and returning ``None`` on failure.

    A missing or malformed profile is an ordinary, expected failure (a fresh clone has no vault;
    a hand edit can break a YAML file), not a bug, so every CLI script's ``main()`` handles it
    the same way: ``profile = load_profile_or_none(root); if profile is None: return 1``.
    """
    from jobomatic import bootstrap

    try:
        return bootstrap.load_profile(root)
    except (ProfileError, VaultError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None


def print_wrote(*paths: Path) -> None:
    """Print "Wrote <path>" for each output artifact, in order."""
    for p in paths:
        print(f"Wrote {p}")


def run_and_report(fn: Callable[..., tuple[Path, Path, Any]], *args: Any, **kwargs: Any) -> int:
    """Call a generator function that returns (out_path, sidecar_path, ...),
    catch ValueError as a clean ERROR + exit 1 (the one exception class core
    generator functions in this project use for expected validation
    failures — e.g. interview_prep's missing qa_cards fields, thank-you's
    missing discussion points), and print the standard "Wrote" lines on
    success. Extra tuple elements beyond (out_path, sidecar_path) are
    ignored.
    """
    try:
        result = fn(*args, **kwargs)
    except (ValueError, DocumentError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    out, sidecar = result[0], result[1]
    print_wrote(out, sidecar)
    return 0


def verify_pages(kind: str, path: Path) -> int:
    """Measure ``path`` with LibreOffice and refuse it if it breaks the page limit for ``kind``.

    Only called when the user asked for ``--check-pages``. Raises ``DocumentError`` (a missing
    LibreOffice is one too), so the file stays where it is and the command exits 1.
    """
    from jobomatic import bootstrap
    from jobomatic.documents import service

    pages = service.check_pages(kind, path, bootstrap.page_counter())
    print(f"Pages: {pages}")
    return pages
