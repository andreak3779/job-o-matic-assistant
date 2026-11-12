#!/usr/bin/env python3
"""Generate a JD-tailored cover-letter DOCX from the profile profile."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from jobomatic import bootstrap, paths
from jobomatic.applications import outputs
from jobomatic.commands.support import (
    Confirmations,
    DocumentData,
    add_confirmation_flags,
    gate_documents,
    note_logged,
    produce_document,
    require_path,
    say,
    verify_pages,
)
from jobomatic.documents.adapters.docx_layout import (
    DEFAULT_SIGNATURE_NAME,
    clean_stack,
)
from jobomatic.documents.adapters.docx_tailored import DocxTailoredCoverLetter
from jobomatic.documents.model import LetterItem, ResumeContact, TailoredCoverLetter
from jobomatic.fit.engine import (
    FitResult,
    humanize_evidence,
    profile_has_skill_text,
    rate_parsed_jd,
)
from jobomatic.fit.parser import parse_jd
from jobomatic.provenance import write_sidecar
from jobomatic.results import CommandResult, Message, emit


def _display_skill(skill: str, parsed: Any) -> str:
    """Return the skill as the JD wrote it (``.NET``, ``SQL Server``), not the lower-cased match key."""
    for original in parsed.required + parsed.nice_to_have:
        if original.lower() == skill.lower():
            skill = original
            break
    else:
        skill = skill.upper() if len(skill) <= 3 else skill.title()
    return f".{skill}" if skill.upper().startswith("NET ") else skill


def _select_evidence(
    profile: Any,
    parsed: Any,
    company: str,
    result: FitResult,
) -> dict[str, Any]:
    """Pick hook, bring-items, and highlights from verified profile evidence.

    The caller passes in the precomputed ``FitResult`` so we don't double-rate.
    Only production (`match`) and portfolio evidence are used in the body.
    Coursework and gaps are omitted from the letter unless the profile explicitly
    tracks them as planned learning (never claimed as experience).
    """
    grounded_required = result.grounded_required
    top_match = next(
        (m for m in grounded_required if m.status == "match"),
        grounded_required[0] if grounded_required else None,
    )

    # Portfolio projects that match required skills (alias-aware).
    matching_projects: list[Any] = []
    for project in profile.projects:
        text = f"{project.name} {' '.join(project.stack)} {project.description}"
        if profile_has_skill_text(" ".join(parsed.required), text):
            matching_projects.append(project)

    # WHAT-I-BRING: grounded required first, then grounded nice-to-have.
    bring: list[dict[str, str]] = []
    for m in grounded_required + [m for m in result.nice_to_have if m.is_grounded]:
        bring.append({"label": _display_skill(m.skill, parsed), "body": humanize_evidence(m)})
        if len(bring) >= 5:
            break

    # Highlights: up to 2 employers / portfolio projects with required-skill overlap.
    highlights: list[dict[str, str]] = []
    for exp in profile.resume_roles:
        if not exp.company:  # e.g. the self-directed learning block, not an employer
            continue
        bullets_joined = " ".join(exp.bullets).lower()
        score = sum(1 for req in parsed.required if _names_skill(req, bullets_joined))
        if score:
            best_bullet = max(
                exp.bullets,
                key=lambda b: sum(1 for r in parsed.required if _names_skill(r, b.lower())),
                default="",
            )
            highlights.append(
                {
                    "label": f"{exp.company} ({exp.dates or 'recent'})",
                    "body": best_bullet.replace("**", ""),
                }
            )
            if len(highlights) >= 2:
                break
    for project in matching_projects:
        if len(highlights) >= 2:
            break
        stack_text = clean_stack(project.stack, limit=4)
        highlights.append(
            {
                "label": f"{project.name} (portfolio)",
                "body": f"{project.description} Built with {stack_text}."
                if stack_text
                else project.description,
            }
        )

    # Hook: if no verified evidence, use a neutral hook rather than fabricate fit.
    top_required = parsed.required[0] if parsed.required else parsed.title
    if top_match:
        hook = (
            f"Your {parsed.title} posting asks for {top_required}, which is a big part of what I do. "
            f"I have {humanize_evidence(top_match)}, so I could be useful on the team quickly."
        )
    elif matching_projects:
        p = matching_projects[0]
        stack = clean_stack(p.stack, limit=3)
        hook = (
            f"I saw the {parsed.title} opening at {company}. Lately I've been building {p.name} "
            f"with {stack}, which lines up with what you're hiring for."
        )
    else:
        hook = (
            f"I'm applying for the {parsed.title} role at {company}. I'd like to talk about "
            f"where my background could help the team."
        )

    # Closing: focus on verified skills only, falling back to neutral phrasing.
    focus_skills = [_display_skill(m.skill, parsed) for m in grounded_required[:2]]
    if focus_skills:
        focus = " and ".join(focus_skills)
        closing = (
            f"I'd enjoy talking through how my {focus} experience could help {company}. "
            f"Do you have time for a short call this week or next?"
        )
    else:
        closing = (
            f"I'd like to talk about how I could help the {parsed.title} team at {company}. "
            f"Do you have time for a short call this week or next?"
        )

    low_confidence = len(grounded_required) < 2 and not matching_projects

    return {
        "bring": bring,
        "highlights": highlights,
        "hook": hook,
        "closing": closing,
        "low_confidence": low_confidence,
    }


def _names_skill(requirement: str, text_lower: str) -> bool:
    """True when ``text_lower`` mentions the requirement, or any one part of an "A / B" entry."""
    return any(part.strip().lower() in text_lower for part in requirement.split(" / "))


def _letter_content(
    profile: Any, title: str, company: str, evidence: dict[str, Any]
) -> TailoredCoverLetter:
    ident = profile.identity
    return TailoredCoverLetter(
        contact=ResumeContact(
            name=ident.name or DEFAULT_SIGNATURE_NAME,
            email=ident.email,
            phone=ident.phone,
            location=ident.location,
            linkedin=ident.linkedin,
            github=ident.github,
            pluralsight=ident.pluralsight,
        ),
        tagline=ident.headline,
        role_title=title,
        company=company,
        hook=evidence["hook"],
        bring=[LetterItem(**item) for item in evidence["bring"]],
        highlights=[LetterItem(**item) for item in evidence["highlights"]],
        closing=evidence["closing"],
    )


def generate_cover_letter(
    jd_path: Path,
    *,
    profile: Any | None = None,
    company: str | None = None,
    out_path: Path | None = None,
    record: bool = True,
    check_pages: bool = False,
    notes: list[Message] | None = None,
) -> tuple[Path, Path, FitResult]:
    """Build and write a tailored cover-letter DOCX plus provenance sidecar from a posting file.

    See ``generate_cover_letter_from_text``.
    """
    return generate_cover_letter_from_text(
        jd_path.read_text(encoding="utf-8"),
        source=jd_path,
        profile=profile,
        company=company,
        out_path=out_path,
        record=record,
        check_pages=check_pages,
        notes=notes,
    )


def generate_cover_letter_from_text(
    jd_text: str,
    *,
    source: Path | None = None,
    profile: Any | None = None,
    company: str | None = None,
    out_path: Path | None = None,
    record: bool = True,
    check_pages: bool = False,
    notes: list[Message] | None = None,
) -> tuple[Path, Path, FitResult]:
    """Build and write a tailored cover-letter DOCX plus provenance sidecar.

    ``source`` is where the posting came from, recorded in the sidecar (``None`` for pasted text).
    ``record=False`` skips the applications log and needs an explicit ``out_path``.
    ``check_pages`` measures the real page count with LibreOffice and raises unless it is one.
    ``notes``, when given, collects what would otherwise be printed (see ``say``).
    """
    profile = profile or bootstrap.load_profile()
    parsed = parse_jd(jd_text)
    result = rate_parsed_jd(parsed, profile)
    company = company or parsed.company
    evidence = _select_evidence(profile, parsed, company, result)

    if record:
        located = outputs.locate_application(
            jd_text,
            log=True,
            documents=("cover_letter",),
            fit_rating=result.rating,
            company=company,
            create_folder=out_path is None,
        )
        if out_path is None:
            out_path = located.folder / "cover-letter.docx"
        note_logged(notes, located)
    elif out_path is None:
        raise ValueError("out_path is required when record is False")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    letter = _letter_content(profile, parsed.title, company, evidence)
    DocxTailoredCoverLetter().render(letter, out_path)

    if evidence["low_confidence"]:
        say(
            notes,
            "warning",
            f"only {len(result.grounded_required)} required skill(s) have verified evidence; "
            "letter drafted cautiously.",
        )

    sidecar = write_sidecar(
        out_path,
        script="generate_cover_letter.py",
        profile=profile,
        inputs=[str(source)] if source else [],
        fit_rating=result.rating,
        evidence_sources=result.evidence_sources(),
        warnings=["low evidence — manually review before sending"]
        if evidence["low_confidence"]
        else [],
    )
    if check_pages:
        verify_pages("cover-letter", out_path, notes)
    return out_path, sidecar, result


def run(
    jd_text: str,
    *,
    source: Path | None = None,
    company: str | None = None,
    out: Path | None = None,
    check_pages: bool = False,
    confirm: Confirmations = Confirmations(),
) -> CommandResult[DocumentData]:
    """Gate the posting (fit, duplicate, pay) and then write the tailored cover letter."""
    return produce_document(
        gate_with_profile=lambda profile, notes: gate_documents(jd_text, profile, confirm, notes),
        make=lambda profile, notes: generate_cover_letter_from_text(
            jd_text,
            source=source,
            profile=profile,
            company=company,
            out_path=out,
            check_pages=check_pages,
            notes=notes,
        ),
    )


PLACEHOLDER_COMPANY = "[Company Name]"
PLACEHOLDER_ROLE = "[Role Title]"
_TEMPLATE_BRING = 4


def generate_profile_cover_letter(
    *,
    profile: Any | None = None,
    out_path: Path | None = None,
    check_pages: bool = False,
) -> tuple[Path, Path]:
    """A reusable cover-letter template: not tailored, with ``[Company Name]`` and ``[Role Title]``
    left as literal text for the candidate to swap per application. Nothing is logged.

    Built from the candidate's own positioning: the hook is the first sentence of the summary,
    WHAT I BRING comes from the differentiators, and the highlights are the most recent
    employers. Returns ``(docx_path, sidecar_path)``.
    """
    profile = profile or bootstrap.load_profile()
    out_path = out_path or paths.output_dir("templates") / "cover-letter.docx"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = " ".join(profile.identity.summary.split())
    hook = re.split(r"(?<=[.!?])\s+", summary, maxsplit=1)[0] if summary else ""
    bring = []
    for item in profile.identity.differentiators[:_TEMPLATE_BRING]:
        label, _, body = item.partition(":")
        bring.append({"label": label.strip(), "body": body.strip() or label.strip()})
    highlights = [
        {
            "label": f"{role.company} ({role.dates or 'recent'})",
            "body": role.bullets[0].replace("**", ""),
        }
        for role in profile.resume_roles
        if role.company and role.bullets
    ][:2]
    evidence = {
        "hook": hook,
        "bring": bring,
        "highlights": highlights,
        "closing": (
            "I'm looking for roles where I can contribute from day one. "
            f"I would welcome the chance to speak with {PLACEHOLDER_COMPANY} about how my "
            f"background fits {PLACEHOLDER_ROLE}."
        ),
    }
    letter = _letter_content(profile, PLACEHOLDER_ROLE, PLACEHOLDER_COMPANY, evidence)
    DocxTailoredCoverLetter().render(letter, out_path)
    sidecar = write_sidecar(
        out_path, script="generate_cover_letter.py", profile=profile, inputs=[], fit_rating=None
    )
    if check_pages:
        verify_pages("cover-letter", out_path)
    return out_path, sidecar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate-cover-letter", description="Generate a tailored cover-letter DOCX"
    )
    parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    parser.add_argument("--company", help="Override company name used in filename")
    parser.add_argument("--out", type=Path, help="Output DOCX path")
    parser.add_argument(
        "--check-pages",
        action="store_true",
        help="Count the real pages with LibreOffice and fail unless it is 1 (slow; needs LibreOffice)",
    )
    add_confirmation_flags(parser, "gaps", "reapply", "below_minimum")
    args = parser.parse_args(argv)

    try:
        require_path(args.jd, "JD file")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return emit(
        run(
            args.jd.read_text(encoding="utf-8"),
            source=args.jd,
            company=args.company,
            out=args.out,
            check_pages=args.check_pages,
            confirm=Confirmations.from_args(args),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
