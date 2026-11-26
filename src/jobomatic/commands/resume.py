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
    PDF_HELP,
    Confirmations,
    DocumentData,
    add_confirmation_flags,
    finish_document,
    gate_documents,
    note_logged,
    produce_document,
    require_path,
)
from jobomatic.documents import budget, skim
from jobomatic.documents.adapters.docx_layout import (
    DEFAULT_SIGNATURE_NAME,
)
from jobomatic.documents.adapters.docx_tailored import DocxTailoredResume
from jobomatic.documents.model import (
    ResumeContact,
    ResumeJob,
    ResumeProject,
    SkillLine,
    TailoredResume,
)
from jobomatic.documents.pagefit import fit_resume
from jobomatic.fit.engine import FitResult, profile_has_skill_text, rate_parsed_jd
from jobomatic.fit.parser import parse_jd
from jobomatic.fit.terms import extract_skill_terms
from jobomatic.provenance import write_sidecar
from jobomatic.results import CommandResult, Message, emit

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
    """Technical-skills lines for a reader who skims: the categories the posting names first, and
    in each the posting's own terms first, cut to a line (``documents.skim``)."""
    jd_pool = " ".join(parsed.required + parsed.nice_to_have)
    categories = list(profile.skills.groups)
    categories.sort(
        key=lambda cat: sum(_skill_score(s, jd_pool) for s in cat.skills),
        reverse=True,
    )
    lines: list[SkillLine] = []
    for cat in categories[: skim.SKILL_LINES]:
        ranked = sorted(cat.skills, key=lambda s: -_skill_score(s, jd_pool))  # stable
        kept: list[str] = []
        for skill in ranked:
            if kept and skim.words(", ".join([*kept, skill])) > skim.SKILL_LINE_WORDS:
                break
            kept.append(skill)
        lines.append(SkillLine(label=cat.category, skills=", ".join(kept)))
    return lines


def _subtitle(stack: list[str]) -> str:
    """The first stack items that fit beside a project's name: at most ``PROJECT_SUBTITLE_ITEMS``
    and ``PROJECT_SUBTITLE_CHARS`` characters, always at least the first."""
    shown: list[str] = []
    for item in stack[: budget.PROJECT_SUBTITLE_ITEMS]:
        if shown and len(" · ".join([*shown, item])) > budget.PROJECT_SUBTITLE_CHARS:
            break
        shown.append(item)
    return " · ".join(shown)


def _project_content(profile: Any, parsed: Any) -> list[ResumeProject]:
    """The Selected Projects: the pinned projects first (the work every employer should see), then
    the best matches for the posting, at most ``budget.PROJECTS`` in all.

    A project without ``resume_bullets`` is never used. A private repository shows no link.
    """
    jd_pool = " ".join(parsed.required + parsed.nice_to_have)

    def relevance(project: Any) -> int:
        text = " ".join([project.name, *project.stack, *project.skills_evidence])
        return _bullet_score(text, jd_pool) + sum(
            _bullet_score(b, jd_pool) for b in project.resume_bullets
        )

    usable = [p for p in profile.projects if p.resume_bullets]
    pinned = [p for p in usable if p.resume_pin]
    rest = sorted((p for p in usable if not p.resume_pin), key=relevance, reverse=True)  # stable
    return [
        ResumeProject(
            name=p.name,
            subtitle=_subtitle(p.stack),
            link="" if p.repo_private else p.url.removeprefix("https://").removeprefix("http://"),
            bullets=[
                skim.shorten(b, skim.BULLET_WORDS)
                for b in sorted(
                    p.resume_bullets, key=lambda b: _bullet_score(b, jd_pool), reverse=True
                )[: budget.PROJECT_BULLETS]
            ],
        )
        for p in [*pinned, *rest][: budget.PROJECTS]
    ]


def _job_content(
    profile: Any, parsed: Any, shown_projects: frozenset[str] = frozenset()
) -> list[ResumeJob]:
    """The resume-window roles with their bullets ordered by relevance to the posting.

    A bullet of a self-directed role (no employer) that names a project already shown in Selected
    Projects is left out, so the same work is not on the page twice. If that would empty the role,
    its own bullets are kept.
    """
    jd_pool = " ".join(parsed.required + parsed.nice_to_have)

    def bullets_of(job: Any) -> list[str]:
        own = list(job.bullets)
        if job.company or not shown_projects:
            return own
        kept = [b for b in own if not any(name in b.lower() for name in shown_projects)]
        return kept or own

    return [
        ResumeJob(
            title=job.title,
            company=job.company or "",
            location=job.location or "",
            dates=job.dates or "",
            bullets=[
                skim.shorten(b, skim.BULLET_WORDS)
                for b in sorted(
                    bullets_of(job), key=lambda b: _bullet_score(b, jd_pool), reverse=True
                )[: skim.JOB_BULLETS]
            ],
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
    jd_pool = " ".join(parsed.required + parsed.nice_to_have)
    paragraphs = [
        line.strip()
        for line in ident.summary.splitlines()
        if line.strip() and not _MARKDOWN_RULE.fullmatch(line.strip())
    ]
    # Three lines at most, and the sentences that speak to this posting rather than the first few.
    summary = (
        [
            skim.pick_sentences(
                " ".join(paragraphs),
                skim.SUMMARY_WORDS,
                lambda sentence: _bullet_score(sentence, jd_pool),
            )
        ]
        if paragraphs
        else [""]
    )
    projects = _project_content(profile, parsed)
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
        projects=projects,
        experience=_job_content(profile, parsed, frozenset(p.name.lower() for p in projects)),
        additional_experience=ident.additional_experience.strip(),
        education=_education_lines(profile),
        certifications=_certification_lines(profile),
    )
    # The profile holds every skill and every bullet; a resume is at most two pages, so trim it
    # (oldest role first, never below two bullets) or refuse. ``--check-pages`` measures the result.
    return fit_resume(full)


def _build_tagline(parsed: Any, profile: Any, matched: list[str] | None = None) -> str:
    """The headline: the candidate's own role, then up to three skills the posting names that the
    candidate has evidence for. One line (``documents.skim``), never the posting's own phrases."""
    role = profile.identity.headline.replace("**", "").split("|")[0].strip() or parsed.title
    chosen: list[str] = []
    for term in matched or []:
        low = term.lower()
        if len(term.split()) > 2 or low in role.lower():
            continue
        if any(low in c.lower() or c.lower() in low for c in chosen):
            continue
        chosen.append(term)
        if len(chosen) == 3:
            break
    return f"{role} | {' · '.join(chosen)}" if chosen else role


def _matched_terms(jd_text: str, grounded: list[str]) -> list[str]:
    """Skill names from the posting that the profile backs with evidence, named tools and
    technologies ("Claude Code", "SQL Server") before plain practices ("testing"), each group in
    the posting's own order."""
    found = [
        term
        for term in extract_skill_terms(jd_text)
        if any(term.lower() in g.lower() for g in grounded)
    ]
    return [t for t in found if t != t.lower()] + [t for t in found if t == t.lower()]


def draft_resume(profile: Any, parsed: Any, jd_text: str) -> TailoredResume:
    """The deterministic resume content for a parsed posting: what ``generate-resume`` renders.

    ``render draft`` hands it out as the starting point for a hand-tailored resume (ADR 0035).
    """
    rated = rate_parsed_jd(parsed, profile)
    grounded = [m.skill for m in (*rated.required, *rated.nice_to_have) if m.is_grounded]
    return _resume_content(
        profile, parsed, _build_tagline(parsed, profile, _matched_terms(jd_text, grounded))
    )


def generate_resume(
    jd_path: Path,
    *,
    profile: Any | None = None,
    company: str | None = None,
    out_path: Path | None = None,
    check_pages: bool = False,
    pdf: bool = False,
    notes: list[Message] | None = None,
) -> tuple[Path, Path, FitResult]:
    """Build and write a tailored resume DOCX plus provenance sidecar from a posting file.

    Returns ``(docx_path, sidecar_path, fit_result)``. See ``generate_resume_from_text``.
    """
    return generate_resume_from_text(
        jd_path.read_text(encoding="utf-8"),
        source=jd_path,
        profile=profile,
        company=company,
        out_path=out_path,
        check_pages=check_pages,
        pdf=pdf,
        notes=notes,
    )


def generate_resume_from_text(
    jd_text: str,
    *,
    source: Path | None = None,
    profile: Any | None = None,
    company: str | None = None,
    out_path: Path | None = None,
    check_pages: bool = False,
    pdf: bool = False,
    notes: list[Message] | None = None,
) -> tuple[Path, Path, FitResult]:
    """Build and write a tailored resume DOCX plus provenance sidecar.

    ``source`` is where the posting came from, recorded in the sidecar (``None`` for text that was
    pasted in). The profile is *not* mutated: the JD-specific tagline is used for this document
    only. The content is trimmed to two pages first (or refused), before anything is logged.
    ``check_pages`` then measures the real page count with LibreOffice and raises if it is over.
    ``notes``, when given, collects what would otherwise be printed (see ``say``).
    """
    profile = profile or bootstrap.load_profile()
    parsed = parse_jd(jd_text)
    result = rate_parsed_jd(parsed, profile)
    content = draft_resume(profile, parsed, jd_text)

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
    note_logged(notes, located)

    DocxTailoredResume().render(content, out_path)

    sidecar = write_sidecar(
        out_path,
        script="generate_resume.py",
        profile=profile,
        inputs=[str(source)] if source else [],
        fit_rating=result.rating,
    )
    finish_document("resume", out_path, notes, pdf=pdf, check_pages=check_pages)
    return out_path, sidecar, result


def run(
    jd_text: str,
    *,
    source: Path | None = None,
    company: str | None = None,
    out: Path | None = None,
    check_pages: bool = False,
    pdf: bool = False,
    confirm: Confirmations = Confirmations(),
) -> CommandResult[DocumentData]:
    """Gate the posting (fit, duplicate, pay) and then write the tailored resume (ADR 0003, 0028)."""
    return produce_document(
        gate_with_profile=lambda profile, notes: gate_documents(jd_text, profile, confirm, notes),
        make=lambda profile, notes: generate_resume_from_text(
            jd_text,
            source=source,
            profile=profile,
            company=company,
            out_path=out,
            check_pages=check_pages,
            pdf=pdf,
            notes=notes,
        ),
        pdf=pdf,
    )


def generate_profile_resume(
    *,
    profile: Any | None = None,
    out_path: Path | None = None,
    check_pages: bool = False,
    pdf: bool = False,
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
    finish_document("resume", out_path, pdf=pdf, check_pages=check_pages)
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
    parser.add_argument("--pdf", action="store_true", help=PDF_HELP)
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
            pdf=args.pdf,
            confirm=Confirmations.from_args(args),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
