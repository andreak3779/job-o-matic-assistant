"""The profile as markdown text, for skills that read it conversationally.

``profile show`` prints these so a skill can pull in just the part it needs ("facts", one named
section, the whole resume) instead of loading every YAML file. Everything is rendered on demand
from the typed profile; no file is written. The public rendering is built from ``PresenceView``
only, so it cannot contain contact details or anything not marked public.
"""

from __future__ import annotations

from jobomatic.profile.cert_status import cert_status_cell
from jobomatic.profile.copy_fragments import compute_copy_fragments, fragments_block
from jobomatic.profile.model import PresenceView, Profile

Section = tuple[str, str]


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _cert_table(certs: list, coursework: str | None) -> str:
    rows = ["| Cert | Status |", "|---|---|"]
    rows.extend(f"| {c.code} | {cert_status_cell(c)} |" for c in certs)
    if coursework:
        rows.append(f"| Azure coursework | {coursework} |")
    return "\n".join(rows)


def _projects_table(projects: list) -> str:
    rows = "\n".join(
        f"| {p.name} | {' · '.join(p.stack)} | {p.description} | {p.url} |" for p in projects
    )
    return "| Project | Stack | Description | URL |\n|---|---|---|---|\n" + rows


def _experience(roles: list) -> str:
    blocks = []
    for job in roles:
        heading = " | ".join(f for f in (job.company, job.location, job.dates) if f)
        blocks.append(f"### {job.title}\n**{heading}**\n\n" + _bullets(job.bullets))
    return "\n\n".join(blocks)


def facts_sections(profile: Profile) -> list[Section]:
    """Everything a gap analysis or positioning task needs, without the resume prose."""
    ident = profile.identity
    fragments = compute_copy_fragments(
        ident.differentiators, profile.certifications, profile.coursework_summary
    )
    coverage = "\n".join(f"| {d.domain} | {d.status} |" for d in profile.domain_coverage)
    note = (
        ident.domain_experience_note
        or "Employer stage/size is unknown unless listed here; do not infer it."
    )
    return [
        ("Copy Fragments", fragments_block(fragments)),
        ("Cert Registry", _cert_table(profile.certifications, profile.coursework_summary)),
        (
            "Key Differentiators",
            "Surface these when the JD references them:\n" + _bullets(ident.differentiators),
        ),
        (
            "Known Genuine Gaps",
            "These are gaps unless the JD marks them optional:\n"
            + _bullets([g.notes or g.skill for g in profile.genuine_gaps]),
        ),
        (
            "Resolved Framing Gaps — Never Re-flag",
            "Treat all of these as ✅ Strong Match in every gap analysis:\n"
            + _bullets(profile.resolved_gap_names),
        ),
        ("Employer & Industry Context", note + "\n" + _bullets(ident.domain_experience)),
        ("Portfolio Projects", _projects_table(profile.projects)),
        (
            "Skills — ATS Keywords",
            "\n\n".join(f"**{g}:** " + ", ".join(k) for g, k in profile.keyword_map.items()),
        ),
        (
            "AI-200 Domain Coverage",
            "| Domain | Status |\n|--------|--------|\n" + coverage,
        ),
    ]


def resume_section(profile: Profile) -> Section:
    """The resume content: headline, summary, skills, experience, education."""
    ident = profile.identity
    skills = "\n\n".join(f"### {g.category}\n" + ", ".join(g.skills) for g in profile.skills.groups)
    education = _bullets(
        [
            ", ".join(p for p in (e.credential, e.institution, e.dates) if p)
            for e in profile.education
        ]
    )
    parts = [
        f"**{ident.headline}**",
        ident.summary,
        "### Technical Skills\n" + skills,
        "### Professional Experience\n" + _experience(profile.resume_roles),
    ]
    if ident.additional_experience:
        parts.append(f"**Additional Experience:** {ident.additional_experience}")
    if education:
        parts.append("### Education\n" + education)
    return "Resume", "\n\n".join(parts)


def contact_text(profile: Profile) -> str:
    ident = profile.identity
    lines = [
        f"Name: {ident.name}",
        f"Email: {ident.email}",
        f"Phone: {ident.phone}",
        f"Location: {ident.location}",
        f"LinkedIn: {ident.linkedin}",
        f"GitHub: {ident.github}",
        f"Pluralsight: {ident.pluralsight}",
    ]
    return "\n".join(line for line in lines if not line.endswith(": "))


def presence_sections(view: PresenceView) -> list[Section]:
    """The public profile: what LinkedIn, GitHub and job boards may be told."""
    fragments = compute_copy_fragments(
        view.differentiators, view.certifications, view.coursework_summary
    )
    skills = "\n\n".join(f"### {c}\n" + ", ".join(s) for c, s in view.technical_skills.items())
    return [
        ("Copy Fragments", fragments_block(fragments)),
        ("Professional Headline", view.headline),
        ("Summary / About", view.summary),
        ("Cert Status + Badge URLs", _cert_table(view.certifications, None)),
        ("Technical Skills", skills),
        ("Professional Experience", _experience(view.roles)),
        ("Portfolio Projects", _projects_table(view.projects)),
        ("Key Differentiators", _bullets(view.differentiators)),
    ]


def render(sections: list[Section]) -> str:
    return "\n\n---\n".join(f"## {title}\n{body}" for title, body in sections) + "\n"


def pick(sections: list[Section], names: list[str]) -> tuple[list[Section], list[str]]:
    """The named sections (case-insensitive, first match) and the names that were not found."""
    found: list[Section] = []
    missing: list[str] = []
    for name in names:
        match = next((s for s in sections if s[0].lower() == name.lower()), None)
        if match:
            found.append(match)
        else:
            missing.append(name)
    return found, missing
