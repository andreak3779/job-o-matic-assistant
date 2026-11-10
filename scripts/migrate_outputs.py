#!/usr/bin/env python3
"""One-time migration of generated files into the outputs hierarchy (ADR 0015).

Reads the vault's old loose files (``outputs/_legacy_import/**`` and ``outputs/profiles/drafts``)
and moves them into ``outputs/applications/<date>_<company>_<role>/`` and friends. Files it
cannot place go to ``outputs/_unsorted/`` under their old relative path. **Nothing is deleted.**

It prints the mapping and changes nothing unless ``--apply`` is given.

A file whose company matches an application in the log goes to that application's folder.
Otherwise a folder is made from the file's date (the sidecar's ``generated_at``, else the file's
modification time) and the name in the file name. When two files want the same destination the
newer one wins and the older one goes to ``_unsorted``.

Usage:
    python scripts/migrate_outputs.py [--vault DIR]            # dry run
    python scripts/migrate_outputs.py [--vault DIR] --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jobomatic import applications, paths
from jobomatic.applications import Application

SCAN_ROOTS = ("_legacy_import", "profiles/drafts")
SIDECAR = ".meta.json"
MAP_FILE = "_migration-map.tsv"
# Labels that mean "the generic one", not a particular employer.
GENERIC_LABELS = {"template", "general", "seniorfullstacknet"}
PLATFORMS = ("linkedin", "github", "jobgether", "job-board", "pluralsight")

# (pattern, kind, file name in the destination folder). Tried in order on the base name.
_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^[^_]+_PartTimeResume_(?P<label>.+)\.docx$"), "part-time", "resume.docx"),
    (
        re.compile(r"^[^_]+_PartTimeCoverLetter_(?P<label>.+)\.docx$"),
        "part-time",
        "cover-letter.docx",
    ),
    (re.compile(r"^[^_]+_Resume_(?P<label>.+)\.docx$"), "application", "resume.docx"),
    (re.compile(r"^[^_]+_CoverLetter_(?P<label>.+)\.docx$"), "application", "cover-letter.docx"),
    (re.compile(r"^[^_]+_ThankYou_(?P<label>.+)\.docx$"), "application", "thank-you.docx"),
    (re.compile(r"^[^_]+_JobSite_(?P<label>.+)\.txt$"), "application", "job-site-letter.txt"),
    (re.compile(r"^[^_]+_ColdCall_(?P<label>.+)\.docx$"), "outreach", "cold-outreach.docx"),
    (
        re.compile(r"^(?P<label>[^_]+)_(?P<role>.+)_GapAnalysis\.md$"),
        "application",
        "gap-analysis.md",
    ),
    (re.compile(r"^SalaryExpectations_(?P<label>.+)\.md$"), "application", "salary.md"),
    (re.compile(r"^TopChoice_(?P<label>.+)\.md$"), "application", "top-choice.md"),
    (re.compile(r"^(?P<label>.+)_InterviewPrep\.docx$"), "application", "interview-prep.docx"),
    (re.compile(r"^(?P<label>.+)_InterviewPrep\.md$"), "application", "interview-prep.md"),
]
_TEMPLATE_NAMES = {
    "resume.docx": "resume.docx",
    "cover-letter.docx": "cover-letter.docx",
}
_DRAFT = re.compile(r"^(?P<platform>" + "|".join(PLATFORMS) + r")-(?:profile-)?update-draft\.md$")


@dataclass(frozen=True)
class Move:
    src: Path  # relative to the outputs directory
    dest: Path  # relative to the outputs directory
    why: str


@dataclass
class _Item:
    rel: Path
    kind: str  # application | part-time | outreach | profiles | templates | research
    label: str
    role: str | None
    filename: str
    when: datetime
    sidecar_of: Path | None = None  # set on a .meta.json: the file it describes


def _split_words(text: str) -> str:
    """``BrightPath`` -> ``Bright Path``; underscores and hyphens become spaces."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    return re.sub(r"[_\-]+", " ", text).strip()


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _read_when(path: Path) -> datetime:
    """When a file was made: the sidecar's ``generated_at`` if there is one, else its mtime."""
    sidecar = path.with_name(path.name + SIDECAR)
    if sidecar.is_file():
        try:
            stamp = json.loads(sidecar.read_text(encoding="utf-8")).get("generated_at")
            if stamp:
                return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except (OSError, ValueError):
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _classify(rel: Path, base: Path) -> _Item | None:
    name = rel.name
    if name == ".gitkeep":
        return None
    sidecar_of: Path | None = None
    if name.endswith(SIDECAR):
        name = name[: -len(SIDECAR)]
        sidecar_of = rel.with_name(name)
    when = _read_when(base / (rel if sidecar_of is None else sidecar_of))

    in_drafts = rel.parts[:2] == ("profiles", "drafts")
    if in_drafts and (m := _DRAFT.match(name)):
        return _Item(rel, "profiles", m["platform"], None, f"{when:%Y-%m-%d}.md", when, sidecar_of)
    if "JobFit" in name and name.endswith(".md"):
        return _Item(rel, "research", "", None, "job-fit-recommendations.md", when, sidecar_of)
    for pattern, kind, filename in _RULES:
        m = pattern.match(name)
        if not m:
            continue
        label, role = m["label"], (m.groupdict().get("role"))
        if label.lower() in GENERIC_LABELS:
            if filename in _TEMPLATE_NAMES and kind != "part-time":
                return _Item(rel, "templates", "", None, filename, when, sidecar_of)
            if kind == "part-time":
                return _Item(rel, "templates", "", None, f"part-time-{filename}", when, sidecar_of)
            if filename == "salary.md":
                return _Item(rel, "research", "", None, "salary-expectations.md", when, sidecar_of)
        return _Item(rel, kind, label, role, filename, when, sidecar_of)
    return None


def _match_application(label: str, role: str | None, apps: list[Application]) -> Application | None:
    """The logged application a file name refers to, if any.

    Company names must agree (one may be a prefix of the other, at least 4 characters unless
    they are equal). With several applications at one company, the one whose title shares the
    most words with the rest of the file name wins; otherwise the earliest.
    """
    wanted = _norm(label)
    candidates = []
    for app in apps:
        key = _norm(applications.company_key(app.company))
        if not key or not wanted:
            continue
        same = key == wanted
        prefix = min(len(key), len(wanted)) >= 4 and (
            key.startswith(wanted) or wanted.startswith(key)
        )
        if same or prefix:
            candidates.append((len(key) if same else 0, key, app))
    if not candidates:
        return None
    best_key = max(candidates, key=lambda c: (c[0], len(c[1])))[1]
    same_company = [c[2] for c in candidates if c[1] == best_key]
    extra = _norm(wanted.removeprefix(best_key)) if wanted.startswith(best_key) else ""
    words = set(_split_words(label).lower().split()) | set(_split_words(role or "").lower().split())

    def overlap(app: Application) -> int:
        return len(words & set(_split_words(app.title).lower().split())) if extra or role else 0

    return min(same_company, key=lambda a: (-overlap(a), a.created))


def plan(outputs: Path, apps: list[Application]) -> list[Move]:
    """The moves that would put every old file where it belongs. Pure: touches nothing."""
    items: list[_Item] = []
    unsorted: list[tuple[Path, str]] = []
    for root in SCAN_ROOTS:
        base = outputs / root
        if not base.is_dir():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            rel = path.relative_to(outputs)
            item = _classify(rel, outputs)
            if item is None:
                if path.name != ".gitkeep":
                    unsorted.append((rel, "not recognised"))
                continue
            items.append(item)

    # Group the application and part-time files that belong to one job into one folder.
    folders: dict[tuple[str, str], str] = {}
    dates: dict[tuple[str, str], datetime] = {}
    roles: dict[tuple[str, str], str] = {}
    matched: dict[str, str] = {}
    for item in items:
        if item.kind not in ("application", "part-time", "outreach"):
            continue
        key = (item.kind, _norm(item.label))
        dates[key] = min(dates.get(key, item.when), item.when)
        if item.role:
            roles.setdefault(key, item.role)
    for item in items:
        if item.kind not in ("application", "part-time", "outreach"):
            continue
        key = (item.kind, _norm(item.label))
        if key in folders:
            continue
        app = (
            _match_application(item.label, item.role, apps) if item.kind == "application" else None
        )
        if app:
            folders[key] = applications.folder_name_for(app)
            matched[folders[key]] = app.id
        else:
            role = _split_words(roles[key]) if key in roles else None
            folders[key] = paths.folder_name(dates[key].date(), _split_words(item.label), role)

    # Newest file claims a destination; older claimants are set aside, not overwritten.
    claimed: dict[Path, _Item] = {}
    by_rel = {i.rel: i for i in items}
    moves: list[Move] = []
    for item in sorted(items, key=lambda i: i.when, reverse=True):
        dest = _destination(item, folders)
        if item.sidecar_of is not None:
            described = by_rel.get(item.sidecar_of) if item.sidecar_of else None
            if described is None:
                unsorted.append((item.rel, "the file it describes is not here"))
                continue
            owner = claimed.get(_destination(described, folders))
            if owner is None or owner.rel != item.sidecar_of:
                unsorted.append((item.rel, "the file it describes was set aside"))
                continue
            moves.append(Move(item.rel, dest, "sidecar"))
            continue
        if dest in claimed:
            unsorted.append((item.rel, f"older than {claimed[dest].rel.name}"))
            continue
        claimed[dest] = item
        logged = item.kind == "application" and dest.parent.name in matched
        why = "matches a logged application" if logged else "new folder"
        moves.append(Move(item.rel, dest, why))
    moves += [Move(rel, _unsorted_path(rel), why) for rel, why in unsorted]
    return sorted(moves, key=lambda m: (m.dest.parts[0] == "_unsorted", str(m.dest), str(m.src)))


def _destination(item: _Item, folders: dict[tuple[str, str], str]) -> Path:
    suffix = SIDECAR if item.sidecar_of is not None else ""
    if item.kind == "profiles":
        return Path("profiles") / paths.slug(item.label) / (item.filename + suffix)
    if item.kind in ("templates", "research"):
        return Path(item.kind) / (item.filename + suffix)
    folder = folders[(item.kind, _norm(item.label))]
    group = {"application": "applications", "part-time": "part-time", "outreach": "outreach"}
    return Path(group[item.kind]) / folder / (item.filename + suffix)


def _unsorted_path(rel: Path) -> Path:
    parts = rel.parts[1:] if rel.parts[0] == "_legacy_import" else rel.parts
    return Path("_unsorted").joinpath(*parts)


def apply(outputs: Path, moves: list[Move]) -> None:
    """Move the files. Never overwrites: a taken destination goes to ``_unsorted`` instead."""
    for move in moves:
        src, dest = outputs / move.src, outputs / move.dest
        if dest.exists():
            dest = outputs / _unsorted_path(move.src)
        if dest.exists():
            raise FileExistsError(f"both {move.dest} and {dest} already exist")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    lines = [f"{m.src}\t{m.dest}\t{m.why}" for m in moves]
    (outputs / MAP_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def report(moves: list[Move]) -> str:
    folders = {m.dest.parent for m in moves if m.dest.parts[0] in ("applications", "part-time")}
    unsorted = [m for m in moves if m.dest.parts[0] == "_unsorted"]
    lines = [f"{m.src}  ->  {m.dest}   [{m.why}]" for m in moves]
    lines.append("")
    lines.append(
        f"{len(moves)} files: {len(moves) - len(unsorted)} placed in {len(folders)} folders "
        f"or shared folders, {len(unsorted)} to _unsorted."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", type=Path, help="Vault directory (default: the configured one)")
    parser.add_argument("--apply", action="store_true", help="Move the files (default: dry run)")
    args = parser.parse_args(argv)

    outputs = (args.vault / "outputs") if args.vault else paths.outputs_dir()
    log = (args.vault / "applications" / "applications.jsonl") if args.vault else None
    moves = plan(outputs, applications.load_applications(log))
    print(report(moves))
    if not args.apply:
        print("\nDry run: nothing was moved. Run again with --apply to move the files.")
        return 0
    apply(outputs, moves)
    print(f"\nMoved. The mapping is in {outputs / MAP_FILE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
