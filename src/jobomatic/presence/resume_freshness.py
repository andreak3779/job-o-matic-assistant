"""Resume-freshness check shared by the Jobgether and Indeed/ZipRecruiter
profile-update generators.

Both platforms parse an uploaded resume DOCX into most of the candidate
profile, so their SKILL.md workflows open with a "check the resume isn't
stale before writing any field" step. This compares the resume file's own
mtime against the profile YAML files it should reflect — stable across a fresh
`git clone` (checkout stamps every file with the same moment) unlike comparing
against a parsed date string.
"""

from __future__ import annotations

from jobomatic import paths

# The platform-ready (not job-specific) resume lives in the vault's ``outputs/templates/``.
RESUME_GLOB = "resume*.docx"
_SOURCE_FILES = ["identity.yaml", "roles.yaml", "skills.yaml"]


def resume_freshness_lines() -> list[str]:
    """Human-readable report lines for a generated draft's "Resume File
    Dependency Check" section. Never raises if the resume or a source file
    is missing — the resume DOCX lives in a gitignored `outputs/` folder, so
    a fresh checkout legitimately won't have it yet.
    """
    templates = paths.output_dir("templates")
    candidates = sorted(templates.glob(RESUME_GLOB), key=lambda p: p.stat().st_mtime)
    resume_path = candidates[-1] if candidates else templates / RESUME_GLOB
    if not resume_path.is_file():
        return [
            f"Resume file not found at `{resume_path}`.",
            "Run the fullstack_net_profile_resume skill to generate it before uploading.",
        ]

    resume_mtime = resume_path.stat().st_mtime
    stale: list[str] = []
    for name in _SOURCE_FILES:
        source_path = paths.profile_dir() / name
        if not source_path.is_file():
            continue
        if source_path.stat().st_mtime > resume_mtime:
            stale.append(name)

    if stale:
        return [
            f"Resume file (`{resume_path.name}`) is **STALE** — older than: {', '.join(stale)}.",
            "Run the fullstack_net_profile_resume skill to regenerate it before uploading — "
            "the typed fields below only cover headline/summary/skills/preferences, not the "
            "parsed work history the platform builds from the resume itself.",
        ]
    return [
        f"Resume file (`{resume_path.name}`) is current relative to {', '.join(_SOURCE_FILES)}."
    ]
