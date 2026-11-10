"""Typed profile models: the facts about the candidate (ADR 0014).

Pure domain code: no file access, no network. The YAML adapter builds these from the vault
and ``service.presence_view`` filters them for public surfaces.

Visibility is declared here, once per field, not repeated in the data:

* a field's default comes from its declaration (``Field(..., json_schema_extra=PRIVATE)``);
* a record may override its own visibility with a ``visibility:`` line, for example a legacy
  role, which is never public;
* anything not marked public is private, so a new field cannot leak by being forgotten.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Visibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


# Markers for ``Field(json_schema_extra=...)``. They end up in the generated JSON Schema too.
PUBLIC: dict[str, Any] = {"visibility": Visibility.PUBLIC.value}
PRIVATE: dict[str, Any] = {"visibility": Visibility.PRIVATE.value}


class CertStatus(str, Enum):
    CERTIFIED = "certified"
    IN_PROGRESS = "in_progress"
    NOT_PURSUING = "not_pursuing"


class GapSeverity(str, Enum):
    GENUINE = "genuine"  # a real gap: be honest about it
    RESOLVED = "resolved"  # looked like a gap, is not: never re-flag


class EvidenceLevel(str, Enum):
    PRODUCTION = "production"
    PORTFOLIO = "portfolio"
    COURSE = "course"
    NONE = "none"


# Cert codes that may appear on public surfaces (LinkedIn, GitHub).
PUBLIC_CERTS: frozenset[str] = frozenset({"AZ-900", "AI-200"})


class Record(BaseModel):
    """Base for every stored record: unknown keys are an error, not silently dropped."""

    model_config = ConfigDict(extra="forbid")

    # What this kind of record is when its ``visibility`` is not set. Safe by default.
    default_visibility: ClassVar[Visibility] = Visibility.PRIVATE

    # Record-level override. ``None`` means "use the model's default".
    visibility: Visibility | None = None

    def effective_visibility(self) -> Visibility:
        return self.visibility or self.default_visibility


class Identity(Record):
    """Who the candidate is, how to reach them, and how they position themselves."""

    default_visibility: ClassVar[Visibility] = Visibility.PUBLIC

    # Contact: never on public surfaces.
    name: str = Field(json_schema_extra=PRIVATE)
    email: str = Field(json_schema_extra=PRIVATE)
    phone: str = Field(json_schema_extra=PRIVATE)
    location: str = Field(default="", json_schema_extra=PRIVATE)
    linkedin: str = Field(default="", json_schema_extra=PRIVATE)
    github: str = Field(default="", json_schema_extra=PRIVATE)
    pluralsight: str = Field(default="", json_schema_extra=PRIVATE)

    headline: str = Field(json_schema_extra=PUBLIC)
    summary: str = Field(json_schema_extra=PUBLIC)
    differentiators: list[str] = Field(default_factory=list, json_schema_extra=PUBLIC)

    # Context about past employers and a free-text block: profile only.
    domain_experience: list[str] = Field(default_factory=list, json_schema_extra=PRIVATE)
    domain_experience_note: str = Field(default="", json_schema_extra=PRIVATE)
    additional_experience: str = Field(default="", json_schema_extra=PRIVATE)


class Role(Record):
    """One job. ``tier`` says whether it is inside the resume window or legacy."""

    default_visibility: ClassVar[Visibility] = Visibility.PUBLIC

    title: str = Field(json_schema_extra=PUBLIC)
    # What documents print when it differs from the real title. ``None`` means use ``title``.
    display_title: str | None = Field(default=None, json_schema_extra=PUBLIC)
    company: str = Field(json_schema_extra=PUBLIC)
    location: str | None = Field(default=None, json_schema_extra=PUBLIC)
    dates: str | None = Field(default=None, json_schema_extra=PUBLIC)
    bullets: list[str] = Field(default_factory=list, json_schema_extra=PUBLIC)
    tier: Literal["resume", "legacy"] = Field(default="resume", json_schema_extra=PUBLIC)

    @model_validator(mode="after")
    def _legacy_roles_are_never_public(self) -> Role:
        if self.tier == "legacy" and self.effective_visibility() is Visibility.PUBLIC:
            raise ValueError(f"legacy role {self.company!r} cannot be public")
        return self


class Education(Record):
    default_visibility: ClassVar[Visibility] = Visibility.PRIVATE

    institution: str = Field(default="", json_schema_extra=PRIVATE)
    credential: str = Field(json_schema_extra=PRIVATE)
    dates: str | None = Field(default=None, json_schema_extra=PRIVATE)


class Part(BaseModel):
    """A nested value with no visibility of its own: it is shown exactly when its parent field is."""

    model_config = ConfigDict(extra="forbid")


class DomainCoverage(Part):
    """How well a certification's exam domain is covered by completed learning."""

    domain: str
    status: str


class Certification(Record):
    default_visibility: ClassVar[Visibility] = Visibility.PRIVATE

    code: str = Field(json_schema_extra=PUBLIC)
    status: CertStatus = Field(json_schema_extra=PUBLIC)
    date: dt.date | None = Field(default=None, json_schema_extra=PUBLIC)
    credential_url: str | None = Field(default=None, json_schema_extra=PUBLIC)
    notes: str | None = Field(default=None, json_schema_extra=PUBLIC)
    domain_coverage: list[DomainCoverage] = Field(default_factory=list, json_schema_extra=PUBLIC)

    @model_validator(mode="after")
    def _only_known_public_certs_are_public(self) -> Certification:
        if self.effective_visibility() is Visibility.PUBLIC and self.code not in PUBLIC_CERTS:
            raise ValueError(f"certification {self.code!r} is not allowed on public surfaces")
        return self


class SkillGroup(Record):
    """A category of technical skills as the resume lists them, in resume order."""

    default_visibility: ClassVar[Visibility] = Visibility.PUBLIC

    category: str = Field(json_schema_extra=PUBLIC)
    skills: list[str] = Field(json_schema_extra=PUBLIC)


class KeywordGroup(Record):
    """A group of ATS keywords used to match job descriptions (profile only)."""

    default_visibility: ClassVar[Visibility] = Visibility.PRIVATE

    group: str = Field(json_schema_extra=PRIVATE)
    keywords: list[str] = Field(json_schema_extra=PRIVATE)


class Gap(Record):
    """A skill the candidate lacks (``genuine``) or one that only looks like a gap (``resolved``)."""

    default_visibility: ClassVar[Visibility] = Visibility.PRIVATE

    skill: str = Field(json_schema_extra=PRIVATE)
    severity: GapSeverity = Field(json_schema_extra=PRIVATE)
    evidence: EvidenceLevel = Field(default=EvidenceLevel.NONE, json_schema_extra=PRIVATE)
    notes: str | None = Field(default=None, json_schema_extra=PRIVATE)


class Skills(BaseModel):
    """Everything about skills: resume groups, ATS keywords and known gaps."""

    model_config = ConfigDict(extra="forbid")

    groups: list[SkillGroup] = Field(default_factory=list, json_schema_extra=PUBLIC)
    keywords: list[KeywordGroup] = Field(default_factory=list, json_schema_extra=PRIVATE)
    gaps: list[Gap] = Field(default_factory=list, json_schema_extra=PRIVATE)


class Project(Record):
    default_visibility: ClassVar[Visibility] = Visibility.PUBLIC

    name: str = Field(json_schema_extra=PUBLIC)
    url: str = Field(json_schema_extra=PUBLIC)
    stack: list[str] = Field(default_factory=list, json_schema_extra=PUBLIC)
    description: str = Field(json_schema_extra=PUBLIC)
    skills_evidence: list[str] = Field(default_factory=list, json_schema_extra=PUBLIC)
    # The GitHub repo is private: its URL will not open for a recruiter, so link lists skip
    # it. The project itself is still public evidence. Not the same as ``visibility``.
    repo_private: bool = Field(default=False, json_schema_extra=PUBLIC)


class Story(Record):
    """A Situation/Task/Action/Result story for behavioural questions."""

    default_visibility: ClassVar[Visibility] = Visibility.PRIVATE

    title: str = Field(json_schema_extra=PRIVATE)
    jd_tags: list[str] = Field(default_factory=list, json_schema_extra=PRIVATE)
    use_for: list[str] = Field(default_factory=list, json_schema_extra=PRIVATE)
    situation: str = Field(default="", json_schema_extra=PRIVATE)
    task: str = Field(default="", json_schema_extra=PRIVATE)
    action: str = Field(default="", json_schema_extra=PRIVATE)
    result: str = Field(default="", json_schema_extra=PRIVATE)
    last_used: str | None = Field(default=None, json_schema_extra=PRIVATE)
    used_for: list[str] = Field(default_factory=list, json_schema_extra=PRIVATE)
    adapt_when: list[str] = Field(default_factory=list, json_schema_extra=PRIVATE)


class Rules(BaseModel):
    """Document rules that are data, not prose: what to leave out and how to word headlines.

    Personal values live in the vault's ``rules.yaml``. This model only defines the shape.
    """

    model_config = ConfigDict(extra="forbid")

    headline_forbidden_words: list[str] = Field(default_factory=list, json_schema_extra=PRIVATE)
    headline_required_phrase: str = Field(default="", json_schema_extra=PRIVATE)
    # The first year of the resume window, or ``None`` when every role is in the window.
    resume_window_start: dt.date | None = Field(default=None, json_schema_extra=PRIVATE)
    # Free-form rules that skills read as text.
    notes: list[str] = Field(default_factory=list, json_schema_extra=PRIVATE)


class Profile(BaseModel):
    """The whole profile, loaded from the vault. Immutable in spirit: build a new one to change."""

    model_config = ConfigDict(extra="forbid")

    # Containers pass through; each record decides for itself (see ``Visibility``).
    identity: Identity = Field(json_schema_extra=PUBLIC)
    roles: list[Role] = Field(default_factory=list, json_schema_extra=PUBLIC)
    education: list[Education] = Field(default_factory=list, json_schema_extra=PUBLIC)
    certifications: list[Certification] = Field(default_factory=list, json_schema_extra=PUBLIC)
    # The "Azure coursework" summary line from the certification table (profile and public).
    coursework_summary: str | None = Field(default=None, json_schema_extra=PUBLIC)
    skills: Skills = Field(default_factory=Skills, json_schema_extra=PUBLIC)
    projects: list[Project] = Field(default_factory=list, json_schema_extra=PUBLIC)
    stories: list[Story] = Field(default_factory=list, json_schema_extra=PUBLIC)
    rules: Rules = Field(default_factory=Rules, json_schema_extra=PRIVATE)

    # -- read helpers -----------------------------------------------------------------------
    # Small, pure views that the generators and the fit engine read, so none of them has to
    # know how the YAML files are split.

    @property
    def resume_roles(self) -> list[Role]:
        """Roles inside the resume window, in resume order."""
        return [r for r in self.roles if r.tier == "resume"]

    @property
    def legacy_roles(self) -> list[Role]:
        """Roles older than the resume window: evidence for the fit engine only, never printed."""
        return [r for r in self.roles if r.tier == "legacy"]

    @property
    def genuine_gaps(self) -> list[Gap]:
        return [g for g in self.skills.gaps if g.severity is GapSeverity.GENUINE]

    @property
    def resolved_gap_names(self) -> list[str]:
        return [g.skill for g in self.skills.gaps if g.severity is GapSeverity.RESOLVED]

    @property
    def keyword_map(self) -> dict[str, list[str]]:
        """ATS keywords by group, in file order."""
        return {k.group: k.keywords for k in self.skills.keywords}

    def certification(self, code: str) -> Certification | None:
        return next((c for c in self.certifications if c.code == code), None)

    @property
    def domain_coverage(self) -> list[DomainCoverage]:
        """How well completed learning covers the AI-200 exam domains."""
        cert = self.certification("AI-200")
        return cert.domain_coverage if cert else []


class PresenceView(BaseModel):
    """What may appear on public surfaces (LinkedIn, GitHub, job boards): public fields only.

    Built by ``service.presence_view`` from the visibility filter, so a profile-update generator
    that is handed this cannot reach contact details, employers outside the resume window, or
    anything else not marked public.
    """

    model_config = ConfigDict(extra="forbid")

    headline: str
    summary: str
    differentiators: list[str] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    skill_groups: list[SkillGroup] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
    coursework_summary: str | None = None

    @property
    def technical_skills(self) -> dict[str, list[str]]:
        """Public skill groups as ``{category: [skills]}``, in file order."""
        return {g.category: g.skills for g in self.skill_groups}
