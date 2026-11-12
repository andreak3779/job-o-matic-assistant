#!/usr/bin/env python3
"""Generate LinkedIn profile copy.

Renders the same rich, 8-step draft the ``update_linkedin_profile`` SKILL.md
workflow produces conversationally — About/Open-to-Work/Experience/Skills/
Certifications/Courses/Featured, with `{fragment}` substitution and
char-limit checks — by loading the typed presence view for its data and
reading the *skill's own* prose templates (fenced code blocks in SKILL.md)
for the copy structure, so the two can't drift apart the way an earlier
audit found hardcoded copies do (see CLAUDE.md, "Skills", on hardcoded facts).

Two sections of the draft (Step 3's portfolio-repo hook clauses, Step 3.5's
over-limit trimming) rely on heuristics rather than real judgment: Step 3 uses
a curated hook per known project (falling back to the project's first stack
items, with a warning), and Step 3.5 drops near-duplicate then shortest bullets
to fit LinkedIn's 2,000-char limit. Step 4's skills come from the curated list
in SKILL.md, because the full derived list runs to several hundred terms.
Alongside the draft, this also writes a ``<draft>.raw-inputs.json`` sidecar
with the untouched source data, so a caller with actual judgment available
(e.g. Claude, reading this tool's response) can re-derive those sections
properly instead of trusting the heuristic output.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from jobomatic import paths
from jobomatic.presence.draft import DraftData, write_draft
from jobomatic.presence.skill_text import derive_skill_terms
from jobomatic.presence.skill_text import fenced_blocks as _fenced_blocks
from jobomatic.presence.skill_text import section_text as _section_text
from jobomatic.presence.skill_text import substitute_fragments as _substitute_fragments
from jobomatic.profile.cert_status import cert_status_rows
from jobomatic.profile.copy_fragments import compute_copy_fragments
from jobomatic.profile.model import PresenceView, Project, Role
from jobomatic.provenance import profile_hash
from jobomatic.results import CommandResult, emit

ROOT = paths.code_root()
SKILL_PATH = ROOT / "skills" / "update_linkedin_profile" / "SKILL.md"
TOP_5_SKILLS = ["C#", "ASP.NET Core", "Angular", "Microsoft Azure", "CI/CD"]

# One-clause hook per known portfolio project for Step 3's "Building portfolio
# projects" bullet. Projects not listed here fall back to their first stack
# items (see ``_project_hook``) and raise a warning so a curated hook gets added.
PORTFOLIO_HOOKS = {
    "CookingTime": ".NET 10 Blazor legacy migration, 118 automated tests, 80% coverage, blocking CI gate",
    "MoviesApp": "Angular SSR + ASP.NET Core, containerized with Docker Compose",
    "career-fit-assistant": "Python MCP server",
    "ai-job-search-workflow": "Claude API + Python job-application automation",
    "Resume_Site": "GitHub Actions CI/CD",
    "awk_linux_scripts": "Linux maintenance scripts",
}
# Terms that matter when screening a resume-style bullet but aren't LinkedIn
# skill tags, so they aren't in SKILL.md's curated skills list. Step 3.5's
# trimming counts them alongside the pinned skills so bullets carrying them
# (TDD with xUnit/Moq, on-call support, root-cause work, Agile, quantified wins) survive.
TRIM_EXTRA_TERMS = [
    "Moq",
    "unit and integration tests",
    "on-call",
    "root cause",
    "Agile",
    "sprint",
    "7×",
]


def _static_featured_links() -> list[tuple[str, str]]:
    """Profile links (GitHub, Pluralsight...) from the vault's ``profile/featured-links.json``."""
    path = paths.profile_dir() / "featured-links.json"
    if not path.is_file():
        return []
    return [(str(title), str(url)) for title, url in json.loads(path.read_text(encoding="utf-8"))]


def _bullet_or_line(text: str) -> str:
    return f"• {text.strip()}" if not text.strip().startswith(("•", "-")) else text.strip()


def _headline(view: PresenceView) -> str:
    if view.headline:
        return view.headline
    summary = view.summary.splitlines()[0] if view.summary else "Engineering leader"
    return f"{summary[:80]} | Engineering profile"


def _is_sparse(view) -> bool:
    return not any([view.headline, view.summary, view.differentiators, view.projects])


def _cert_summary(view) -> str:
    if not view.certifications:
        return ""
    active = [c for c in view.certifications if c.status == "certified"]
    in_progress = [c for c in view.certifications if c.status == "in_progress"]
    parts: list[str] = []
    if active:
        parts.append("Certified: " + ", ".join(c.code for c in active))
    if in_progress:
        parts.append("Preparing for: " + ", ".join(c.code for c in in_progress))
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Typed-view → template-slot adapters. The heavy lifting (fragments, cert
# status text, skill-term cleanup) now lives in shared/ helpers rather than
# being regex-scraped from rendered markdown; this module just wires a
# ``PresenceView`` into the SKILL.md template slots.
# ---------------------------------------------------------------------------


def _skills_categories(technical_skills: dict[str, list[str]]) -> dict[str, str]:
    # Rejoin each category's items into one comma string (undoing the naive,
    # paren-blind comma split the typed model's own parser applies) so
    # ``derive_skill_terms`` can re-split on top-level commas only and strip
    # trailing "(qualifier)" clauses — the same cleanup the old
    # rendered-markdown path did via presence-view.md's flat skills list.
    return {cat: ", ".join(items) for cat, items in technical_skills.items()}


def _experience_meta(job: Role) -> str:
    fields = [f for f in (job.company, job.location, job.dates) if f]
    return f"**{' | '.join(fields)}**" if fields else ""


# ---------------------------------------------------------------------------
# Step builders — each mirrors one "## Step N" section of SKILL.md.
# ---------------------------------------------------------------------------


def _project_hook(project: Project) -> tuple[str, bool]:
    """Return (hook, curated). Falls back to the first three stack items."""
    if project.name in PORTFOLIO_HOOKS:
        return PORTFOLIO_HOOKS[project.name], True
    items = [i.strip() for i in project.stack[:3] if i.strip()]
    return ", ".join(items) or project.name, False


def _clean_course_title(raw: str) -> str | None:
    title = raw.strip()
    title = re.sub(r"\s*completed\b.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\(\d+%.*?\)\s*$", "", title)
    title = re.sub(r"\s*\d+%.*$", "", title)
    title = re.sub(r"\s*in progress.*$", "", title, flags=re.IGNORECASE)
    title = title.strip(" -:")
    if len(title) < 5 or title[:1].isdigit() or title.lower() in {"active target", "certified"}:
        return None
    return title


def _step1_about(skill_text: str, fragments: dict[str, str]) -> tuple[str, list[str]]:
    section = _section_text(skill_text, "Step 1 — About Section") or ""
    blocks = _fenced_blocks(section)
    warnings: list[str] = []
    if not blocks:
        warnings.append("Step 1 — could not find About template in SKILL.md")
        return "", warnings
    about = _substitute_fragments(blocks[0].strip("\n"), fragments)
    if len(about) > 2600:
        warnings.append(
            f"Step 1 About is {len(about)} chars — over the 2,600 limit, trim before pasting"
        )
    return about, warnings


def _step0_headline(skill_text: str, view: PresenceView) -> tuple[str, list[str]]:
    section = _section_text(skill_text, "Headline") or ""
    blocks = _fenced_blocks(section)
    warnings: list[str] = []
    if blocks:
        headline = blocks[0].strip()
    else:
        headline = _headline(view)
        warnings.append("Headline — no headline template in SKILL.md; used the profile headline")
    if len(headline) > 220:
        warnings.append(
            f"Headline is {len(headline)} chars — over the 220 limit, trim before pasting"
        )
    return headline, warnings


def _step2_open_to_work(skill_text: str) -> str:
    section = _section_text(skill_text, "Step 2 — Open to Work Banner") or ""
    return section.strip()


def _step3_experience_entry(
    skill_text: str, fragments: dict[str, str], portfolio: list[Project]
) -> tuple[str, list[str]]:
    section = _section_text(skill_text, "Step 3 — Add Experience Entry") or ""
    blocks = _fenced_blocks(section)
    warnings: list[str] = []
    if not blocks:
        warnings.append("Step 3 — could not find Experience template in SKILL.md")
        return "", warnings
    template = blocks[0]
    hook_parts: list[str] = []
    for p in portfolio:
        hook, curated = _project_hook(p)
        hook_parts.append(f"{p.name} ({hook})")
        if not curated:
            warnings.append(
                f"Step 3 — no curated hook for {p.name}; used its first stack items. "
                "Add one to PORTFOLIO_HOOKS in generate_linkedin.py."
            )
    hooks = ", ".join(hook_parts)
    lines = []
    for line in template.split("\n"):
        if "derive the repo list" in line:
            lines.append(f"- Building portfolio projects on GitHub: {hooks}.")
        else:
            lines.append(line)
    text = _substitute_fragments("\n".join(lines).strip("\n"), fragments)
    if len(text) > 2000:
        warnings.append(
            f"Step 3 Experience entry is {len(text)} chars — over the 2,000 limit, trim before pasting"
        )
    return text, warnings


def _curated_skills(skill_text: str) -> list[str] | None:
    """The curated Step 4 skills list from SKILL.md (second fenced block), if any."""
    section = _section_text(skill_text, "Step 4 — Skills") or ""
    blocks = _fenced_blocks(section)
    if len(blocks) < 2:
        return None
    return [t.strip() for t in blocks[1].split("\n") if t.strip()]


def _trim_bullets(bullets: list[str], priority_terms: list[str], limit: int = 2000) -> list[str]:
    """Shrink ``bullets`` to fit ``limit`` chars without cutting from the bottom.

    Each bullet is scored by how many of ``priority_terms`` (the skills this
    profile is pinning on LinkedIn) it mentions; the lowest-scoring bullet goes
    first, shortest first on a tie, which in practice removes generic or
    duplicated bullets. Survivors keep their original resume order.
    """

    def size(items: list[str]) -> int:
        return len("\n".join(f"- {b}" for b in items))

    terms = [t.lower() for t in priority_terms]

    def score(bullet: str) -> int:
        low = bullet.lower()
        return sum(1 for t in terms if t in low)

    kept = list(bullets)
    while size(kept) > limit and len(kept) > 1:
        victim = min(range(len(kept)), key=lambda k: (score(kept[k]), len(kept[k])))
        kept.pop(victim)
    return kept


def _step3_5_experience_sync(
    experience: list[Role], priority_terms: list[str]
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    parts: list[str] = []
    for role in experience:
        if role.title == "Professional Development & Portfolio Building":
            continue  # owned by Step 3
        bullets = _trim_bullets(list(role.bullets), priority_terms)
        body = "\n".join(f"- {b}" for b in bullets)
        dropped = len(role.bullets) - len(bullets)
        if dropped:
            warnings.append(
                f"Step 3.5 — dropped {dropped} bullet(s) for {role.title} to fit the 2,000-char "
                "limit (fewest pinned-skill mentions first, then the shortest; re-check against the resume before pasting)"
            )
        header = f"### {role.title}"
        meta = _experience_meta(role)
        if meta:
            header += f"\n{meta}"
        parts.append(f"{header}\n\n{body}\n\n_{len(body)} / 2,000 chars_")
    return "\n\n".join(parts), warnings


def _step4_skills(skill_text: str, skills_categories: dict[str, str]) -> tuple[str, list[str]]:
    section = _section_text(skill_text, "Step 4 — Skills") or ""
    blocks = _fenced_blocks(section)
    warnings: list[str] = []
    top5_block = blocks[0] if blocks else "\n".join(TOP_5_SKILLS)
    curated = _curated_skills(skill_text)
    if curated is None:
        # No curated list in SKILL.md: fall back to the derived terms, capped so
        # the draft never exceeds LinkedIn's 50-skill limit.
        warnings.append(
            "Step 4 — no curated skills list in SKILL.md; used derived terms (review before adding)"
        )
        curated = derive_skill_terms(skills_categories, exclude=set(TOP_5_SKILLS))
    room = 50 - len(TOP_5_SKILLS)
    if len(curated) > room:
        warnings.append(
            f"Step 4 — skills list had {len(curated)} terms; cut to {room} (LinkedIn caps skills at 50)"
        )
        curated = curated[:room]
    lines = [
        "**Top 5 to pin (in order):**",
        "```",
        top5_block.strip("\n"),
        "```",
        "",
        f"**Then add ({len(curated)} more, {len(TOP_5_SKILLS) + len(curated)} of 50 total):**",
        "\n".join(f"- {t}" for t in curated),
    ]
    return "\n".join(lines), warnings


_AZ900_EXAM_PREP = "Microsoft Azure Fundamentals (AZ-900): Exam Preparation"
_AI200_EXAM_PREP = "Azure AI Cloud Developer Associate (AI-200): Exam Preparation"


def _status_label(status_cell: str) -> str:
    """The row's leading bold status word (e.g. "Certified April 18, 2026" or
    "Active target"), not the whole notes cell — which contains many other
    bolded course names that can themselves contain the word "Certified"
    (e.g. "Microsoft Certified: Azure Developer Associate (AZ-204)...")."""
    m = re.match(r"^\*\*(.*?)\*\*", status_cell.strip())
    if m:
        return m.group(1)
    # Unbolded cell (a not-pursuing / on-hold note): use only the text before the
    # first " — " so course names later in the notes can't read as a status.
    return status_cell.split(" — ", 1)[0]


def _step5_certifications(
    skill_text: str, cert_rows: list[tuple[str, str]]
) -> tuple[str, list[str]]:
    section = _section_text(skill_text, "Step 5 — Certifications") or ""
    ai200_status = next((s for c, s in cert_rows if c == "AI-200"), "")
    warnings: list[str] = []
    if "certified" in _status_label(ai200_status).lower():
        warnings.append(
            "AI-200 shows Certified in the profile — SKILL.md Step 5 still says wait; add the badge now"
        )
        section = section.replace(
            "**Do NOT add AI-200 manually** — it hasn't been earned (the exam is on hold). "
            "Wait for Microsoft to issue that credential before repeating the steps above.",
            "**AI-200 is certified with a live credential** — add it now via the Microsoft Learn "
            "credentials page → Share → Add to LinkedIn, the same way AZ-900 was added above.",
        )
    return section.strip(), warnings


def _step6_courses(cert_rows: list[tuple[str, str]]) -> str:
    courses: list[str] = []
    for code, status in cert_rows:
        label = _status_label(status).lower()
        if "certified" in label or "progress" in label or "target" in label:
            if code == "AZ-900":
                courses.append(_AZ900_EXAM_PREP)
            elif code == "AI-200":
                courses.append(_AI200_EXAM_PREP)
    ai200_status = next((s for c, s in cert_rows if c == "AI-200"), "")
    for raw in re.findall(r"\*\*(.*?)\*\*", ai200_status):
        title = _clean_course_title(raw)
        if title:
            courses.append(title)
    seen: set[str] = set()
    deduped = []
    for c in courses:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    capped = deduped[:10]
    return "\n".join(f"- {c} — Pluralsight" for c in capped)


def _step7_featured(portfolio: list[Project]) -> str:
    lines: list[str] = []
    for i, p in enumerate(portfolio, start=1):
        desc = ". ".join(p.description.split(". ")[:2]).rstrip(".") + "."
        lines.append(f"{i}. **{p.name}** — {p.url}\n   {desc}")
    offset = len(portfolio)
    for i, (title, url) in enumerate(_static_featured_links(), start=offset + 1):
        lines.append(f"{i}. {title} — {url}")
    return "\n".join(lines)


def _build_rich_draft(view: PresenceView, skill_text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    char_limits = _section_text(skill_text, "Character Limits") or ""
    fragments = compute_copy_fragments(
        view.differentiators, view.certifications, view.coursework_summary
    )
    cert_rows = cert_status_rows(view.certifications)
    # Private repos can't be opened by a recruiter, so they stay out of linked lists.
    public_projects = [p for p in view.projects if not p.repo_private]
    skills_categories = _skills_categories(view.technical_skills)

    headline, w = _step0_headline(skill_text, view)
    warnings.extend(w)
    about, w = _step1_about(skill_text, fragments)
    warnings.extend(w)
    open_to_work = _step2_open_to_work(skill_text)
    exp_entry, w = _step3_experience_entry(skill_text, fragments, public_projects)
    warnings.extend(w)
    priority_terms = TOP_5_SKILLS + (_curated_skills(skill_text) or []) + TRIM_EXTRA_TERMS
    exp_sync, w = _step3_5_experience_sync(view.roles, priority_terms)
    warnings.extend(w)
    skills, w = _step4_skills(skill_text, skills_categories)
    warnings.extend(w)
    certs, w = _step5_certifications(skill_text, cert_rows)
    warnings.extend(w)
    courses = _step6_courses(cert_rows)
    featured = _step7_featured(public_projects)

    sections = [
        "<!-- GENERATED DRAFT — regenerate via the generate_linkedin MCP tool / "
        "update_linkedin_profile skill.",
        f"     Reflects the public profile data (hash {profile_hash(view)}). -->",
        "",
        "# LinkedIn Profile Update Draft",
        "",
        "## Character Limits",
        char_limits,
        "",
        "## Headline",
        "```",
        headline,
        "```",
        f"_{len(headline)} / 220 chars_",
        "",
        "## Step 1 — About Section",
        "```",
        about,
        "```",
        f"_{len(about)} / 2,600 chars_",
        "",
        "## Step 2 — Open to Work Banner",
        open_to_work,
        "",
        "## Step 3 — Add Experience Entry",
        "```",
        exp_entry,
        "```",
        "",
        "## Step 3.5 — Sync Existing Experience Entries",
        exp_sync,
        "",
        "## Step 4 — Skills",
        skills,
        "",
        "## Step 5 — Certifications",
        certs,
        "",
        "## Step 6 — Courses Section",
        courses,
        "",
        "## Step 7 — Featured Section",
        featured,
        "",
        "## After applying",
        "Once each field above has been pasted into LinkedIn, update the "
        '"Current State vs Target" diff table in SKILL.md by hand — this draft '
        "has no visibility into what's actually live on LinkedIn.",
    ]
    return "\n".join(sections), warnings


# ---------------------------------------------------------------------------


def _raw_inputs(view: PresenceView) -> dict[str, Any]:
    """The source data behind the sections that are built with heuristics, written beside the draft."""
    return {
        "note": (
            "Pre-heuristic source data for the sections of the draft built with "
            "heuristics rather than real judgment: Step 3's portfolio-repo hooks and "
            "the full set of derived skill candidates (the draft's Step 4 uses the "
            "curated list in SKILL.md instead, since the derived set is several "
            "hundred terms). An LLM refining the draft should re-derive from this "
            "raw data directly rather than trusting the heuristic output."
        ),
        "portfolio_projects": [p.model_dump(mode="json") for p in view.projects],
        "technical_skills_categories": _skills_categories(view.technical_skills),
    }


def run(out: Path | None = None) -> CommandResult[DraftData]:
    """Write the linkedin profile draft and its sidecar (ADR 0028)."""
    return write_draft(
        platform="linkedin",
        script="generate_linkedin.py",
        skill_path=SKILL_PATH,
        build=_build_rich_draft,
        out=out,
        evidence_sources=lambda view: [p.name for p in view.projects],
        raw_inputs=_raw_inputs,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate-linkedin", description="Generate LinkedIn profile copy"
    )
    parser.add_argument(
        "--out", type=Path, help="Output markdown file (default: linkedin-update-draft.md)"
    )
    args = parser.parse_args(argv)
    return emit(run(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
