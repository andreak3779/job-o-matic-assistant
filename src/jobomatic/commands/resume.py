#!/usr/bin/env python3
"""Generate a JD-tailored resume DOCX from the profile profile."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from docx.shared import Pt

from jobomatic import bootstrap, paths
from jobomatic.applications import outputs
from jobomatic.commands.support import (
    load_profile_or_none,
    require_path,
    run_and_report,
    verify_pages,
)
from jobomatic.documents.adapters.docx_layout import (
    DEFAULT_SIGNATURE_NAME,
)
from jobomatic.documents.adapters.docx_tailored import DocxTailoredResume
from jobomatic.documents.model import ResumeContact, ResumeJob, SkillLine, TailoredResume
from jobomatic.documents.pagefit import fit_resume
from jobomatic.fit.engine import FitResult, profile_has_skill_text, rate_parsed_jd
from jobomatic.fit.parser import parse_jd
from jobomatic.provenance import write_sidecar

_PAGE2_HEADER_SIZE = Pt(9)
_MARKDOWN_RULE = re.compile(r"[-*_]{3,}")  # a leftover "---" line is not a paragraph


def _skill_score(skill: str, jd_pool: str) -> int:
    """Count how many JD tokens/aliases this resume skill overlaps.

    Uses the fit engine's alias expansion so a resume skill like
    ``"Azure (AZ-900)"`` boosts against a JD asking for ``"AZ-900"``.
    """
    return 1 if profile_has_skill_text(skill, jd_pool) else 0


def _bullet_score(bullet: str, jd_pool: str) -> int:
    """Score a bullet by alias-aware matches against the JD pool.

    Each unique JD skill that hits this bullet (after alias expansion)
    contributes one point. Counts are bounded by the number of JD skills so
    longer bullets don't get a free length boost.
    """
    jd_terms = {t.lower() for t in re.split(r"[/;,\s]+", jd_pool) if len(t) > 1}
    if not jd_terms:
        return 0
    return sum(1 for t in jd_terms if profile_has_skill_text(t, bullet))


def _skill_content(profile: Any, parsed: Any) -> list[SkillLine]:
    """Technical-skills categories, ordered by relevance to the posting."""
    jd_pool = " ".join(parsed.required + parsed.nice_to_have)
    categories = list(profile.skills.groups)
    categories.sort(
        key=lambda cat: sum(_skill_score(s, jd_pool) for s in cat.skills),
        reverse=True,
    )
    return [SkillLine(label=cat.category, skills=", ".join(cat.skills)) for cat in categories]


def _job_content(profile: Any, parsed: Any) -> list[ResumeJob]:
    """The resume-window roles with their bullets ordered by relevance to the posting."""
    jd_pool = " ".join(parsed.required + parsed.nice_to_have)
    return [
        ResumeJob(
            title=job.title,
            company=job.company or "",
            location=job.location or "",
            dates=job.dates or "",
            bullets=sorted(job.bullets, key=lambda b: _bullet_score(b, jd_pool), reverse=True),
        )
        for job in profile.resume_roles
    ]


def _cert_status(cert: Any) -> str:
    """The cert's own note when it has one, else its status in words ("In Progress")."""
    return str(cert.notes or cert.status.value.replace("_", " ").title())


def _certification_lines(profile: Any) -> list[str]:
    certs = {c.code: c for c in profile.certifications}
    lines: list[str] = []
    az900 = certs.get("AZ-900")
    ai200 = certs.get("AI-200")
    if az900:
        lines.append(f"Microsoft Azure Fundamentals (AZ-900) — {_cert_status(az900)}")
    # A not-pursuing / on-hold cert is omitted: its notes are internal, not resume copy.
    if ai200 and ai200.status.value != "not_pursuing":
        lines.append(f"Azure AI Cloud Developer Associate (AI-200) — {_cert_status(ai200)}")
    return lines


def _education_lines(profile: Any) -> list[str]:
    lines = []
    for edu in profile.education:
        line = f"{edu.credential} — {edu.institution}"
        if edu.dates:
            line += f", {edu.dates}"
        lines.append(line)
    return lines


def _resume_content(profile: Any, parsed: Any, tagline: str) -> TailoredResume:
    """The resume for a posting. ``parsed`` orders skills and bullets by relevance to it."""
    ident = profile.identity
    # Paragraphs only: a blank line between them must not become an empty second paragraph.
    summary = [
        line.strip()
        for line in ident.summary.splitlines()
        if line.strip() and not _MARKDOWN_RULE.fullmatch(line.strip())
    ][:2] or [""]
    full = TailoredResume(
        contact=ResumeContact(
            name=ident.name or DEFAULT_SIGNATURE_NAME,
            email=ident.email,
            phone=ident.phone,
            location=ident.location,
            linkedin=ident.linkedin,
            github=ident.github,
            pluralsight=ident.pluralsight,
        ),
        tagline=tagline,
        summary=summary,
        skills=_skill_content(profile, parsed),
        experience=_job_content(profile, parsed),
        additional_experience=ident.additional_experience.strip(),
        education=_education_lines(profile),
        certifications=_certification_lines(profile),
    )
    # The profile holds every skill and every bullet; a resume is at most two pages, so trim it
    # (oldest role first, never below two bullets) or refuse. ``--check-pages`` measures the result.
    return fit_resume(full)


def _build_tagline(parsed: Any, profile: Any) -> str:
    """Compose a JD-aware tagline from role title + top skills."""
    title = parsed.title
    top_skills = parsed.required[:3]
    if not top_skills and profile.skills.groups:
        first_cat = profile.skills.groups[0]
        top_skills = first_cat.skills[:3]
    skills_text = " · ".join(top_skills)
    return f"{title} | {skills_text}" if skills_text else title


def generate_resume(
    jd_path: Path,
    *,
    profile: Any | None = None,
    company: str | None = None,
    out_path: Path | None = None,
    check_pages: bool = False,
) -> tuple[Path, Path, FitResult]:
    """Build and write a tailored resume DOCX plus provenance sidecar.

    Returns ``(docx_path, sidecar_path, fit_result)``. The profile is *not*
    mutated: the JD-specific tagline is used for this document only. The content is trimmed to
    two pages first (or refused), before anything is logged. ``check_pages`` then measures the
    real page count with LibreOffice and raises if it is over.
    """
    profile = profile or bootstrap.load_profile()
    jd_text = jd_path.read_text(encoding="utf-8")
    parsed = parse_jd(jd_text)
    result = rate_parsed_jd(parsed, profile)
    content = _resume_content(profile, parsed, _build_tagline(parsed, profile))

    located = outputs.locate_application(
        jd_text,
        log=True,
        documents=("resume",),
        fit_rating=result.rating,
        company=company,
        create_folder=out_path is None,
    )
    if out_path is None:
        out_path = located.folder / "resume.docx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    outputs.report(located)

    DocxTailoredResume().render(content, out_path)

    sidecar = write_sidecar(
        out_path,
        script="generate_resume.py",
        profile=profile,
        inputs=[str(jd_path)],
        fit_rating=result.rating,
    )
    if check_pages:
        verify_pages("resume", out_path)
    return out_path, sidecar, result


def generate_profile_resume(
    *,
    profile: Any | None = None,
    out_path: Path | None = None,
    check_pages: bool = False,
) -> tuple[Path, Path]:
    """The platform-ready resume: no job description, the profile's own order and headline.

    For uploading to job boards. Nothing is tailored and nothing is logged. Returns
    ``(docx_path, sidecar_path)``.
    """
    profile = profile or bootstrap.load_profile()
    out_path = out_path or paths.output_dir("templates") / "resume.docx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    no_posting = SimpleNamespace(required=[], nice_to_have=[])
    content = _resume_content(profile, no_posting, profile.identity.headline)
    DocxTailoredResume().render(content, out_path)
    sidecar = write_sidecar(
        out_path, script="generate_resume.py", profile=profile, inputs=[], fit_rating=None
    )
    if check_pages:
        verify_pages("resume", out_path)
    return out_path, sidecar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate-resume", description="Generate a tailored resume DOCX"
    )
    parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    parser.add_argument("--company", help="Override company name used in filename")
    parser.add_argument("--out", type=Path, help="Output DOCX path")
    parser.add_argument(
        "--check-pages",
        action="store_true",
        help="Count the real pages with LibreOffice and fail if over 2 (slow; needs LibreOffice)",
    )
    args = parser.parse_args(argv)

    try:
        require_path(args.jd, "JD file")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    profile = load_profile_or_none()
    if profile is None:
        return 1
    return run_and_report(
        generate_resume,
        args.jd,
        profile=profile,
        company=args.company,
        out_path=args.out,
        check_pages=args.check_pages,
    )


if __name__ == "__main__":
    raise SystemExit(main())
