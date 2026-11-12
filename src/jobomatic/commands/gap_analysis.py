#!/usr/bin/env python3
"""Generate a markdown gap analysis report from a job description."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from jobomatic.applications import outputs
from jobomatic.commands.support import (
    load_profile_or_none,
    print_wrote,
    require_path,
)
from jobomatic.fit.engine import LOW_CONFIDENCE_MESSAGE, SkillMatch, rate_parsed_jd
from jobomatic.fit.parser import parse_jd
from jobomatic.fit.soft_requirements import LABELS

_STATUS_LABELS = {
    "match": "✅ Match",
    "portfolio": "🟡 Portfolio",
    "course": "🟡 Coursework",
    "legacy": "🕰️ Legacy",
    "gap": "🔴 Gap",
}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _recommendations(required: list[SkillMatch], nice: list[SkillMatch]) -> dict[str, list[str]]:
    """Group skills by recommended next action.

    Required and nice-to-have skills are walked separately (not
    ``required + nice`` with an ``m in nice`` membership check) so each
    lands in a bucket whose rendered text actually describes it correctly.
    Two bugs this fixes:

    - A nice-to-have "gap" skill used to land in ``close_with_portfolio``
      alongside genuine required gaps, under report text that explicitly
      calls them "required skills" — mislabeling an optional gap as a
      candidacy blocker.
    - A required skill with portfolio-only evidence matched no branch at
      all (gap/course/"portfolio and in nice" only), so it silently got no
      recommendation whatsoever, despite the report's Framing Gaps section
      already flagging it as needing attention.
    """
    recs: dict[str, list[str]] = {
        "close_with_portfolio": [],
        "close_with_course": [],
        "emphasize_required_portfolio": [],
        "position_as_nice_to_have": [],
        "surface_legacy_experience": [],
    }
    for m in required:
        if m.status == "gap":
            recs["close_with_portfolio"].append(m.skill)
        elif m.status == "course":
            recs["close_with_course"].append(m.skill)
        elif m.status == "portfolio":
            recs["emphasize_required_portfolio"].append(m.skill)
        elif m.status == "legacy":
            recs["surface_legacy_experience"].append(m.skill)
    for m in nice:
        if m.status == "course":
            recs["close_with_course"].append(m.skill)
        elif m.status == "portfolio":
            recs["position_as_nice_to_have"].append(m.skill)
        # A nice-to-have "gap" gets no recommendation bucket: it's already
        # shown correctly in the Nice-to-Have Skills table, and it's
        # optional by definition — not something to "close" the way a
        # required gap is.
    return recs


def _resume_tailoring_priorities(result, recs: dict[str, list[str]]) -> list[str]:
    """Per-application resume actions built from this JD's actual skill names.

    Uses the same recommendation buckets `_recommendations()` already
    computes — not fixed boilerplate — so two JDs with different skill
    profiles produce different priorities.
    """
    actions: list[str] = []
    matched_required = [m.skill for m in result.required if m.status == "match"]
    if matched_required:
        shown = ", ".join(matched_required[:4])
        actions.append(
            f"Lead with production evidence for {shown} — these map directly to required skills."
        )
    if recs["close_with_course"]:
        shown = ", ".join(recs["close_with_course"][:4])
        actions.append(
            f"Upgrade course-only signal to portfolio/production evidence where possible: {shown}."
        )
    if recs["close_with_portfolio"]:
        shown = ", ".join(recs["close_with_portfolio"][:4])
        actions.append(
            f"Close genuine gaps with a focused portfolio spike, or highlight adjacent "
            f"experience if any exists: {shown}."
        )
    if recs.get("emphasize_required_portfolio"):
        shown = ", ".join(recs["emphasize_required_portfolio"][:4])
        actions.append(
            f"Lead with existing portfolio evidence for these required skills — it's real "
            f"evidence, not just coursework: {shown}."
        )
    if recs["position_as_nice_to_have"]:
        shown = ", ".join(recs["position_as_nice_to_have"][:4])
        actions.append(f"Emphasize nice-to-have strengths with portfolio evidence: {shown}.")
    if recs.get("surface_legacy_experience"):
        shown = ", ".join(recs["surface_legacy_experience"][:4])
        actions.append(
            f"Decide whether to add an Earlier Experience addendum for these required skills, "
            f"which only legacy work demonstrates: {shown}."
        )
    if not actions:
        actions.append(
            "No specific tailoring signal found for this JD's parsed requirements — "
            "review the Summary Table above and tailor manually."
        )
    return actions


def _cover_letter_angle(company: str, result) -> str:
    """Hook + proof points + company framing, built from this JD's actual
    matched skills and evidence sources rather than a fixed template sentence."""
    matched_required = [m.skill for m in result.required if m.status == "match"]
    hook_skill = matched_required[0] if matched_required else None
    hook = (
        f"production experience with {hook_skill}"
        if hook_skill
        else "relevant production and portfolio experience"
    )
    sources = result.evidence_sources()
    points = (
        f"proof points from {', '.join(sources[:3])}"
        if sources
        else "2-3 concrete proof points from production or portfolio work"
    )
    gaps = [m.skill for m in result.required if m.status == "gap"]
    gap_clause = f"; a concise plan for closing {', '.join(gaps[:2])}" if gaps else ""
    return f"Hook: {hook}, directly aligned with {company}'s stated requirements; {points}{gap_clause}."


def _sanitize_evidence(evidence: str, max_len: int = 120) -> str:
    """Collapse whitespace and keep evidence strings readable in a markdown table cell."""
    evidence = re.sub(r"\s+", " ", evidence or "").strip()
    if len(evidence) <= max_len:
        return evidence
    truncated = evidence[:max_len].rsplit(" ", 1)[0]
    return truncated + " …"


def _format_header_meta(company: str, location: str | None, job_id: str | None) -> str:
    """ "[Company] — [Location] · [Job ID]", omitting whichever parts are absent."""
    extras = [p for p in (location, job_id) if p]
    return f"{company} — {' · '.join(extras)}" if extras else company


def _render_report(
    title: str,
    company: str,
    result,
    location: str | None = None,
    job_id: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Gap Analysis: {title}")
    lines.append(
        f"**{_format_header_meta(company, location, job_id)}** · {date.today().strftime('%B %Y')}"
    )
    lines.append("")
    lines.append(f"## Overall Fit: {result.rating}")
    lines.append(f"{result.rationale}")
    lines.append("")
    if result.location_disqualifiers or result.location_flags:
        lines.append("## Location & Work Arrangement")
        for reason in result.location_disqualifiers:
            lines.append(f"- 🚫 {reason}")
        for flag in result.location_flags:
            lines.append(f"- ⚠️ {flag}")
        if result.location_disqualified:
            lines.append("")
            lines.append(
                f"**This Pass is driven by location, not skills** (skills alone would rate "
                f"{result.skills_only_rating}). Don't spend learning time closing the gaps "
                "below for this role — they are listed for reference only."
            )
        lines.append("")
    lines.append("## Summary Table")
    lines.append("| Requirement | Status | Evidence |")
    lines.append("|---|---|---|")
    for m in result.required:
        status = _STATUS_LABELS[m.status]
        evidence = _sanitize_evidence(m.evidence)
        lines.append(f"| {m.skill} | {status} | {evidence} |")
    if result.nice_to_have:
        lines.append("")
        lines.append("### Nice-to-Have Skills")
        lines.append("| Skill | Status | Evidence |")
        lines.append("|---|---|---|")
        for m in result.nice_to_have:
            status = _STATUS_LABELS[m.status]
            evidence = _sanitize_evidence(m.evidence)
            lines.append(f"| {m.skill} | {status} | {evidence} |")
    if result.unscored_required:
        lines.append("")
        lines.append("### Required lines not scored")
        lines.append(
            "No recognizable skill was found in these required lines, so the rating above "
            "does not cover them — read each one yourself:"
        )
        for line in result.unscored_required:
            lines.append(f"- {line}")
    if result.low_confidence:
        lines.append("")
        lines.append("### Low-confidence result")
        lines.append(LOW_CONFIDENCE_MESSAGE)
    if result.soft_requirements:
        lines.append("")
        lines.append("### Soft requirements")
        lines.append(
            "Education, years-of-experience, title-level and soft-skill lines. They are listed for you to read and "
            "are never scored or counted as gaps:"
        )
        for soft in result.soft_requirements:
            label = LABELS.get(soft.kind, "Education")
            lines.append(f"- {label} — {soft.note}: {soft.line}")
    if result.terms_to_confirm:
        lines.append("")
        lines.append("### Terms to confirm")
        lines.append(
            "Each of these words is also a skill name. It was read as ordinary English and "
            "not scored. Ask the user which meaning the posting intends:"
        )
        for word, line in result.terms_to_confirm:
            lines.append(f'- "{word}" in: {line}')
    if result.possible_typos:
        lines.append("")
        lines.append("### Possible typos")
        lines.append(
            "Each word is one letter from a skill name, so it may be a typo in the posting. "
            "It was not scored. Check the posting:"
        )
        for word, term, line in result.possible_typos:
            lines.append(f'- "{word}" may be "{term}" in: {line}')
    if result.unknown_names:
        lines.append("")
        lines.append("### Names to check")
        lines.append(
            "The posting names these in a list of examples, but they are not in the skill list, "
            "so they were not scored. Read the posting:"
        )
        for name, line in result.unknown_names:
            lines.append(f'- "{name}" in: {line}')
    lines.append("")
    lines.append("## ✅ Strong Matches")
    for m in result.required + result.nice_to_have:
        if m.status == "match":
            lines.append(f"- **{m.skill}** — {m.evidence}")
    if not any(m.status == "match" for m in result.required + result.nice_to_have):
        lines.append("- None identified")
    lines.append("")
    lines.append("## 🟡 Framing Gaps")
    for m in result.required:
        if m.status in ("portfolio", "course"):
            lines.append(f"- **{m.skill}** — {m.evidence}")
    if not any(m.status in ("portfolio", "course") for m in result.required):
        lines.append("- None identified")
    lines.append("")
    lines.append("## 🕰️ Legacy Experience")
    lines.append(
        "Only evidenced by legacy work, which is kept off the active resume by default "
        "by design. Surfacing it is a per-application decision."
    )
    for m in result.required:
        if m.status == "legacy":
            lines.append(f"- **{m.skill}** — {m.evidence}")
    if not any(m.status == "legacy" for m in result.required):
        lines.append("- None identified")
    lines.append("")
    lines.append("## 🔴 Genuine Gaps")
    for m in result.required:
        if m.status == "gap":
            lines.append(
                f"- **{m.skill}** — no evidence; consider focused learning or a portfolio spike"
            )
    if not any(m.status == "gap" for m in result.required):
        lines.append("- None identified")
    lines.append("")

    recs = _recommendations(result.required, result.nice_to_have)
    lines.append("## Recommendations")
    if recs["close_with_portfolio"]:
        lines.append("### Close with portfolio evidence")
        lines.append(
            "These required skills are genuine gaps. Pick 1–2 and build or extend a portfolio project that demonstrates them:"
        )
        for skill in recs["close_with_portfolio"]:
            lines.append(f"- {skill}")
        lines.append("")
    if recs["close_with_course"]:
        lines.append("### Close with coursework or lab")
        lines.append(
            "These skills are course-only. Add a small hands-on project or cert lab to upgrade them to portfolio/production evidence:"
        )
        for skill in recs["close_with_course"]:
            lines.append(f"- {skill}")
        lines.append("")
    if recs["emphasize_required_portfolio"]:
        lines.append("### Emphasize portfolio evidence for required skills")
        lines.append(
            "These required skills already have portfolio evidence — lead with it as real, "
            "hands-on experience, not just coursework:"
        )
        for skill in recs["emphasize_required_portfolio"]:
            lines.append(f"- {skill}")
        lines.append("")
    if recs["position_as_nice_to_have"]:
        lines.append("### Emphasize in application narrative")
        lines.append(
            "These nice-to-have skills have portfolio evidence. Mention them explicitly in the cover letter:"
        )
        for skill in recs["position_as_nice_to_have"]:
            lines.append(f"- {skill}")
        lines.append("")
    if recs["surface_legacy_experience"]:
        lines.append("### Decide whether to surface legacy experience")
        lines.append(
            "These required skills are only evidenced in legacy roles. Decide per application whether "
            'to add an "Earlier Experience" resume addendum or a cover-letter mention — never automatically:'
        )
        for skill in recs["surface_legacy_experience"]:
            lines.append(f"- {skill}")
        lines.append("")
    lines.append("## How to Frame the Application")
    lines.append("### Resume tailoring priorities")
    for i, action in enumerate(_resume_tailoring_priorities(result, recs), start=1):
        lines.append(f"{i}. {action}")
    lines.append("")
    lines.append("### Cover letter angle")
    lines.append(_cover_letter_angle(company, result))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gap-analysis", description="Generate a JD gap analysis report"
    )
    parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    parser.add_argument(
        "--out",
        type=Path,
        help="Output markdown file (default: gap-analysis.md in the application's folder)",
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

    jd_text = args.jd.read_text(encoding="utf-8")
    parsed = parse_jd(jd_text)
    result = rate_parsed_jd(parsed, profile)

    located = outputs.locate_application(
        jd_text,
        log=False,
        documents=("gap_analysis",),
        fit_rating=result.rating,
        create_folder=args.out is None,
    )
    out_file = args.out or located.folder / "gap-analysis.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    outputs.report(located)
    try:
        out_file.write_text(
            _render_report(parsed.title, parsed.company, result, parsed.location, parsed.job_id),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"ERROR: failed to write {out_file}: {exc}", file=sys.stderr)
        return 1
    print_wrote(out_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
