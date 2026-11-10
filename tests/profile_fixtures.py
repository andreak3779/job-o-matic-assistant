"""A small fictional profile for the profile-module tests."""

from __future__ import annotations

import datetime as dt

from jobomatic.profile.model import (
    Certification,
    DomainCoverage,
    Education,
    Gap,
    Identity,
    KeywordGroup,
    Profile,
    Project,
    Role,
    Rules,
    SkillGroup,
    Skills,
    Story,
    Visibility,
)


def sample_profile(**overrides) -> Profile:
    data = {
        "identity": Identity(
            name="Sarah Ashford",
            email="sarah.ashford.dev@example.com",
            phone="(410) 555-0142",
            location="Springfield, MD",
            headline="Full-Stack .NET Developer",
            summary="Builds web apps.",
            differentiators=["Full-stack depth"],
            domain_experience=["Worked in a ten-person team"],
        ),
        "roles": [
            Role(
                title="Developer",
                company="Acme Health",
                dates="2020 - Present",
                bullets=["Built X"],
            ),
            Role(
                title="Programmer",
                company="Northwind Traders",
                dates="2004 - 2009",
                tier="legacy",
                visibility=Visibility.PRIVATE,
            ),
        ],
        "education": [Education(institution="Lakeshore Polytechnic", credential="Diploma")],
        "certifications": [
            Certification(
                code="AZ-900",
                status="certified",
                date=dt.date(2026, 4, 18),
                credential_url="https://learn.example.com/x",
                visibility=Visibility.PUBLIC,
            ),
            Certification(
                code="AI-200",
                status="in_progress",
                visibility=Visibility.PUBLIC,
                domain_coverage=[DomainCoverage(domain="RAG", status="Partial")],
            ),
            Certification(code="OTHER-1", status="certified", date=dt.date(2025, 1, 1)),
        ],
        "coursework_summary": "10 courses completed",
        "skills": Skills(
            groups=[SkillGroup(category="Backend", skills=["C#", "SQL"])],
            keywords=[KeywordGroup(group="Cloud", keywords=["Azure"])],
            gaps=[
                Gap(skill="kubernetes", severity="genuine", evidence="course", notes="course only")
            ],
        ),
        "projects": [
            Project(
                name="CookingTime", url="https://github.com/example/CookingTime", description="Demo"
            )
        ],
        "stories": [Story(title="Pipeline ownership", situation="Releases were slow")],
        "rules": Rules(),
    }
    data.update(overrides)
    return Profile(**data)


# -- builders for tests that need a small, specific profile ------------------------------------
#
# These accept the field names the tests used when the profile was a profile (``experience``,
# ``cert_registry``, ``ats_keywords`` ...) so a test can describe just what it cares about.


def WorkExperience(**fields):  # noqa: N802 - reads like the record it builds
    return Role(**fields)


def SkillCategory(category: str, skills: list[str]) -> SkillGroup:  # noqa: N802
    return SkillGroup(category=category, skills=skills)


def StarStory(**fields) -> Story:  # noqa: N802
    return Story(**fields)


def Cert(**fields) -> Certification:  # noqa: N802
    return Certification(**fields)


def Contact(**fields) -> Identity:  # noqa: N802
    return _identity(**fields)


def _identity(**fields) -> Identity:
    base = {
        "name": "Test Candidate",
        "email": "test@example.com",
        "phone": "",
        "headline": "",
        "summary": "",
    }
    base.update(fields)
    return Identity(**base)


def make_profile(
    *,
    contact: Identity | None = None,
    headline: str = "Engineer",
    summary: str = "Test",
    experience: list[Role] | None = None,
    legacy_experience: list[Role] | None = None,
    education: list[Education] | None = None,
    technical_skills: list[SkillGroup] | None = None,
    star_stories: list[Story] | None = None,
    cert_registry: list[Certification] | None = None,
    differentiators: list[str] | None = None,
    known_genuine_gaps: list[Gap] | None = None,
    resolved_framing_gaps: list[str] | None = None,
    portfolio_projects: list[Project] | None = None,
    ats_keywords: dict[str, list[str]] | None = None,
    ai200_domain_coverage: list[dict[str, str]] | None = None,
    azure_coursework: str | None = None,
    domain_experience: list[str] | None = None,
    additional_experience: str = "",
) -> Profile:
    """A small profile. Defaults describe a minimal engineer with one Azure skill and one project."""
    base = contact or _identity()
    identity = base.model_copy(
        update={
            "headline": headline,
            "summary": summary,
            "differentiators": differentiators or [],
            "domain_experience": domain_experience or [],
            "additional_experience": additional_experience,
        }
    )
    roles = list(
        experience
        if experience is not None
        else [
            Role(
                title="Engineer",
                company="Contoso",
                location="",
                dates="2023–Present",
                bullets=["Built .NET APIs on Azure"],
            )
        ]
    )
    for old in legacy_experience or []:
        roles.append(old.model_copy(update={"tier": "legacy", "visibility": Visibility.PRIVATE}))
    gaps = list(known_genuine_gaps or []) + [
        Gap(skill=name, severity="resolved") for name in resolved_framing_gaps or []
    ]
    certs = list(cert_registry or [])
    if ai200_domain_coverage:
        coverage = [DomainCoverage(**row) for row in ai200_domain_coverage]
        target = next((c for c in certs if c.code == "AI-200"), None)
        if target is None:
            certs.append(
                Certification(code="AI-200", status="in_progress", domain_coverage=coverage)
            )
        else:
            target.domain_coverage = coverage
    projects = (
        portfolio_projects
        if portfolio_projects is not None
        else [
            Project(
                name="AI Demo",
                description="A demo using OpenAI and Python",
                stack=["python", "openai"],
                url="https://example.com/ai-demo",
                skills_evidence=["python", "openai"],
            )
        ]
    )
    keywords = ats_keywords if ats_keywords is not None else {"ai": ["python", "openai"]}
    return Profile(
        identity=identity,
        roles=roles,
        education=education or [],
        certifications=certs,
        coursework_summary=azure_coursework,
        skills=Skills(
            groups=technical_skills
            if technical_skills is not None
            else [SkillGroup(category="Cloud", skills=["azure"])],
            keywords=[KeywordGroup(group=g, keywords=k) for g, k in keywords.items()],
            gaps=gaps,
        ),
        projects=projects,
        stories=star_stories or [],
    )
