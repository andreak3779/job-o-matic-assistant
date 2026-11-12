"""Shared CLI helpers for project-1 generator scripts."""

from __future__ import annotations

import argparse
import re
import sys
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jobomatic import gate
from jobomatic.applications import outputs
from jobomatic.documents.service import DocumentError
from jobomatic.fit.engine import FitResult
from jobomatic.fit.terms import extract_skill_terms
from jobomatic.paths import VaultError, not_found_message
from jobomatic.profile.model import Profile
from jobomatic.profile.service import ProfileError
from jobomatic.results import CommandResult, Level, Message, console, guarded, ok


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
        raise FileNotFoundError(not_found_message(path, label))
    return path


def load_profile_or_none() -> Profile | None:
    """Load the profile, printing a clean ERROR and returning ``None`` on failure.

    A missing or malformed profile is an ordinary, expected failure (a fresh clone has no vault;
    a hand edit can break a YAML file), not a bug, so every CLI script's ``main()`` handles it
    the same way: ``profile = load_profile_or_none(); if profile is None: return 1``.
    """
    from jobomatic import bootstrap

    try:
        return bootstrap.load_profile()
    except (ProfileError, VaultError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None


# The user's confirmations past a refusal (ADR 0003, 0010, 0011, 0021). Each is a decision the
# user makes, never a default, so each is an unticked flag.
_CONFIRMATIONS = {
    "gaps": (
        "--confirm-gaps",
        "Generate despite a Stretch or Worth a try rating (only after the user says so)",
    ),
    "reapply": (
        "--confirm-reapply",
        "Generate despite an application to this posting inside the duplicate window",
    ),
    "below_minimum": (
        "--confirm-below-minimum",
        "Generate despite stated pay below the minimum (only after the user says so)",
    ),
}


# Commands that read the vault and then write it (the applications log, the learning items, the
# story bank, a draft recorded for a posting) hold this while they do, so two callers in one
# process never interleave (the MCP server and the web UI run commands on several threads). It is
# re-entrant because one command may call another. It does not protect against a second
# *process* (the command line while the MCP server runs); nothing ever did (ADR 0028).
_VAULT_WRITE_LOCK = threading.RLock()


def vault_write_lock() -> AbstractContextManager[Any]:
    """``with vault_write_lock():`` around a read-modify-write of the vault."""
    return _VAULT_WRITE_LOCK


def add_confirmation_flags(parser: argparse.ArgumentParser, *names: str) -> None:
    """Add the ``--confirm-*`` flags named in ``names`` (``gaps``, ``reapply``, ``below_minimum``)."""
    for name in names:
        flag, help_text = _CONFIRMATIONS[name]
        parser.add_argument(flag, action="store_true", help=help_text)


def check_gate(
    kind: str, jd_path: Path | None, profile: Profile | None, args: argparse.Namespace
) -> int | None:
    """Run the gate for a command, before it writes anything (ADR 0003, 0028).

    ``kind`` is ``documents`` (fit, duplicate and pay: the resume and cover letter), ``letter``
    (location and duplicate: the job-site letter) or ``location`` (the cold-call letter, when it is
    given a posting). Prints what passed. Returns ``None`` to go ahead, or the exit status to stop
    with: 2 for a refusal, which is printed to stderr, and 1 when the posting cannot be read.
    """
    if jd_path is None:
        return None
    try:
        text = jd_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    confirm_gaps = getattr(args, "confirm_gaps", False)
    confirm_reapply = getattr(args, "confirm_reapply", False)
    confirm_below_minimum = getattr(args, "confirm_below_minimum", False)
    try:
        if kind == "documents":
            assert profile is not None
            result = gate.check_documents(
                text,
                profile,
                confirm_gaps=confirm_gaps,
                confirm_reapply=confirm_reapply,
                confirm_below_minimum=confirm_below_minimum,
            )
            if result.fit is not None:
                print(f"Fit Rating: {result.fit.rating} — {result.fit.rationale}")
            notes = result.notes
        elif kind == "letter":
            notes = gate.check_letter(text, confirm_reapply=confirm_reapply)
        else:
            gate.check_location(text)
            notes = []
    except gate.GateRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    for note in notes:
        print(f"Note: {note}")
    return None


def logged_messages(located: outputs.Located) -> tuple[Message, ...]:
    """What ``outputs.report`` printed, as a message: which log entry a document was filed under."""
    note = outputs.logged_note(located)
    return (Message("info", note),) if note else ()


# -- what a document command says on the way, and what it returns ------------------------------


def say(notes: list[Message] | None, level: Level, text: str) -> None:
    """Record a line about the run in ``notes`` (what ``run`` collects into its result), or, for a
    caller that passes no list (a test, a script), print it the way the command line would."""
    if notes is not None:
        notes.append(Message(level, text))
        return
    printed = console(ok(messages=(Message(level, text),)))
    sys.stdout.write(printed.stdout)
    sys.stderr.write(printed.stderr)


def note_logged(notes: list[Message] | None, located: outputs.Located) -> None:
    """Say which log entry a document was filed under, when this call wrote one."""
    note = outputs.logged_note(located)
    if note:
        say(notes, "info", note)


@dataclass(frozen=True)
class Confirmations:
    """The user's confirmations past a refusal. Each is a decision the user makes, never a default."""

    gaps: bool = False
    reapply: bool = False
    below_minimum: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Confirmations:
        return cls(
            gaps=getattr(args, "confirm_gaps", False),
            reapply=getattr(args, "confirm_reapply", False),
            below_minimum=getattr(args, "confirm_below_minimum", False),
        )


@dataclass(frozen=True)
class DocumentData:
    """The document that was written (its sidecar is in ``written`` too) and the fit it was made
    for, when there was a posting to rate."""

    path: Path
    fit: FitResult | None


def gate_documents(
    jd_text: str, profile: Profile, confirm: Confirmations, notes: list[Message]
) -> None:
    """The gate for a tailored resume or cover letter: fit, duplicate and pay. A refusal raises
    ``Refusal``; what passed (the rating, and advice) goes into ``notes``."""
    result = gate.check_documents(
        jd_text,
        profile,
        confirm_gaps=confirm.gaps,
        confirm_reapply=confirm.reapply,
        confirm_below_minimum=confirm.below_minimum,
    )
    if result.fit is not None:
        notes.append(Message("info", f"Fit Rating: {result.fit.rating} — {result.fit.rationale}"))
    notes.extend(Message("note", note) for note in result.notes)


def produce_document(
    *,
    make: Callable[[Profile | None, list[Message]], tuple[Path, Path, FitResult | None]],
    gate_with_profile: Callable[[Profile, list[Message]], None] | None = None,
) -> CommandResult[DocumentData]:
    """Run a document command: gate it, make the document, and describe what happened.

    ``gate_with_profile`` is for a gate that needs the profile (fit); it runs first, before any
    file is written. ``make`` returns the document, its sidecar and the fit. The whole run holds the
    vault write lock, because it checks the log for a duplicate and then records a draft in it.
    """

    def body() -> CommandResult[DocumentData]:
        notes: list[Message] = []
        profile: Profile | None = None
        if gate_with_profile is not None:
            profile = bootstrap_load_profile()
            gate_with_profile(profile, notes)
        out, sidecar, fit = make(profile, notes)
        return ok(DocumentData(out, fit), messages=tuple(notes), written=(out, sidecar))

    with vault_write_lock():
        return guarded(body)


def bootstrap_load_profile() -> Profile:
    from jobomatic import bootstrap

    return bootstrap.load_profile()


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


def verify_pages(kind: str, path: Path, notes: list[Message] | None = None) -> int:
    """Measure ``path`` with LibreOffice and refuse it if it breaks the page limit for ``kind``.

    Only called when the user asked for ``--check-pages``. Raises ``DocumentError`` (a missing
    LibreOffice is one too), so the file stays where it is and the command exits 1.
    """
    from jobomatic import bootstrap
    from jobomatic.documents import service

    pages = service.check_pages(kind, path, bootstrap.page_counter())
    say(notes, "info", f"Pages: {pages}")
    return pages
