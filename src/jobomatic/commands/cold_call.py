#!/usr/bin/env python3
"""Generate a cold-call (unsolicited) cover-letter DOCX from the profile profile."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt

from jobomatic import bootstrap, paths
from jobomatic.commands.support import (
    DocumentData,
    gate_location,
    produce_document,
    require_path,
    say,
)
from jobomatic.documents.adapters.docx_layout import (
    BODY_SIZE,
    add_paragraph,
    bullet_label_para,
    clean_stack,
    letter_footer,
    letter_header,
    section_heading,
    split_label_body,
)
from jobomatic.fit.engine import FitResult, rate_parsed_jd
from jobomatic.fit.parser import looks_unknown, parse_jd
from jobomatic.provenance import write_sidecar
from jobomatic.results import CommandResult, Message, emit


def _read_target_description(jd_path: Path | None) -> tuple[str, str]:
    """Return (company, description) from a target file if one is supplied (see ``_describe``)."""
    if jd_path is None:
        return _describe(None, None)
    return _describe(jd_path.read_text(encoding="utf-8"), jd_path)


def _describe(text: str | None, source: Path | None) -> tuple[str, str]:
    """Return (company, description) from a target posting if one is supplied.

    The posting is optional: cold outreach is usually conversational, with no JD in hand (see
    ``--recruiter-name``/``--role-type`` on ``main()``). If it is markdown (a ``.md`` file, or text
    that was pasted in, which has no file name) with a real company and title, parse it like a JD
    to get those fields. Otherwise the description is empty (or the raw text, if one was given) and
    the company defaults to ``"Your Company"``.
    """
    if text is None:
        return "Your Company", ""
    if source is None or source.suffix.lower() in (".md", ".markdown"):
        parsed = parse_jd(text)
        # If parse_jd found a real company AND a real title, treat it as a proper JD. A blank
        # ``**Company:**`` line parses to "" which we treat the same as "Unknown Company".
        if not looks_unknown(parsed.company) and not looks_unknown(parsed.title):
            return parsed.company, text
    return "Your Company", text


def _select_evidence(profile: Any, company: str, role_type: str | None = None) -> dict[str, Any]:
    """Pick a short hook, 2–3 bring-items, and a closing for a cold outreach.

    All claims are sourced from the profile (differentiators, technical-skills
    categories, and portfolio projects). No JD-specific assertions are made.
    ``role_type`` (e.g. "Senior .NET Developer roles") names the kind of role
    being sought — the cold-outreach skill's actual intake question — and is
    threaded into the hook so the letter isn't purely company-generic.
    """
    top_differentiators = profile.identity.differentiators[:3]
    has_portfolio = bool(profile.projects)
    has_differentiators = bool(top_differentiators)

    differentiator_text = (
        "; ".join(top_differentiators) if top_differentiators else profile.identity.headline
    )
    role_clause = f" for {role_type}" if role_type else ""

    if has_differentiators or has_portfolio:
        hook = (
            f"I'm a {profile.identity.headline}, and {company} looks like a place where my work "
            f"could fit. I wanted to introduce myself in case you're hiring{role_clause}. "
            f"A few things about me: {differentiator_text}."
        )
    else:
        hook = (
            f"I'm a {profile.identity.headline}, and I'm interested in what {company} is building. "
            f"I'd like a quick chat about opportunities{role_clause} where my background could help."
        )

    # Bring: top differentiators split into (label, body) using the shared
    # separator-aware helper. Cap at 3 items.
    bring: list[dict[str, str]] = []
    for diff in top_differentiators:
        label, body = split_label_body(diff)
        bring.append({"label": label, "body": body})
        if len(bring) >= 3:
            break

    # Fallback if differentiators are sparse: list technical-skill categories
    # without claiming hands-on production experience for every keyword.
    if not bring and profile.skills.groups:
        cat = profile.skills.groups[0]
        skills = ", ".join(cat.skills[:4])
        bring.append({"label": cat.category, "body": f"Background includes {skills}."})

    # Portfolio highlight (one only, cold letters stay short).
    portfolio_highlight = ""
    if has_portfolio:
        project = profile.projects[0]
        stack = clean_stack(project.stack, limit=3)
        portfolio_highlight = (
            f"A recent example is {project.name}, built with {stack}, where {project.description[:140].rstrip('.')}..."
            if stack
            else f"A recent example is {project.name}, where {project.description[:160].rstrip('.')}..."
        )

    closing = (
        f"I'd like to hear what {company} is working on and where I might help. "
        f"Would you have 15 minutes for an intro call?"
    )

    evidence_sources = []
    if has_portfolio:
        evidence_sources.append(profile.projects[0].name)
    evidence_sources.extend(
        label for label, _ in (split_label_body(d) for d in top_differentiators)
    )

    low_confidence = not has_differentiators and not has_portfolio

    return {
        "bring": bring,
        "hook": hook,
        "portfolio_highlight": portfolio_highlight,
        "closing": closing,
        "evidence_sources": evidence_sources,
        "low_confidence": low_confidence,
    }


def _empty_fit_result() -> FitResult:
    """Honest ``FitResult`` for cold calls where we couldn't parse a JD.

    We deliberately do NOT rate the candidate against their own headline
    (that's a self-fit and always Strong), nor against an arbitrary fallback
    — the rating would be noise. Return ``"Stretch"`` as a reasonable default
    since cold outreach is by definition speculative.
    """
    return FitResult(
        rating="Stretch",
        required=[],
        nice_to_have=[],
        rationale="No JD provided — fit not assessed.",
    )


def generate_cold_call_letter(
    jd_path: Path | None = None,
    *,
    profile: Any | None = None,
    company: str | None = None,
    recruiter_name: str | None = None,
    role_type: str | None = None,
    out_path: Path | None = None,
    notes: list[Message] | None = None,
) -> tuple[Path, Path, FitResult]:
    """Build and write a cold-call cover-letter DOCX plus provenance sidecar, from a target file.

    ``jd_path`` is optional; see ``generate_cold_call_letter_from_text``.
    """
    return generate_cold_call_letter_from_text(
        jd_path.read_text(encoding="utf-8") if jd_path is not None else None,
        source=jd_path,
        profile=profile,
        company=company,
        recruiter_name=recruiter_name,
        role_type=role_type,
        out_path=out_path,
        notes=notes,
    )


def generate_cold_call_letter_from_text(
    jd_text: str | None = None,
    *,
    source: Path | None = None,
    profile: Any | None = None,
    company: str | None = None,
    recruiter_name: str | None = None,
    role_type: str | None = None,
    out_path: Path | None = None,
    notes: list[Message] | None = None,
) -> tuple[Path, Path, FitResult]:
    """Build and write a cold-call cover-letter DOCX plus provenance sidecar.

    The posting is optional — cold outreach is normally conversational, with no JD in hand. If one
    is given and contains a company description, we use it; otherwise (the common case) supply
    ``recruiter_name``/``role_type`` directly instead of synthesizing a throwaway JD just to invoke
    this function. ``source`` is where it came from, recorded in the sidecar (``None`` if pasted).
    """
    profile = profile or bootstrap.load_profile()

    target_company, description = _describe(jd_text, source)
    company = company or target_company

    # Compute a fit rating against the description so the sidecar is meaningful.
    # Only record the JD as an input when we actually parsed real skills from it.
    parsed = parse_jd(description)
    if parsed.required:
        result = rate_parsed_jd(parsed, profile)
        sidecar_inputs = [str(source)] if source else []
    else:
        # No parseable JD skills — don't rate the candidate against themselves.
        result = _empty_fit_result()
        sidecar_inputs = []

    evidence = _select_evidence(profile, company, role_type)

    if out_path is None:
        out_path = (
            paths.output_dir("outreach", day=date.today(), company=company) / "cold-outreach.docx"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    letter_header(
        doc,
        profile.identity,
        company=company,
        tagline=profile.identity.headline,
        salutation=f"Dear {recruiter_name}," if recruiter_name else "Dear Hiring Team,",
        re_line=f"Re: {role_type} Opportunities" if role_type else None,
    )

    add_paragraph(doc, evidence["hook"], size=BODY_SIZE, space_before=Pt(8))

    section_heading(doc, "Why I’m a Fit")
    for item in evidence["bring"]:
        bullet_label_para(doc, item["label"], item["body"])

    if evidence["portfolio_highlight"]:
        add_paragraph(
            doc,
            evidence["portfolio_highlight"],
            size=BODY_SIZE,
            space_before=Pt(6),
        )

    add_paragraph(doc, evidence["closing"], size=BODY_SIZE, space_before=Pt(8))
    letter_footer(doc, profile.identity)

    doc.save(str(out_path))

    if evidence["low_confidence"]:
        say(
            notes,
            "warning",
            "cold-call letter has no differentiators or portfolio projects; "
            "draft is generic — manually review before sending.",
        )

    sidecar = write_sidecar(
        out_path,
        script="generate_cold_call_letter.py",
        profile=profile,
        inputs=sidecar_inputs,
        fit_rating=result.rating,
        evidence_sources=evidence["evidence_sources"],
        warnings=["low evidence — manually review before sending"]
        if evidence["low_confidence"]
        else [],
    )
    return out_path, sidecar, result


def run(
    jd_text: str | None = None,
    *,
    source: Path | None = None,
    company: str | None = None,
    recruiter_name: str | None = None,
    role_type: str | None = None,
    out: Path | None = None,
) -> CommandResult[DocumentData]:
    """Write the cold-call letter. Given a posting, a location Pass refuses it (skill fit does
    not: this letter is not an application)."""
    return produce_document(
        gate_without_profile=(lambda notes: gate_location(jd_text, notes)) if jd_text else None,
        make=lambda profile, notes: generate_cold_call_letter_from_text(
            jd_text,
            source=source,
            company=company,
            recruiter_name=recruiter_name,
            role_type=role_type,
            out_path=out,
            notes=notes,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate-cold-call",
        description="Generate a short cold-call cover-letter DOCX",
    )
    parser.add_argument(
        "jd",
        type=Path,
        nargs="?",
        default=None,
        help="Optional path to a target company description or JD markdown file. "
        "Cold outreach is usually conversational — omit this and use "
        "--recruiter-name/--role-type instead.",
    )
    parser.add_argument("--company", help="Override company name used in filename and salutation")
    parser.add_argument(
        "--recruiter-name", help='Salutation name, e.g. "Jane Doe" (default: "Hiring Team")'
    )
    parser.add_argument("--role-type", help='Target role type, e.g. "Senior .NET Developer roles"')
    parser.add_argument("--out", type=Path, help="Output DOCX path")
    args = parser.parse_args(argv)

    if args.jd is not None:
        try:
            require_path(args.jd, "JD file")
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    return emit(
        run(
            args.jd.read_text(encoding="utf-8") if args.jd is not None else None,
            source=args.jd,
            company=args.company,
            recruiter_name=args.recruiter_name,
            role_type=args.role_type,
            out=args.out,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
