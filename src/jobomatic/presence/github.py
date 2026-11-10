#!/usr/bin/env python3
"""Generate GitHub profile copy.

Renders the same draft the ``update_github_profile`` SKILL.md workflow produces
conversationally — Bio, Status, Profile README, Profile Fields and Pinned
Repositories, with `{fragment}` substitution and character-limit checks — by
loading the typed presence view for its data (copy fragments, portfolio
projects) and reading the skill's own templates (fenced code blocks and tables
in SKILL.md) for the copy structure, so the two can't drift apart. See
``generate_linkedin.py`` for the fuller version of this pattern.

An earlier version of this script built a README straight from the profile's
summary, differentiators and skills. That leaked internal notes ("course-level"),
split skill lists in the middle of parentheses, and published differentiators
that belong off public profiles (such as legacy platform experience). The
README now comes only from the SKILL.md template.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from jobomatic import bootstrap, paths
from jobomatic.presence.skill_text import fenced_blocks, section_text, substitute_fragments
from jobomatic.profile.copy_fragments import compute_copy_fragments
from jobomatic.profile.model import PresenceView
from jobomatic.provenance import profile_hash, write_sidecar

ROOT = paths.code_root()
SKILL_PATH = ROOT / "skills" / "update_github_profile" / "SKILL.md"
BIO_LIMIT = 160
STATUS_LIMIT = 80


def _is_sparse(view: PresenceView) -> bool:
    """Return True when the profile lacks headline, summary, differentiators, and portfolio."""
    return not any([view.headline, view.summary, view.differentiators, view.projects])


def _template_block(
    skill_text: str, heading: str, label: str, fragments: dict[str, str]
) -> tuple[str, list[str]]:
    """First fenced block under ``heading`` with fragments substituted."""
    section = section_text(skill_text, heading) or ""
    blocks = fenced_blocks(section)
    if not blocks:
        return "", [f"{label} — could not find the template in SKILL.md ({heading})"]
    text = substitute_fragments(blocks[0].strip("\n"), fragments)
    warnings: list[str] = []
    leftover = re.findall(r"\{\w+\}", text)
    if leftover:
        warnings.append(
            f"{label} still contains unfilled placeholders: {', '.join(sorted(set(leftover)))}"
        )
    return text, warnings


def _step1_bio(skill_text: str, fragments: dict[str, str]) -> tuple[str, list[str]]:
    bio, warnings = _template_block(skill_text, "Step 1 — Bio", "Step 1 Bio", fragments)
    if len(bio) > BIO_LIMIT:
        warnings.append(
            f"Step 1 Bio is {len(bio)} chars — over the {BIO_LIMIT} limit, trim before saving"
        )
    return bio, warnings


def _step2_status(skill_text: str, fragments: dict[str, str]) -> tuple[str, str, list[str]]:
    """Return (status text, the Settings block that follows it, warnings)."""
    status, warnings = _template_block(skill_text, "Step 2 — Status", "Step 2 Status", fragments)
    if len(status) > STATUS_LIMIT:
        warnings.append(f"Step 2 Status is {len(status)} chars — over the {STATUS_LIMIT} limit")
    section = section_text(skill_text, "Step 2 — Status") or ""
    settings = ""
    if "**Settings:**" in section:
        settings = section[section.index("**Settings:**") :].split("\n> ")[0].strip()
    return status, settings, warnings


def _step3_readme(skill_text: str, fragments: dict[str, str]) -> tuple[str, list[str]]:
    return _template_block(skill_text, "Step 3 — Profile README", "Step 3 README", fragments)


def _section_body(skill_text: str, heading: str) -> str:
    return (section_text(skill_text, heading) or "").strip()


def _step5_pins(skill_text: str, view: PresenceView) -> tuple[str, list[str]]:
    """The skill's pinning guidance plus the profile's portfolio projects as candidates.

    The view can't tell public repos from private ones, and GitHub only lets
    a profile pin repos visible to everyone, so the candidates are labeled as
    unverified rather than presented as a final pin list.
    """
    warnings: list[str] = []
    guidance = _section_body(skill_text, "Step 5 — Pinned Repositories").rstrip("-\n ")
    lines = [
        guidance,
        "",
        "**Candidates from the profile's portfolio (private repos are left out; confirm each is public before pinning):**",
    ]
    public = [p for p in view.projects if not p.repo_private]
    if public:
        for p in public:
            lines.append(f"- {p.name} — {p.url}")
    else:
        lines.append("- (no portfolio projects in the profile)")
        warnings.append("Step 5 — no portfolio projects in the profile to suggest as pins")
    return "\n".join(lines), warnings


def _build_draft(view: PresenceView, skill_text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    char_limits = section_text(skill_text, "Character Limits") or ""
    fragments = compute_copy_fragments(
        view.differentiators, view.certifications, view.coursework_summary
    )

    bio, w = _step1_bio(skill_text, fragments)
    warnings.extend(w)
    status, settings, w = _step2_status(skill_text, fragments)
    warnings.extend(w)
    readme, w = _step3_readme(skill_text, fragments)
    warnings.extend(w)
    fields = _section_body(skill_text, "Step 4 — Profile Fields")
    pins, w = _step5_pins(skill_text, view)
    warnings.extend(w)
    if _is_sparse(view):
        warnings.append("sparse profile — manually review public copy")

    sections = [
        "<!-- GENERATED DRAFT — regenerate via the generate_github MCP tool / "
        "update_github_profile skill.",
        f"     Reflects the public profile data (hash {profile_hash(view)}). -->",
        "",
        "# GitHub Profile Update Draft",
        "",
        "## Character Limits",
        char_limits,
        "",
        "## Step 1 — Bio",
        "```",
        bio,
        "```",
        f"_{len(bio)} / {BIO_LIMIT} chars_",
        "",
        "## Step 2 — Status",
        "```",
        status,
        "```",
        f"_{len(status)} / {STATUS_LIMIT} chars_",
        "",
        settings,
        "",
        "## Step 3 — Profile README",
        "Create or edit the `README.md` in a repo named exactly like your username.",
        "",
        "```markdown",
        readme,
        "```",
        "",
        "## Step 4 — Profile Fields",
        fields,
        "",
        "## Step 5 — Pinned Repositories",
        pins,
        "",
        "## After applying",
        "Once each field above has been pasted into GitHub, update the "
        '"Current State vs Target" diff table in SKILL.md by hand — this draft '
        "has no visibility into what's actually live on GitHub.",
    ]
    return "\n".join(sections), warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate-github", description="Generate GitHub profile copy"
    )
    parser.add_argument(
        "--out", type=Path, help="Output markdown file (default: github-profile-update-draft.md)"
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
    if not view.headline:
        warnings.append("no profile headline — SKILL.md copy used as-is")

    out_file = (
        args.out
        or paths.output_dir("profiles", platform="github") / f"{date.today().isoformat()}.md"
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
        script="generate_github.py",
        profile=view,
        inputs=[],
        evidence_sources=[p.name for p in view.projects],
        warnings=warnings,
    )
    print(f"Wrote {out_file}")
    print(f"Wrote {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
