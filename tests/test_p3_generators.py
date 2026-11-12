"""Unit tests for Project 3 presence/identity generators."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jobomatic import paths
from jobomatic.profile.adapters.yaml_vault import YamlVaultProfile
from jobomatic.profile.model import Certification, PresenceView, Project, SkillGroup
from tests.profile_fixtures import make_profile

REPO_ROOT = Path(__file__).resolve().parents[1]

from jobomatic.presence.github import (
    _build_draft as github_build_draft,
)
from jobomatic.presence.github import (
    _is_sparse as github_is_sparse,
)
from jobomatic.presence.github import (
    _step1_bio as github_step1_bio,
)
from jobomatic.presence.github import (
    _step2_status as github_step2_status,
)
from jobomatic.presence.linkedin import (
    _cert_summary,
    _headline,
    _is_sparse,
    _project_hook,
    _step0_headline,
    _step4_skills,
    _step5_certifications,
    _trim_bullets,
)


def _make_view(
    *,
    headline: str | None = None,
    summary: str | None = None,
    differentiators: list[str] | None = None,
    technical_skills: dict[str, list[str]] | None = None,
    portfolio_projects: list[dict[str, Any]] | None = None,
    cert_registry: list[dict[str, Any]] | None = None,
) -> PresenceView:
    """A minimal public view for testing."""
    return PresenceView(
        headline=headline or "",
        summary=summary or "",
        differentiators=differentiators or [],
        skill_groups=[
            SkillGroup(category=c, skills=sk) for c, sk in (technical_skills or {}).items()
        ],
        projects=[
            Project(
                name=p.get("name", ""),
                description=p.get("description", ""),
                stack=p.get("stack", []),
                url=p.get("url", ""),
                repo_private=p.get("private", False),
            )
            for p in (portfolio_projects or [])
        ],
        certifications=[
            Certification(code=c.get("code", ""), status=c.get("status", "in_progress"))
            for c in (cert_registry or [])
        ],
    )


def test_linkedin_headline_uses_profile_headline() -> None:
    view = _make_view(headline="Cloud Engineer | .NET | Azure")
    assert _headline(view) == "Cloud Engineer | .NET | Azure"


def test_linkedin_headline_falls_back_to_summary() -> None:
    view = _make_view(summary="Engineering leader with cloud focus\nMore detail")
    assert _headline(view) == "Engineering leader with cloud focus | Engineering profile"
    assert "Azure" not in _headline(view)
    assert ".NET" not in _headline(view)


def test_linkedin_headline_falls_back_when_empty() -> None:
    view = _make_view()
    assert _headline(view) == "Engineering leader | Engineering profile"


def test_linkedin_is_sparse() -> None:
    assert _is_sparse(_make_view()) is True
    assert _is_sparse(_make_view(headline="H")) is False
    assert _is_sparse(_make_view(summary="S")) is False
    assert _is_sparse(_make_view(differentiators=["D"])) is False
    assert _is_sparse(_make_view(portfolio_projects=[{"name": "P"}])) is False


def test_linkedin_cert_summary_phrasing() -> None:
    view = _make_view(
        cert_registry=[
            {"code": "AZ-104", "status": "certified"},
            {"code": "AI-200", "status": "in_progress"},
        ]
    )
    summary = _cert_summary(view)
    assert "Certified: AZ-104" in summary
    assert "Preparing for: AI-200" in summary
    assert "In progress" not in summary


_STEP5_SKILL_TEXT = (
    "## Step 5 — Certifications\n\n"
    "**Do NOT add AI-200 manually** — it hasn't been earned (the exam is on hold). "
    "Wait for Microsoft to issue that credential before repeating the steps above.\n\n"
    "## Step 6 — Courses\n"
)


def test_step5_certifications_rewrites_wait_language_once_ai200_is_certified() -> None:
    """The exact regression class that has already bitten this project twice
    per the repo's CLAUDE.md (stale AZ-900/course-count claims outliving the
    facts they described): if the profile says AI-200 is certified but
    SKILL.md's template still tells the user to wait, the generator must both
    rewrite the section and surface a loud warning, not silently keep telling
    the user to wait on a credential they already have."""
    cert_rows = [("AI-200", "**Certified August 20, 2026** — [Credential](https://example.com)")]
    section, warnings = _step5_certifications(_STEP5_SKILL_TEXT, cert_rows)
    assert any("shows Certified in the profile" in w for w in warnings)
    assert "Do NOT add AI-200 manually" not in section
    assert "AI-200 is certified with a live credential" in section


def test_step5_certifications_leaves_wait_language_when_still_in_progress() -> None:
    cert_rows = [("AI-200", "**Active target** — in progress")]
    section, warnings = _step5_certifications(_STEP5_SKILL_TEXT, cert_rows)
    assert warnings == []
    assert "Do NOT add AI-200 manually" in section


def test_trim_bullets_drops_low_skill_bullets_not_the_bottom_of_the_list() -> None:
    """The old trim popped from the bottom of the list, which dropped the
    on-call, Agile and API-integration bullets that sit late in a role. The
    trim must instead drop the bullets that mention the fewest pinned skills,
    and leave the survivors in their original order."""
    bullets = [
        "Generic filler about maintaining things " + "x" * 700,
        "Managed CI/CD deployments through GitLab pipelines " + "y" * 700,
        "Created unit and integration tests using xUnit and Moq " + "z" * 700,
        "Short generic bullet",
    ]
    kept = _trim_bullets(bullets, ["CI/CD", "GitLab", "xUnit", "Moq"], limit=1700)
    assert kept == [bullets[1], bullets[2]]


def test_trim_bullets_is_a_noop_when_already_under_the_limit() -> None:
    bullets = ["one", "two", "three"]
    assert _trim_bullets(bullets, ["C#"], limit=2000) == bullets


def test_project_hook_uses_curated_hook_and_flags_unknown_projects() -> None:
    known = SimpleNamespace(name="CookingTime", stack=["C#"])
    hook, curated = _project_hook(known)
    assert curated is True
    assert "118 automated tests" in hook

    unknown = SimpleNamespace(name="NewRepo", stack=["Go", "gRPC", "Postgres", "Docker"])
    hook, curated = _project_hook(unknown)
    assert curated is False
    assert hook == "Go, gRPC, Postgres"


_STEP4_SKILL_TEXT = (
    "## Step 4 — Skills\n\n"
    "```\n1. C#\n2. ASP.NET Core\n```\n\n"
    "```\n" + "\n".join(f"Skill {i}" for i in range(60)) + "\n```\n\n"
    "## Step 5 — Certifications\n"
)


def test_step4_skills_never_exceeds_linkedins_50_skill_cap() -> None:
    text, warnings = _step4_skills(_STEP4_SKILL_TEXT, {})
    assert text.count("\n- ") == 45  # 5 pinned + 45 listed = 50
    assert "Skill 44" in text and "Skill 45" not in text
    assert any("cut to 45" in w for w in warnings)


def test_step0_headline_reads_template_and_flags_overlength() -> None:
    skill = "## Headline\n\n```\n" + "H" * 230 + "\n```\n\n## Step 1 — About Section\n"
    headline, warnings = _step0_headline(skill, _make_view(headline="Fallback"))
    assert headline == "H" * 230
    assert any("over the 220 limit" in w for w in warnings)

    headline, warnings = _step0_headline(
        "## Step 1 — About Section\n", _make_view(headline="Fallback")
    )
    assert headline == "Fallback"
    assert any("no headline template" in w for w in warnings)


def test_github_is_sparse() -> None:
    assert github_is_sparse(_make_view()) is True
    assert github_is_sparse(_make_view(summary="S")) is False


_GITHUB_SKILL_TEXT = (
    "## Character Limits\n| Field | Limit |\n|---|---|\n| Bio | 160 chars |\n\n"
    "## Step 1 — Bio\n\n```\nFull-stack dev | {cert_status_short}\n```\n\n"
    "## Step 2 — Status\n\n```\nOpen to work\n```\n\n"
    "**Settings:**\n- Emoji: 🚀\n\n> note after settings\n\n"
    "## Step 3 — Profile README\n\n```markdown\n## Hi, I'm Jordan\n\n"
    "**Currently:** {cert_status_short}\n```\n\n"
    "## Step 4 — Profile Fields\n| Field | Value |\n|---|---|\n| Name | Jordan |\n\n"
    "## Step 5 — Pinned Repositories\nPick repos.\n\n---\n\n"
    "## Post-Exam Update Checklist\nlater\n"
)


def _github_view(**kwargs: Any) -> PresenceView:
    """``_make_view`` with the fields the full draft builder reads."""
    return _make_view(**kwargs)


def test_github_readme_template_survives_a_heading_inside_its_code_block() -> None:
    """The README template contains its own '## Hi, I'm ...' line. The section
    parser used to treat that as a new section, which emptied the README block
    in the generated draft."""
    draft, warnings = github_build_draft(_github_view(headline="H"), _GITHUB_SKILL_TEXT)
    assert "## Hi, I'm Jordan" in draft
    assert "**Currently:**" in draft
    assert not any("could not find" in w for w in warnings)


def test_github_draft_fills_fragments_and_leaves_no_placeholders() -> None:
    draft, warnings = github_build_draft(_github_view(headline="H"), _GITHUB_SKILL_TEXT)
    assert "{cert_status_short}" not in draft
    assert not any("unfilled placeholders" in w for w in warnings)


def test_github_draft_never_publishes_profile_differentiators_or_skill_chips() -> None:
    """The old README builder dumped the profile's differentiators (including
    legacy platform experience and internal 'course-level' notes) and its
    skill lists onto the public profile. The draft must come from the SKILL.md
    template only."""
    view = _github_view(
        headline="H",
        differentiators=["PowerBuilder, Sybase, and DB2 production experience (course-level)"],
        technical_skills={"Backend": ["C# (Generics", "Delegates)"]},
    )
    draft, _ = github_build_draft(view, _GITHUB_SKILL_TEXT)
    assert "PowerBuilder" not in draft
    assert "course-level" not in draft
    assert "What sets me apart" not in draft


def test_github_bio_and_status_flag_over_limit_copy() -> None:
    long_skill = _GITHUB_SKILL_TEXT.replace(
        "Full-stack dev | {cert_status_short}", "B" * 170
    ).replace("```\nOpen to work\n```", "```\n" + "S" * 90 + "\n```")
    _, bio_warnings = github_step1_bio(long_skill, {})
    assert any("over the 160 limit" in w for w in bio_warnings)
    _, _, status_warnings = github_step2_status(long_skill, {})
    assert any("over the 80 limit" in w for w in status_warnings)


def test_github_main_writes_sidecar_with_evidence(tmp_path: Path) -> None:
    import jobomatic.presence.github as github_module

    sparse = make_profile(
        headline="",
        summary="",
        experience=[],
        technical_skills=[],
        portfolio_projects=[],
        ats_keywords={},
    )
    YamlVaultProfile(paths.profile_dir()).save(sparse)

    out_file = tmp_path / "GitHub_Readme.md"
    rc = github_module.main(["--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()
    sidecar_path = out_file.with_suffix(out_file.suffix + ".meta.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["script"] == "generate_github.py"
    assert sidecar["evidence_sources"] == []
    assert any("sparse" in w for w in sidecar["warnings"])


def test_github_pin_candidates_skip_private_repos() -> None:
    """A private repo can't be pinned and its URL 404s for recruiters."""
    view = _github_view(
        headline="H",
        portfolio_projects=[
            {"name": "PublicRepo", "url": "https://github.com/x/PublicRepo"},
            {"name": "SecretRepo", "url": "https://github.com/x/SecretRepo", "private": True},
        ],
    )
    draft, _ = github_build_draft(view, _GITHUB_SKILL_TEXT)
    assert "PublicRepo" in draft
    assert "SecretRepo" not in draft
