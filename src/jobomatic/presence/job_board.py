#!/usr/bin/env python3
"""Generate Indeed & ZipRecruiter profile copy.

Renders the same draft the ``update_job_board_profiles`` SKILL.md workflow
produces conversationally — Headline/Job Title, Summary/About, Skills, and
Job Preferences, with `{fragment}` substitution and a resume-freshness
check — by loading the typed presence view for its data (fragments,
skills) and reading the skill's own prose templates (fenced code blocks /
tables in SKILL.md) for the copy structure, so the two can't drift apart.
See ``generate_linkedin.py`` for the fuller version of this pattern, and
``generate_jobgether.py`` for the near-identical sibling this was built
from — the two platforms share the same profile shape.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from jobomatic import bootstrap, paths
from jobomatic.presence.resume_freshness import resume_freshness_lines
from jobomatic.presence.skill_text import (
    curated_tags,
    derive_skill_terms,
    fenced_blocks,
    section_text,
    substitute_fragments,
)
from jobomatic.profile.copy_fragments import compute_copy_fragments
from jobomatic.profile.model import PresenceView
from jobomatic.provenance import profile_hash, write_sidecar

ROOT = paths.code_root()
SKILL_PATH = ROOT / "skills" / "update_job_board_profiles" / "SKILL.md"
_SKILLS_CAP = 20


def _step1_headline(skill_text: str, fragments: dict[str, str]) -> tuple[str, list[str]]:
    section = section_text(skill_text, "Step 1 — Headline / Job Title") or ""
    blocks = fenced_blocks(section)
    if not blocks:
        return "", ["Step 1 — could not find Headline template in SKILL.md"]
    return substitute_fragments(blocks[0].strip("\n"), fragments), []


def _step2_summary(skill_text: str, fragments: dict[str, str]) -> tuple[str, list[str]]:
    section = section_text(skill_text, "Step 2 — Summary / About") or ""
    blocks = fenced_blocks(section)
    warnings: list[str] = []
    if not blocks:
        warnings.append("Step 2 — could not find Summary/About template in SKILL.md")
        return "", warnings
    summary = substitute_fragments(blocks[0].strip("\n"), fragments)
    if len(summary) > 1500:
        warnings.append(
            f"Step 2 Summary/About is {len(summary)} chars — over the ~1,500-char practical "
            "target (no published hard limit), consider trimming"
        )
    return summary, warnings


def _step3_skills(skill_text: str, technical_skills: dict[str, list[str]]) -> tuple[str, list[str]]:
    """Skill tags from the curated block in SKILL.md.

    Falls back to the first terms derived from the profile (with a warning) when
    SKILL.md has no curated block. The derived terms are in profile order, not
    ranked by relevance, so they are a last resort.
    """
    tags = curated_tags(skill_text, "Step 3 — Skills", cap=_SKILLS_CAP)
    if tags is not None:
        return ", ".join(tags), []
    skills_categories = {cat: ", ".join(items) for cat, items in technical_skills.items()}
    derived = derive_skill_terms(skills_categories, limit=_SKILLS_CAP)
    return ", ".join(derived), [
        "Step 3 — no curated skills block in SKILL.md; used the first profile-derived terms (review before adding)"
    ]


def _step4_job_preferences(skill_text: str) -> str:
    return (section_text(skill_text, "Step 4 — Job Preferences") or "").strip()


def _build_draft(view: PresenceView, skill_text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    char_limits = section_text(skill_text, "Character Limits") or ""
    resume_check = resume_freshness_lines()
    fragments = compute_copy_fragments(
        view.differentiators, view.certifications, view.coursework_summary
    )

    headline, w = _step1_headline(skill_text, fragments)
    warnings.extend(w)
    summary, w = _step2_summary(skill_text, fragments)
    warnings.extend(w)
    skills, w = _step3_skills(skill_text, view.technical_skills)
    warnings.extend(w)
    preferences = _step4_job_preferences(skill_text)

    sections = [
        "<!-- GENERATED DRAFT — regenerate via the generate_job_board MCP tool / "
        "update_job_board_profiles skill.",
        f"     Reflects the public profile data (hash {profile_hash(view)}). -->",
        "",
        "# Indeed & ZipRecruiter Profile Update Draft",
        "",
        "## Character Limits",
        char_limits,
        "",
        "## Resume File Dependency Check",
        "\n".join(f"- {line}" for line in resume_check),
        "",
        "## Step 1 — Headline / Job Title",
        "```",
        headline,
        "```",
        "",
        "## Step 2 — Summary / About",
        "```",
        summary,
        "```",
        f"_{len(summary)} / ~1,500 chars (practical target)_",
        "",
        "## Step 3 — Skills",
        skills,
        "",
        "## Step 4 — Job Preferences",
        preferences,
        "",
        "## After applying",
        "Once each field above has been pasted into Indeed/ZipRecruiter, update the "
        '"Current State vs Target" diff table in SKILL.md by hand — this draft has no '
        "visibility into what's actually live on either site.",
    ]
    return "\n".join(sections), warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate-job-board", description="Generate Indeed & ZipRecruiter profile copy"
    )
    parser.add_argument(
        "--out", type=Path, help="Output markdown file (default: job-board-profile-update-draft.md)"
    )
    args = parser.parse_args(argv)

    if not SKILL_PATH.is_file():
        print(f"ERROR: SKILL.md not found: {SKILL_PATH}", file=sys.stderr)
        return 1
    try:
        view = bootstrap.load_presence_view()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    content, warnings = _build_draft(view, skill_text)

    out_file = (
        args.out
        or paths.output_dir("profiles", platform="job-board") / f"{date.today().isoformat()}.md"
    )
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"ERROR: cannot create output directory {out_file.parent}: {exc}", file=sys.stderr)
        return 1
    try:
        out_file.write_text(content, encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot write output file {out_file}: {exc}", file=sys.stderr)
        return 1

    sidecar = write_sidecar(
        out_file,
        script="generate_job_board.py",
        profile=view,
        inputs=[],
        evidence_sources=[],
        warnings=warnings,
    )
    print(f"Wrote {out_file}")
    print(f"Wrote {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
