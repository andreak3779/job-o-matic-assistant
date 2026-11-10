#!/usr/bin/env python3
"""Capture and compare the text of every generated document, to prove a refactor changed nothing.

``capture`` runs each generator over three fictional job descriptions (and the profile-update
generators once) against a vault and writes the *text* of what they produce: DOCX paragraphs and
tables, markdown and plain text. ``compare`` captures again and diffs against a saved set.

Dates that change daily are replaced by ``<TODAY>``. The applications log and the output files
go to a scratch folder, so nothing in the vault is touched.

Usage:
    python scripts/golden_outputs.py capture --out DIR [--vault DIR]
    python scripts/golden_outputs.py compare --golden DIR [--vault DIR]
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"
JDS = ("strong-fit-jd.md", "cloud-devops-jd.md", "frontend-angular-jd.md")
PLATFORMS = (
    "generate-linkedin",
    "generate-github",
    "generate-jobgether",
    "generate-job-board",
    "generate-pluralsight",
)


def _text_of(paragraph) -> str:
    """The text of one paragraph element; a tab inside a run counts as a tab character."""
    parts: list[str] = []
    for el in paragraph.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "t":
            parts.append(el.text or "")
        elif tag == "tab" and el.getparent().tag.endswith("}r"):
            parts.append("\t")
    return "".join(parts)


def docx_text(path: Path) -> str:
    """Every paragraph and table cell of a DOCX, in document order."""
    from docx import Document

    document = Document(str(path))
    lines: list[str] = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append(_text_of(child))
        elif tag == "tbl":
            for row in child.iter():
                if row.tag.endswith("}tr"):
                    cells = []
                    for cell in row.iterchildren():
                        if cell.tag.endswith("}tc"):
                            cells.append(
                                " ".join(_text_of(p) for p in cell.iter() if p.tag.endswith("}p"))
                            )
                    lines.append(" | ".join(cells))
    for section in document.sections:
        for part in (section.header, section.first_page_header, section.footer):
            for paragraph in part.paragraphs:
                if paragraph.text.strip():
                    lines.append(f"[header/footer] {paragraph.text}")
    return "\n".join(lines)


def normalize(text: str) -> str:
    today = date.today()
    forms = {
        today.isoformat(),
        today.strftime("%B %d, %Y"),
        today.strftime("%B %-d, %Y"),
        today.strftime("%b %d, %Y"),
        today.strftime("%b %-d, %Y"),
        today.strftime("%d %B %Y"),
        today.strftime("%B %Y"),  # gap analyses are headed "<Month> <Year>"
    }
    for form in forms:
        text = text.replace(form, "<TODAY>")
    text = text.replace(str(ROOT), "<ROOT>")  # keep the checkout path out of the goldens
    return re.sub(r"[ \t]+\n", "\n", text).rstrip() + "\n"


def _run(argv: list[str]) -> tuple[int, str]:
    from jobomatic.interfaces.cli.main import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, out.getvalue() + err.getvalue()


def capture(vault: Path | None, dest: Path) -> list[str]:
    """Write the golden text files under ``dest``; returns notes about anything that failed."""
    notes: list[str] = []
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch_name:
        scratch = Path(scratch_name)
        os.environ["CLAUDE_JOBS_APPLICATIONS_LOG"] = str(scratch / "applications.jsonl")
        if vault is not None:
            os.environ["JOBOMATIC_VAULT"] = str(vault)

        def save(name: str, text: str) -> None:
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(normalize(text), encoding="utf-8")

        for jd_name in JDS:
            jd = FIXTURES / jd_name
            stem = jd.stem
            jobs: list[tuple[str, list[str], str | None]] = [
                ("fit-check", ["fit-check", str(jd)], None),
                ("gap-analysis.md", ["gap-analysis", str(jd), "--out", "{out}.md"], "md"),
                (
                    "resume.docx",
                    ["generate-resume", str(jd), "--out", "{out}.docx", "--confirm-gaps"],
                    "docx",
                ),
                (
                    "cover-letter.docx",
                    ["generate-cover-letter", str(jd), "--out", "{out}.docx", "--confirm-gaps"],
                    "docx",
                ),
                ("job-site-letter.txt", ["generate-job-site", str(jd), "--out", "{out}.txt"], "md"),
                ("interview-prep.docx", ["interview-prep", str(jd), "--out", "{out}.docx"], "docx"),
                (
                    "cold-outreach.docx",
                    ["generate-cold-call", str(jd), "--out", "{out}.docx"],
                    "docx",
                ),
                (
                    "thank-you.docx",
                    [
                        "generate-thank-you",
                        str(jd),
                        "--discussion-point",
                        "We talked about release pipelines.",
                        "--interviewer",
                        "Pat Example",
                        "--out",
                        "{out}.docx",
                    ],
                    "docx",
                ),
            ]
            for name, argv, kind in jobs:
                out = scratch / f"{stem}-{name}".replace(".", "_")
                args = [a.replace("{out}", str(out)) for a in argv]
                code, printed = _run(args)
                if code != 0:
                    notes.append(f"{stem}/{name}: exit {code}: {printed.strip()[:200]}")
                    save(f"{stem}/{name}.txt", f"EXIT {code}\n{printed}")
                    continue
                if kind is None:
                    save(f"{stem}/{name}.txt", printed)
                elif kind == "docx":
                    save(f"{stem}/{name}.txt", docx_text(Path(f"{out}.docx")))
                else:
                    suffix = ".md" if name.endswith(".md") else ".txt"
                    save(f"{stem}/{name}.txt", Path(f"{out}{suffix}").read_text(encoding="utf-8"))
        for command in PLATFORMS:
            out = scratch / f"{command}.md"
            code, printed = _run([command, "--out", str(out)])
            if code != 0:
                notes.append(f"{command}: exit {code}: {printed.strip()[:200]}")
                save(f"profiles/{command}.txt", f"EXIT {code}\n{printed}")
            else:
                save(f"profiles/{command}.txt", out.read_text(encoding="utf-8"))
    return notes


def compare(vault: Path | None, golden: Path) -> list[str]:
    """Diff lines for every file that differs from the saved set (empty when identical)."""
    with tempfile.TemporaryDirectory() as fresh_name:
        fresh = Path(fresh_name)
        capture(vault, fresh)
        problems: list[str] = []
        names = {p.relative_to(golden) for p in golden.rglob("*.txt")} | {
            p.relative_to(fresh) for p in fresh.rglob("*.txt")
        }
        for rel in sorted(names):
            old, new = golden / rel, fresh / rel
            if not old.exists():
                problems.append(f"{rel}: only in the new capture")
            elif not new.exists():
                problems.append(f"{rel}: missing from the new capture")
            elif old.read_text(encoding="utf-8") != new.read_text(encoding="utf-8"):
                diff = difflib.unified_diff(
                    old.read_text(encoding="utf-8").splitlines(),
                    new.read_text(encoding="utf-8").splitlines(),
                    "golden",
                    "now",
                    lineterm="",
                    n=1,
                )
                problems.append(f"{rel}: differs\n" + "\n".join(list(diff)[:40]))
        return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--out", type=Path, required=True)
    cap.add_argument("--vault", type=Path)
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("--golden", type=Path, required=True)
    cmp_.add_argument("--vault", type=Path)
    args = parser.parse_args(argv)

    if args.command == "capture":
        notes = capture(args.vault, args.out)
        files = sum(1 for _ in args.out.rglob("*.txt"))
        print(f"Captured {files} files into {args.out}")
        for note in notes:
            print(f"  note: {note}")
        return 0
    problems = compare(args.vault, args.golden)
    print("\n".join(problems) if problems else "Golden outputs match.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
