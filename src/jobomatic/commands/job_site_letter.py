#!/usr/bin/env python3
"""Generate a very short job-site cover letter (plain text) from the profile profile.

This generator is the deliberate exception to the DOCX-only rule: job sites
usually want plain text for their paste-box. It defaults to a ``.txt`` file.
If ``--out`` ends in ``.docx`` we still produce a DOCX using the shared helpers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

from docx import Document
from docx.shared import Pt

from jobomatic import bootstrap
from jobomatic.applications import outputs
from jobomatic.commands.support import (
    load_profile_or_none,
    require_path,
    run_and_report,
)
from jobomatic.documents.adapters.docx_layout import (
    BODY_SIZE,
    add_paragraph,
    clean_stack,
    letter_footer,
    letter_header,
)
from jobomatic.fit.engine import FitResult, humanize_evidence, rate_parsed_jd
from jobomatic.fit.parser import parse_jd
from jobomatic.provenance import write_sidecar


def _build_plain_text(
    company: str,
    title: str,
    result: FitResult,
    profile: Any,
) -> str:
    """Return a 2-paragraph job-site paste-box cover letter as plain text.

    The hook routes evidence through ``humanize_evidence`` so the prose reads
    naturally (``"production evidence at Acme Software"``) instead of the raw
    debug-grade ``"<skill> (<company>: production)"`` strings. We dedupe by
    lower-cased phrase to avoid repeating the same evidence form twice
    (e.g. two consecutive ``"production evidence at …"`` fragments).
    """
    top_matches = [m for m in result.required if m.status in ("match", "portfolio")][:2]
    if top_matches:
        seen: set[str] = set()
        evidence_bits: list[str] = []
        for m in top_matches:
            phrase = humanize_evidence(m)
            key = phrase.lower()
            if key not in seen:
                seen.add(key)
                evidence_bits.append(phrase)
        evidence_phrase = " and ".join(evidence_bits)
        hook = (
            f"I'm applying for the {title} role at {company}. "
            f"My background includes {evidence_phrase}, and I think that would carry over well to your team."
        )
    else:
        hook = (
            f"I'm applying for the {title} role at {company}. "
            f"I'd be glad to talk about how my background could help the team."
        )

    # Paragraph 2: concise closing + portfolio anchor.
    # The letter invites the reader to look, so it names only a project whose repository opens
    # for them; a private repo (``repo_private``) is still evidence, but not a link to follow.
    portfolio = ""
    shown = [p for p in profile.projects if not p.repo_private]
    if shown:
        project = shown[0]
        stack = clean_stack(project.stack, limit=3)
        portfolio = (
            f" You can see a recent example in {project.name} ({stack})."
            if stack
            else f" You can see a recent example in {project.name}."
        )

    closing = (
        f"I'd be glad to talk about how I could help {company}.{portfolio} "
        "Thanks for taking a look."
    )

    return f"{hook}\n\n{closing}"


def _build_docx(
    company: str,
    title: str,
    text: str,
    profile: Any,
    result: FitResult,
    out_path: Path,
    jd_path: Path,
) -> tuple[Path, Path, FitResult]:
    """Build a DOCX when the caller explicitly requests ``.docx``.

    Splits the plain-text body on blank lines and renders each chunk as a
    separate paragraph. The first paragraph sits flush against the date
    header; subsequent paragraphs get extra ``space_before`` so the DOCX
    visually matches the ``\\n\\n`` separation of the .txt version.
    """
    doc = Document()
    letter_header(
        doc,
        profile.identity,
        company=company,
        tagline=profile.identity.headline,
        re_line=f"Re: {title} — {company}",
    )
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    for i, paragraph in enumerate(paragraphs):
        space_before = Pt(8) if i == 0 else Pt(6)
        add_paragraph(doc, paragraph, size=BODY_SIZE, space_before=space_before)
    letter_footer(doc, profile.identity)

    doc.save(str(out_path))

    sidecar = write_sidecar(
        out_path,
        script="generate_job_site_letter.py",
        profile=profile,
        inputs=[str(jd_path)],
        fit_rating=result.rating,
    )
    return out_path, sidecar, result


def generate_job_site_letter(
    jd_path: Path,
    *,
    profile: Any | None = None,
    company: str | None = None,
    out_path: Path | None = None,
    root: Path = ROOT,
) -> tuple[Path, Path, FitResult]:
    """Build and write a short job-site cover letter plus provenance sidecar."""
    profile = profile or bootstrap.load_profile(root)
    jd_text = jd_path.read_text(encoding="utf-8")
    parsed = parse_jd(jd_text)
    result = rate_parsed_jd(parsed, profile)
    located = outputs.locate_application(
        jd_text,
        log=True,
        documents=("job_site_letter",),
        fit_rating=result.rating,
        company=company,
        root=root,
        create_folder=out_path is None,
    )
    company = company or parsed.company
    if out_path is None:
        out_path = located.folder / "job-site-letter.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    outputs.report(located)

    plain_text = _build_plain_text(company, parsed.title, result, profile)

    if out_path.suffix.lower() == ".docx":
        return _build_docx(company, parsed.title, plain_text, profile, result, out_path, jd_path)

    out_path.write_text(plain_text, encoding="utf-8")

    sidecar = write_sidecar(
        out_path,
        script="generate_job_site_letter.py",
        profile=profile,
        inputs=[str(jd_path)],
        fit_rating=result.rating,
    )
    return out_path, sidecar, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate-job-site",
        description="Generate a short job-site cover letter (default: plain-text .txt)",
    )
    parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    parser.add_argument("--company", help="Override company name used in filename")
    parser.add_argument("--out", type=Path, help="Output path (default .txt; use .docx for DOCX)")
    parser.add_argument(
        "--root",
        type=Path,
        help="Repository root to read the profile from (default: the vault)",
    )
    args = parser.parse_args(argv)

    try:
        require_path(args.jd, "JD file")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    profile = load_profile_or_none(args.root or ROOT)
    if profile is None:
        return 1

    return run_and_report(
        generate_job_site_letter,
        args.jd,
        profile=profile,
        company=args.company,
        out_path=args.out,
    )


if __name__ == "__main__":
    raise SystemExit(main())
