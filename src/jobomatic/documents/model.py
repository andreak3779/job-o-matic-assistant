"""Content of the part-time documents: exactly what the old Node templates asked you to fill in.

Pure data. A person or Claude writes this as JSON from the posting and the vault's part-time
notes; a renderer turns it into a file. ``python -m jobomatic render schema <kind>``
prints the JSON Schema for each kind.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Content(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Contact(_Content):
    """Exactly as written in the vault's ``private/part-time-constraints.md``."""

    name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    location: str = Field(min_length=1, description="City, ST")


class Strength(_Content):
    label: str = Field(min_length=1)
    body: str = Field(min_length=1)


class PartTimeJob(_Content):
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    dates: str = Field(
        min_length=1, description="'Mon YYYY – Mon YYYY' (a spaced en dash), or one date"
    )
    bullets: list[str] = Field(min_length=1, max_length=2)


class PartTimeResume(_Content):
    """One page, plain words, no tables or columns (ATS-safe)."""

    contact: Contact
    availability: str = Field(min_length=1)
    summary: str = Field(
        min_length=1, description="2 to 3 sentences using the posting's role title"
    )
    strengths: list[Strength] = Field(min_length=1, max_length=5)
    experience: list[PartTimeJob] = Field(min_length=1, description="Reverse chronological")
    software: str = Field(default="", description="Computer skills line, or empty to omit")
    previous_retail: str = Field(default="", description="One undated sentence, or empty to omit")
    education: list[str] = Field(min_length=1, description="No years")


class PartTimeCoverLetter(_Content):
    """A short business letter on one page."""

    contact: Contact
    date: str = Field(min_length=1)
    recipient: list[str] = Field(min_length=1, max_length=4, description="Address block lines")
    re_line: str = Field(min_length=1)
    salutation: str = Field(min_length=1)
    hook: str = Field(min_length=1, description="2 sentences at most; name the role and one fact")
    strengths_intro: str = Field(min_length=1)
    strengths: list[Strength] = Field(min_length=3, max_length=3, description="Exactly three")
    fit_paragraph: str = Field(min_length=1)
    closing: str = Field(min_length=1, description="2 sentences at most; a plain ask for a call")


class ResumeContact(_Content):
    """The header lines of a resume or letter. Links are optional."""

    name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    phone: str = Field(default="")
    location: str = Field(default="")
    linkedin: str = Field(default="")
    github: str = Field(default="")
    pluralsight: str = Field(default="")


class SkillLine(_Content):
    label: str = Field(min_length=1)
    skills: str = Field(min_length=1, description="Comma-separated, most relevant first")


class ResumeJob(_Content):
    title: str = Field(min_length=1)
    company: str = Field(default="", description="Empty for self-directed work")
    location: str = Field(default="")
    dates: str = Field(default="")
    bullets: list[str] = Field(description="Most relevant first")


class TailoredResume(_Content):
    """A resume for one posting (or the platform-ready one): 1 to 2 pages, ATS-safe."""

    contact: ResumeContact
    tagline: str = Field(min_length=1, description="Role and top skills, e.g. 'Role | A · B · C'")
    summary: list[str] = Field(min_length=1, max_length=2)
    skills: list[SkillLine] = Field(min_length=1, description="5 to 7 lines is typical")
    experience: list[ResumeJob] = Field(min_length=1, description="Reverse chronological")
    additional_experience: str = Field(default="", description="One undated line, or empty")
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list, description="Finished lines")


class LetterItem(_Content):
    label: str = Field(min_length=1)
    body: str = Field(min_length=1)


class TailoredCoverLetter(_Content):
    """A one-page cover letter. Strictly one page: keep each part inside its budget."""

    contact: ResumeContact
    tagline: str = Field(default="")
    date: str = Field(default="", description="Empty means today")
    role_title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    hook: str = Field(min_length=1, description="2 sentences at most, not 'I am writing...'")
    bring: list[LetterItem] = Field(min_length=1, max_length=5, description="WHAT I BRING")
    highlights: list[LetterItem] = Field(default_factory=list, max_length=2)
    closing: str = Field(min_length=1, description="2 sentences at most, with a direct ask")


KINDS: dict[str, type[_Content]] = {
    "resume": TailoredResume,
    "cover-letter": TailoredCoverLetter,
    "part-time-resume": PartTimeResume,
    "part-time-cover-letter": PartTimeCoverLetter,
}
