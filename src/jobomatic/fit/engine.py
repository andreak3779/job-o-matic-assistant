"""Deterministic fit-rating engine for job descriptions vs the candidate profile."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from jobomatic.fit.gap_coaching import GapCoachingEntry
from jobomatic.fit.location import LocationAssessment
from jobomatic.fit.parser import ParsedJD, is_prose_requirement
from jobomatic.fit.soft_requirements import LABELS, SoftRequirement, with_education_on_file
from jobomatic.fit.terms import (
    extract_skill_terms,
    satisfied_by,
    some_of_members,
    strip_skill_punctuation,
    umbrella_parts,
)
from jobomatic.profile.model import Profile

MatchStatus = Literal["match", "portfolio", "course", "legacy", "gap"]
Rating = Literal["Strong", "Good", "Worth a try", "Stretch", "Pass"]

# Order used when ranking evidence strength.
EVIDENCE_STATUS_ORDER: tuple[MatchStatus, ...] = ("match", "portfolio", "course", "legacy", "gap")


@dataclass(frozen=True)
class SkillMatch:
    skill: str
    status: MatchStatus
    evidence: str
    core: bool = False
    """A core requirement (ADR 0021): named in the title, early in the list, carrying a years
    figure, or mentioned twice. Only core gaps can make a posting Stretch or Pass by themselves."""
    members: tuple[SkillMatch, ...] = ()
    """The listed names of a "some of" requirement, each rated on its own (ADR 0038). ``skill``
    then names only those that share the evidence shown, so a document claims nothing more."""
    rated_as: MatchStatus | None = None
    """The status the rating counts when it differs from the evidence: one production tool out of a
    "some of" list is truthfully ``match`` but counts as 🟡."""

    @property
    def rating_status(self) -> MatchStatus:
        """What the rating and the fit table count: ``rated_as`` when set, else ``status``."""
        return self.rated_as or self.status

    @property
    def is_grounded(self) -> bool:
        """True when the match is backed by production or portfolio evidence."""
        return self.status in ("match", "portfolio")

    @property
    def evidence_strength(self) -> int:
        """Sort key, lower is stronger: position in ``EVIDENCE_STATUS_ORDER``
        (match, portfolio, course, legacy, gap); an unknown status ranks last."""
        try:
            return EVIDENCE_STATUS_ORDER.index(self.status)
        except ValueError:
            return len(EVIDENCE_STATUS_ORDER)


# More than this share of the required skills showing no evidence marks the result as
# low-confidence (ADR 0021, step C1; the owner's rule). One place, pinned by boundary tests.
LOW_CONFIDENCE_RED_SHARE = 0.5

LOW_CONFIDENCE_MESSAGE = (
    "More than half of the required skills show no evidence. Either the posting is a poor match "
    "or it was misread — read the posting yourself before relying on this rating."
)

# Fewer required skills than this, with required lines the tool could not read a skill from, and
# the rating rests on too little to trust however the few score. A short posting whose few
# skills were all read ("C#, SQL") is not flagged; one read from nothing is.
LOW_CONFIDENCE_MIN_SKILLS = 4
# A posting with at least this many required lines, of which no more than one in this many yielded
# a skill, was probably misread: most of what it asks for is not in the vocabulary.
LOW_CONFIDENCE_MIN_LINES = 4
LOW_CONFIDENCE_LINES_PER_SKILL = 4


@dataclass(frozen=True)
class FitResult:
    rating: Rating
    required: list[SkillMatch]
    nice_to_have: list[SkillMatch]
    rationale: str
    skill_rating: Rating | None = None
    """Rating from skills alone. Differs from ``rating`` only when a location /
    work-arrangement disqualifier forced ``Pass`` (see src/jobomatic/fit/location.py)."""
    location_disqualifiers: tuple[str, ...] = ()
    location_flags: tuple[str, ...] = ()
    unscored_required: tuple[str, ...] = ()
    """Required lines in which no known skill term could be found (the rating
    covers only the scored ``required`` skills). Listed, never dropped."""
    terms_to_confirm: tuple[tuple[str, str], ...] = ()
    """``(word, line)`` pairs: ordinary words that are also skills, read as plain English and
    left unscored. Shown so the user can say which meaning the posting intends."""
    possible_typos: tuple[tuple[str, str, str], ...] = ()
    unknown_names: tuple[tuple[str, str], ...] = ()
    """``(word, term, line)`` triples: a word one letter from a long skill name. Never scored or
    corrected; shown so the user can check the posting."""
    soft_requirements: tuple[SoftRequirement, ...] = ()
    """Education and years-of-experience lines: listed for the user to read, never scored."""
    required_line_count: int = 0
    """How many lines the posting's required section held (soft and unscored ones included)."""

    @property
    def low_confidence_message(self) -> str | None:
        """Why the rating should not be relied on, or ``None``. Never changes the rating.

        Two reasons: no required skill could be read, or fewer than ``LOW_CONFIDENCE_MIN_SKILLS``
        could be while some required line named none; or more than half of those read are 🔴."""
        count = len(self.required)
        # A "some of" row was read from several names, so it is not a thin read.
        read = sum(len(m.members) or 1 for m in self.required)
        unscored = len(self.unscored_required)
        if count == 0 or (read < LOW_CONFIDENCE_MIN_SKILLS and unscored):
            lines = f"{unscored} required line{'s' if unscored != 1 else ''}"
            tail = f", and {lines} named no skill the tool knows" if unscored else ""
            if count == 0:
                return (
                    f"No required skills could be read from this text{tail}. Check that it is a "
                    "job posting, and read it yourself."
                )
            skills = f"{count} required skill{'s' if count != 1 else ''}"
            return (
                f"Only {skills} could be read{tail}. The rating rests on very little — read the "
                "posting yourself before relying on it, and check that the text is a job posting."
            )
        if (
            self.required_line_count >= LOW_CONFIDENCE_MIN_LINES
            and read * LOW_CONFIDENCE_LINES_PER_SKILL <= self.required_line_count
        ):
            return (
                f"Only {count} required skill{'s' if count != 1 else ''} could be read from "
                f"{self.required_line_count} required lines. The rating rests on very little — "
                "read the posting yourself before relying on it."
            )
        gaps = sum(1 for m in self.required if m.status == "gap")
        if gaps / count > LOW_CONFIDENCE_RED_SHARE:
            return LOW_CONFIDENCE_MESSAGE
        return None

    @property
    def low_confidence(self) -> bool:
        """True when ``low_confidence_message`` has a reason. Never changes the rating."""
        return self.low_confidence_message is not None

    @property
    def skills_only_rating(self) -> Rating:
        """The rating the skills alone would earn, ignoring location overrides."""
        return self.skill_rating or self.rating

    @property
    def location_disqualified(self) -> bool:
        return bool(self.location_disqualifiers)

    @property
    def grounded_required(self) -> list[SkillMatch]:
        """Required skills with production or portfolio evidence."""
        return [m for m in self.required if m.is_grounded]

    @property
    def ungrounded_required(self) -> list[SkillMatch]:
        """Required skills with only coursework or no evidence."""
        return [m for m in self.required if not m.is_grounded]

    def evidence_sources(self) -> list[str]:
        """Return a concise, sorted list of evidence labels used in matches.

        Labels are extracted from the portion before the colon (company or
        project name). Multi-line evidence strings are clamped to their first
        line so labels stay short and sidecars remain readable.
        """
        labels: set[str] = set()
        for m in self.required + self.nice_to_have:
            if not m.is_grounded:
                continue
            raw = (m.evidence or "").strip()
            if ":" in raw:
                label = raw.rsplit(":", 1)[0].strip().splitlines()[0]
                labels.add(label)
            elif raw:
                labels.add(raw.splitlines()[0])
        return sorted(labels)


def _load_aliases(path: Path | None = None) -> dict[str, list[str]]:
    """Load the alias registry from src/jobomatic/fit/aliases.json.

    Fails loudly (``ValueError``) on a malformed entry rather than silently
    misinterpreting it — e.g. ``{"C#": "csharp"}`` (a string where a list was
    intended, an easy hand-editing slip) would otherwise iterate the string
    character-by-character, producing bogus single-letter aliases that
    quietly degrade every fit-check/gap-analysis rating with no visible
    error. This is loaded once at import time as a module-level constant, so
    the failure surfaces immediately at process startup instead of as a
    hard-to-trace bad match deep in a rating result.
    """
    if path is None:
        path = Path(__file__).with_name("aliases.json")
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    aliases = data.get("aliases", {})
    for key, vals in aliases.items():
        if not isinstance(vals, list) or not all(isinstance(v, str) for v in vals):
            raise ValueError(f"aliases.json entry {key!r} must be a list of strings, got {vals!r}")
    return {str(k).lower(): [str(v).lower() for v in vals] for k, vals in aliases.items()}


_ALIASES: dict[str, list[str]] = _load_aliases()


def _tokenize(skills: list[str]) -> list[str]:
    return [s.strip().lower() for s in skills if s.strip()]


# "SQL Server 2008 or later", "Java 11 or higher": a version floor. Left in, the "or" splits off
# "later", which then matches any evidence that happens to use the word.
_VERSION_FLOOR_RE = re.compile(
    r"(?:\s+v?\d+(?:\.\d+)*[a-z]?(?:\s+r\d)?)?\s+or\s+(?:later|higher|newer|above|greater)\b",
    re.IGNORECASE,
)


def _normalize(skill: str) -> str:
    """Lowercase and strip noisy years-of-experience prefixes and parenthetical ranges."""
    s = skill.strip().lower()
    s = re.sub(
        r"^\d+\s*(?:[-+]|to\s*\d+)?\s*(?:years?|yrs?)\s*(?:of\s*)?", "", s, flags=re.IGNORECASE
    )
    s = re.sub(r"^\+\s*", "", s)
    s = re.sub(r"^(?:years?|yrs?)\s*(?:of\s*)?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = _VERSION_FLOOR_RE.sub("", s)
    return strip_skill_punctuation(s)


def skill_match_terms(skill: str) -> list[str]:
    """Return the normalized, alias-expanded match terms for a skill/requirement.

    Public seam around the same pipeline ``_has_skill`` uses internally
    (normalize → alias expansion → compound-phrase splitting), so other
    modules (e.g. gap-coaching heading matching in ``find_gap_coaching_entry``)
    can reuse it without reaching into this module's private helpers.
    """
    normalized = _normalize(skill)
    terms = _expand_terms(normalized)
    # Also expand any multi-token phrase into its component tokens for matching; each piece
    # gets its aliases too, so "vulnerability assessments / pen tests" finds "penetration testing"
    for piece in _split_compound(normalized):
        terms.extend(_expand_terms(piece))
    return list(dict.fromkeys(terms))


# "Containerization and Kubernetes deployment are planned, not done": work a project has not done
# is not evidence of it.
_NOT_BUILT_RE = re.compile(
    r"\bplanned,?\s+(?:but\s+)?not\s+(?:yet\s+)?(?:done|built|started|implemented)\b|"
    r"\b(?:is|are)\s+(?:still\s+)?planned\b|"
    r"\bnot\s+yet\s+(?:done|built|started|implemented)\b",
    re.IGNORECASE,
)
_PROJECT_SENTENCE_RE = re.compile(r"(?<=[.;!?])\s+")


def _built_only(text: str) -> str:
    """``text`` without the sentences about work that is still to be done."""
    return " ".join(s for s in _PROJECT_SENTENCE_RE.split(text) if not _NOT_BUILT_RE.search(s))


def _has_skill(profile: Profile, raw_skill: str) -> tuple[MatchStatus, str]:
    """Return (status, evidence) for a single skill against the profile."""
    skill_lower = _normalize(raw_skill)
    skill_terms = skill_match_terms(raw_skill)

    # Production experience: resume bullets mention it. Entries with no
    # company (e.g. "Professional Development & Portfolio Building" — a
    # resume section for self-directed coursework, not an employer) are
    # skipped here: their content is explicitly course/portfolio-level, and
    # counting it as production would overclaim evidence for a real job
    # requirement. Skills mentioned there still register below via the
    # technical_skills/ats_keywords course-tier check.
    for exp in profile.resume_roles:
        if not exp.company:
            continue
        joined = " ".join(exp.bullets + [exp.title, exp.company]).lower()
        if _match_terms(skill_terms, joined):
            return "match", f"{exp.company}: production"

    # Resolved framing gaps are always matches
    if any(skill_lower == g.lower() for g in profile.resolved_gap_names):
        return "match", "resolved framing gap"

    # Portfolio evidence
    for project in profile.projects:
        parts = [project.name, " ".join(project.stack), _built_only(project.description)]
        parts += [_built_only(line) for line in project.skills_evidence]
        text = " ".join(parts).lower()
        if _match_terms(skill_terms, text):
            return "portfolio", f"{project.name}: portfolio"

    # Known genuine gaps with portfolio evidence
    for gap in profile.genuine_gaps:
        if gap.evidence.value == "portfolio" and _match_terms(skill_terms, gap.skill.lower()):
            return "portfolio", f"tracked gap (portfolio): {gap.skill}"

    # Coursework evidence via ATS keywords / technical skills
    skill_pool = []
    for cat in profile.skills.groups:
        skill_pool.extend(cat.skills)
    for values in profile.keyword_map.values():
        skill_pool.extend(values)
    all_skills_text = " ".join(skill_pool).lower()
    if _match_terms(skill_terms, all_skills_text):
        return "course", "coursework or self-study"

    # Known genuine gaps may already be partially addressed by coursework
    gap_pool = [g.skill for g in profile.genuine_gaps]
    all_gaps_text = " ".join(gap_pool).lower()
    if _match_terms(skill_terms, all_gaps_text):
        return "course", "tracked gap — partial coursework"

    # Last resort: legacy employment deliberately kept off the resume. Only
    # reached when every tier above missed, so it never scans old history for
    # a skill the current resume/portfolio/coursework already covers.
    for exp in profile.legacy_roles:
        if not exp.company:
            continue
        joined = " ".join(exp.bullets + [exp.title, exp.company]).lower()
        if _match_terms(skill_terms, joined):
            return "legacy", (
                f"{exp.company} ({exp.dates or 'legacy'}): legacy experience, "
                "not on the active resume — surface only by explicit per-application "
                "decision (Earlier Experience addendum or cover-letter mention)"
            )

    return "gap", "no evidence"


def _split_compound(skill: str) -> list[str]:
    """Break compound phrases on '/', ';', 'and', 'or' to allow partial matches."""
    pieces = re.split(r"[/;]|\s+or\s+|\s+and\s+", skill)
    return [strip_skill_punctuation(p) for p in pieces if len(p.strip()) > 1]


def _expand_terms(skill: str) -> list[str]:
    """Return the skill plus any registered aliases for it."""
    terms = [skill]
    for key, aliases in _ALIASES.items():
        if skill == key or skill in aliases:
            terms.extend([key] + aliases)
    terms.extend(satisfied_by(skill))
    return list(dict.fromkeys(terms))


def _match_terms(terms: list[str], haystack: str) -> bool:
    """Match any term as a whole token in the haystack (no substring hits inside longer words)."""
    for term in terms:
        if len(term) <= 1:
            continue
        # Whole-token match: "rag" must not hit "storage", "ci" must not hit "Acme".
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?:e?s)?(?![a-z0-9])", haystack):
            return True
    return False


_PAREN_QUALIFIER_RE = re.compile(r"\s*\([^)]*\)")


def find_gap_coaching_entry(skill: str, entries: list[GapCoachingEntry]) -> GapCoachingEntry | None:
    """Find the gap-coaching entry whose heading best matches ``skill``.

    Headings carry a parenthetical qualifier (e.g. "Power BI (as primary
    requirement)") describing *when* the note applies, not part of the
    matchable label — stripped before comparing. Matching is bidirectional
    substring matching on the same normalize/alias-expand/split pipeline
    ``_has_skill`` uses (via ``skill_match_terms``): either the heading's
    terms appear in the skill text (catches a short heading like "Cloud /
    Azure" matching a longer JD phrase like "strong azure fundamentals"),
    or the skill's terms appear in the heading text (catches a short JD
    term like "oracle" matching a longer heading like "Oracle Databases").
    Returns the first entry in file order to match — deterministic, no LLM
    fallback. An unmatched skill returns ``None``, never a fabricated or
    approximate coaching note.
    """
    skill_lower = _normalize(skill)
    skill_terms = skill_match_terms(skill)
    for entry in entries:
        heading_stripped = _PAREN_QUALIFIER_RE.sub("", entry.heading).strip()
        heading_lower = heading_stripped.lower()
        heading_terms = skill_match_terms(heading_stripped)
        if _match_terms(heading_terms, skill_lower) or _match_terms(skill_terms, heading_lower):
            return entry
    return None


def rate_fit(
    required: list[str],
    nice_to_have: list[str],
    profile: Profile,
    location: LocationAssessment | None = None,
    unscored_required: tuple[str, ...] = (),
    terms_to_confirm: tuple[tuple[str, str], ...] = (),
    possible_typos: tuple[tuple[str, str, str], ...] = (),
    unknown_names: tuple[tuple[str, str], ...] = (),
    soft_requirements: tuple[SoftRequirement, ...] = (),
    core_skills: frozenset[str] = frozenset(),
    required_line_count: int = 0,
) -> FitResult:
    """Rate how well ``profile`` matches a JD with the given required and nice skills.

    ``location`` is the JD's ``LocationAssessment`` (``ParsedJD.location_check``).
    A disqualifier — Quebec-based, hybrid/on-site outside the home city, remote
    limited to Atlantic Canada, or French required — forces ``Pass`` regardless
    of skill fit; the per-skill matches are still returned so reports can show
    them, and ``skill_rating`` keeps what the skills alone would have earned.
    Callers that omit ``location`` get the unchanged skills-only rating.
    ``unscored_required`` (``ParsedJD.unscored_required``) is carried onto the
    result for display only — it never changes the rating. Prefer
    ``rate_parsed_jd``, which passes both from a parsed JD so neither is forgotten.
    """
    # The skills are matched in lower case; the posting's own capitals tell a skill name from
    # another proper name in a sentence ("React" from "Azure Data Factory"), so keep them.
    case_of = {s.strip().lower(): s.strip() for s in [*required, *nice_to_have] if s.strip()}
    # A skill the posting asks for as required and also lists as a bonus is one skill: counting it
    # again as a nice-to-have present would help a Good rating reach Strong on the same evidence.
    required_names = {s.strip().lower() for s in required}
    for name in list(required_names):
        required_names.update(some_of_members(name) or ())
    nice_to_have = [s for s in nice_to_have if s.strip().lower() not in required_names]
    required_matches = [
        replace(_classify(skill, profile, case_of.get(skill)), core=skill in core_skills)
        for skill in _tokenize(required)
    ]
    nice_matches = [
        _classify(skill, profile, case_of.get(skill)) for skill in _tokenize(nice_to_have)
    ]
    skill_rating, rationale = _derive_rating(required_matches, nice_matches)
    rating = skill_rating
    disqualifiers: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    if location is not None:
        disqualifiers = location.disqualifiers
        flags = location.flags
        if disqualifiers:
            rating = "Pass"
            rationale = (
                "Outside job-search constraints — "
                + "; ".join(disqualifiers)
                + f". Skills alone would rate {skill_rating}: {rationale}"
            )
    return FitResult(
        rating=rating,
        required=required_matches,
        nice_to_have=nice_matches,
        rationale=rationale,
        skill_rating=skill_rating,
        location_disqualifiers=disqualifiers,
        location_flags=flags,
        unscored_required=tuple(unscored_required),
        terms_to_confirm=tuple(terms_to_confirm),
        possible_typos=tuple(possible_typos),
        unknown_names=tuple(unknown_names),
        soft_requirements=with_education_on_file(soft_requirements, profile.education),
        required_line_count=required_line_count,
    )


def rate_parsed_jd(parsed: ParsedJD, profile: Profile) -> FitResult:
    """Rate a parsed JD, applying its location rules and surfacing unscored lines.

    The one call every JD-driven caller should use: it forwards
    ``parsed.location_check`` and ``parsed.unscored_required`` so neither can be
    forgotten at a call site (see ADR 0008).
    """
    return rate_fit(
        parsed.required_for_rating,
        parsed.nice_for_rating,
        profile,
        location=parsed.location_check,
        unscored_required=parsed.unscored_required,
        terms_to_confirm=parsed.terms_to_confirm,
        possible_typos=parsed.possible_typos,
        unknown_names=parsed.unknown_names,
        soft_requirements=parsed.soft_requirements,
        core_skills=parsed.core_skills,
        required_line_count=parsed.required_line_count,
    )


def _has_umbrella(profile: Profile, parts: tuple[str, ...]) -> tuple[MatchStatus, str]:
    """The best evidence among the parts of an umbrella skill (ADR 0022), naming the part that
    earned it. The umbrella's own word never counts: "AI" in a project description proves nothing."""
    best: tuple[MatchStatus, str, str] | None = None
    for part in parts:
        status, evidence = _has_skill(profile, part)
        if status == "gap":
            continue
        if best is None or _STATUS_RANK[status] > _STATUS_RANK[best[0]]:
            best = (status, evidence, part)
    if best is None:
        return "gap", "no evidence"
    return best[0], f"{best[1]} [via {best[2]}]"


# A "some of" list is met when this many of its names have production evidence (ADR 0038).
SOME_OF_PRODUCTION_NEEDED = 2


def _classify_some_of(skill: str, names: list[str], profile: Profile) -> SkillMatch:
    """One row for a "some of" list: ✅ with two or more names in production, 🟡 with any other
    current evidence, 🕰️ with legacy evidence only, 🔴 with none. A name with no evidence is never
    a gap of its own."""
    rows = tuple(_classify(name, profile) for name in names)
    production = [m for m in rows if m.status == "match"]
    current = [m for m in rows if m.status in ("match", "portfolio", "course")]
    legacy = [m for m in rows if m.status == "legacy"]
    rated_as: MatchStatus | None = None
    if len(production) >= SOME_OF_PRODUCTION_NEEDED:
        # show the source that covers the most of them
        sources = [m.evidence for m in production]
        shown = max(production, key=lambda m: sources.count(m.evidence))
    elif current:
        shown = max(current, key=lambda m: _STATUS_RANK[m.status])
        if shown.status == "match":
            rated_as = "course"
    elif legacy:
        shown = legacy[0]
    else:
        return SkillMatch(
            skill=" / ".join(names), status="gap", evidence="no evidence", members=rows
        )
    named = " / ".join(
        m.skill for m in rows if (m.status, m.evidence) == (shown.status, shown.evidence)
    )
    return SkillMatch(
        skill=named,
        status=shown.status,
        evidence=shown.evidence,
        members=rows,
        rated_as=rated_as,
    )


def _classify(skill: str, profile: Profile, original: str | None = None) -> SkillMatch:
    if (names := some_of_members(skill)) is not None:
        return _classify_some_of(skill, names, profile)
    parts = umbrella_parts(skill)
    if parts is not None:
        status, evidence = _has_umbrella(profile, parts)
        return SkillMatch(skill=skill, status=status, evidence=evidence)
    if is_prose_requirement(skill):
        status, evidence = _has_prose_skill(profile, skill, original)
    else:
        status, evidence = _has_skill(profile, skill)
    return SkillMatch(skill=skill, status=status, evidence=evidence)


# Higher is stronger; derived from EVIDENCE_STATUS_ORDER so the two can't diverge.
_STATUS_RANK: dict[str, int] = {
    status: len(EVIDENCE_STATUS_ORDER) - 1 - i for i, status in enumerate(EVIDENCE_STATUS_ORDER)
}

_PROSE_SPLIT_RE = re.compile(
    r"[,;:/\u2014\u2013()]|\s+(?:or|and)\s+|\s+(?:such as|like|including|e\.g\.)\s+"
    # "backend programming experience in C#" -> "backend programming" + "C#"
    r"|\s+(?:experience|knowledge|skills?|expertise|exposure|proficiency|familiarity|"
    r"background|foundation|competenc(?:y|ies))\s+(?:in|with|of|using|on)\s+",
    re.IGNORECASE,
)
# Words that frame a skill in a sentence ("Solid backend programming
# experience in C#") without being part of it. Stripped from both ends of each
# fragment so what's left is a short noun phrase the matcher can find.
_PROSE_FILLER = (
    "a|an|the|solid|strong|previous|proven|good|deep|extensive|hands-on|working|comparable|"
    "related|modern|other|complex|production-safe|critically|writing|using|diagnosing|"
    "experience|knowledge|skills?|ability|understanding|foundation|proficiency|familiarity|"
    "background|expertise|exposure|competenc(?:y|ies)|equivalent|similar|preferred|"
    "in|with|of|on|for|to|as|such|or|and|their|output|rather|than|accepting|it|at|face|value|"
    "environments?|systems?|tools?|languages?|methodologies|experience|work"
)
_PROSE_FILLER_ONLY_RE = re.compile(rf"(?:{_PROSE_FILLER})", re.IGNORECASE)
_PROSE_EDGE_RE = re.compile(
    rf"^(?:(?:{_PROSE_FILLER})\s+)+|(?:\s+(?:{_PROSE_FILLER}))+$", re.IGNORECASE
)


def _prose_candidates(sentence: str) -> list[str]:
    """Short skill phrases pulled out of a prose requirement.

    "Solid backend programming experience in C#/.NET, or a comparable language
    such as Java" -> ["backend programming", "c#", ".net", "java"].
    """
    candidates: list[str] = []
    for piece in _PROSE_SPLIT_RE.split(sentence.lower()):
        piece = piece.lstrip(" ,:;/").rstrip(" ,.:;/")
        # Peel "<filler> experience in X" repeatedly; a fragment that is only
        # filler collapses to "" and is dropped.
        previous = None
        while piece and piece != previous:
            previous = piece
            piece = _PROSE_EDGE_RE.sub("", piece).lstrip(" ,:;/").rstrip(" ,.:;/")
        # A fragment that is nothing but filler ("equivalent", "diagnosing")
        # would otherwise match unrelated profile text.
        if _PROSE_FILLER_ONLY_RE.fullmatch(piece):
            continue
        if len(piece) >= 2 and piece not in candidates:
            candidates.append(piece)
    return candidates


_CAPITALISED_WORD_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9.+#]*")


def _only_skill_names_capitalised(sentence: str) -> bool:
    """True when every capitalised word after the first belongs to a skill name in the sentence
    ("Web Security", "REST"), so none of them is another proper name ("Factory")."""
    terms = [part.lower() for entry in extract_skill_terms(sentence) for part in entry.split(" / ")]
    known_words = {word for term in terms for word in re.findall(r"[a-z0-9.+#]+", term)}
    words = _CAPITALISED_WORD_RE.findall(sentence)
    first = sentence.split()[0] if sentence.split() else ""
    return all(word == first or word.lower() in known_words for word in words)


def _has_prose_skill(
    profile: Profile, sentence: str, original: str | None = None
) -> tuple[MatchStatus, str]:
    """Rate a prose requirement by the best evidence found for any phrase in it.

    A sentence-style requirement usually lists alternatives or examples
    ("C#/.NET, or a comparable language such as Java"), so one well-evidenced
    phrase covers it. A sentence none of whose phrases match anything is still
    a genuine gap.
    """
    best: tuple[MatchStatus, str] = ("gap", "no evidence")
    for phrase in _prose_candidates(sentence):
        status, evidence = _has_skill(profile, phrase)
        if _STATUS_RANK[status] > _STATUS_RANK[best[0]]:
            best = (status, f"{evidence} [{phrase}]" if status != "gap" else evidence)
    # A sentence whose only capitalised words are skill names ("Experience building frontend
    # applications using React") asks for that skill: rate it by the skill. A sentence with another
    # proper name in it ("Azure Data Factory") may name something more specific, so it is not tried.
    if original is not None and _only_skill_names_capitalised(original):
        for entry in extract_skill_terms(original):
            for term in entry.split(" / "):
                if umbrella_parts(term) is not None:
                    continue
                status, evidence = _has_skill(profile, term)
                if _STATUS_RANK[status] > _STATUS_RANK[best[0]]:
                    best = (status, f"{evidence} [{term}]" if status != "gap" else evidence)
    # An umbrella the sentence names ("Experience using AI-assisted software development tools"
    # names AI) is rated by its parts, as it is when it stands alone. Other terms are not tried:
    # "Azure Data Factory and data pipelines" names Azure, and Azure is not Data Factory.
    for entry in extract_skill_terms(sentence):
        for term in entry.split(" / "):
            parts = umbrella_parts(term)
            if parts is None:
                continue
            status, evidence = _has_umbrella(profile, parts)
            if _STATUS_RANK[status] > _STATUS_RANK[best[0]]:
                best = (status, f"{evidence} [{term}]" if status != "gap" else evidence)
    return best


# Coverage cut-offs, in percent of the required skills (ADR 0021; starting values until outcomes
# are recorded, confirmed as F2). Pinned by boundary tests.
PASS_BELOW_PERCENT = 40
STRETCH_BELOW_PERCENT = 60


def _derive_rating(required: list[SkillMatch], nice: list[SkillMatch]) -> tuple[Rating, str]:
    """Rate on core gaps and coverage (ADR 0021). Rules run top to bottom; the first match wins.

    Coverage is (✅ + ½ × (🟡 + 🕰️)) ÷ required skills. Core gaps are 🔴 rows flagged core.

    | Rating      | When                                                                     |
    |-------------|--------------------------------------------------------------------------|
    | Pass        | 2+ core 🔴, or coverage under 40%                                         |
    | Stretch     | 1 core 🔴, or coverage 40–59%                                             |
    | Worth a try | 0 core 🔴, and a tail 🔴 or 3+ 🟡/🕰️ (so coverage is 60% or more)         |
    | Good        | no 🔴, short of Strong's bar; any 🕰️ caps the rating here                 |
    | Strong      | no 🔴, 0–2 🟡, no 🕰️, at least two nice-to-haves present                  |

    Everything is a count over ``SkillMatch`` rows, so the same input always gives the same
    rating. The rationale states the coverage and names each core gap, so a rating can be
    explained from its output alone.
    """
    if not required:
        return "Pass", "No required skills provided"

    counts = _count_statuses(required)
    nice_counts = _count_statuses(nice)
    total = len(required)
    red = counts["gap"]
    yellow = counts["portfolio"] + counts["course"]
    legacy = counts["legacy"]
    nice_present = (
        nice_counts["match"]
        + nice_counts["portfolio"]
        + nice_counts["course"]
        + nice_counts["legacy"]
    )
    core_gaps = [m.skill for m in required if m.status == "gap" and m.core]
    tail_red = red - len(core_gaps)

    half_points = 2 * counts["match"] + yellow + legacy  # coverage in halves of a skill
    percent = (50 * half_points) // total  # floor, so "59%" can never round up to Stretch's edge
    coverage = f"coverage {percent}% of {total} required skills"
    gap_note = f" Core gap(s): {', '.join(core_gaps)}." if core_gaps else ""
    other = f" {tail_red} other gap(s)." if tail_red and core_gaps else ""

    if len(core_gaps) >= 2:
        return (
            "Pass",
            f"{len(core_gaps)} core requirements have no evidence; {coverage}.{gap_note}{other}",
        )
    if 50 * half_points < PASS_BELOW_PERCENT * total:
        return "Pass", f"Low {coverage}; critical mismatch likely.{gap_note}"
    if len(core_gaps) == 1:
        return "Stretch", f"A core requirement has no evidence; {coverage}.{gap_note}{other}"
    if 50 * half_points < STRETCH_BELOW_PERCENT * total:
        return "Stretch", f"Moderate {coverage}.{gap_note}"
    # From here there are no core gaps and coverage is 60% or more.
    if tail_red or yellow + legacy >= 3:
        parts = []
        if tail_red:
            parts.append(f"{tail_red} gap(s) outside the core requirements")
        if yellow + legacy:
            parts.append(f"{yellow + legacy} course/portfolio/legacy-only signal(s)")
        return "Worth a try", f"No core gaps; {coverage}; " + " and ".join(parts) + "."
    # Good (capped): legacy-only evidence isn't shown by the default resume, so
    # it can't support Strong without an explicit decision to surface it.
    if legacy:
        return (
            "Good",
            f"All required skills covered, but {legacy} rely on legacy experience "
            "not on the active resume — capped below Strong.",
        )
    # Strong: 0-2 required skills course/portfolio-only, and at least 2 nice-to-haves present.
    if yellow <= 2 and nice_present >= 2:
        return (
            "Strong",
            f"All {total} required skills covered "
            f"({yellow} course/portfolio-only); {nice_present} nice-to-have(s) present.",
        )
    # Good: required skills fully covered (✅/🟡, no 🔴), but short of Strong's bar.
    return (
        "Good",
        f"All required skills covered ({yellow} course/portfolio-only signal(s)); "
        f"{nice_present} nice-to-have(s) present.",
    )


def _count_statuses(matches: list[SkillMatch]) -> dict[str, int]:
    counts: dict[str, int] = {"match": 0, "portfolio": 0, "course": 0, "legacy": 0, "gap": 0}
    for m in matches:
        counts[m.rating_status] += 1
    return counts


_STATUS_EMOJI = {
    "match": "✅",
    "portfolio": "🟡",
    "course": "🟡",
    "legacy": "🕰️",
    "gap": "🔴",
}


def _display_evidence(evidence: str) -> str:
    """Comma-separated display form of an evidence string for the fit table
    (e.g. "Contoso: production" -> "Contoso, production"), matching the
    ``"Acme Software, production"`` style in job_description_fit/SKILL.md's
    Step 4 template. The stored evidence string itself keeps its colon
    separator — ``evidence_sources()``/``humanize_evidence()`` split on it —
    this only affects how the table is rendered.
    """
    return evidence.replace(": ", ", ", 1)


def row_label(match: SkillMatch) -> str:
    """The requirement's name in a table: a "some of" row says how many names it stands for."""
    if match.members:
        return f"some of {len(match.members)} listed"
    return match.skill


def row_evidence(match: SkillMatch, evidence: str) -> str:
    """``evidence`` for a table row: a "some of" row counts its names instead."""
    if not match.members:
        return evidence
    production = sum(1 for m in match.members if m.status == "match")
    none = sum(1 for m in match.members if m.status == "gap")
    other = len(match.members) - production - none
    return f"{production} in production, {other} other, {none} without evidence (listed below)"


def _fit_row(m: SkillMatch) -> str:
    emoji = _STATUS_EMOJI[m.rating_status]
    return f"| {row_label(m)} | {emoji} | {row_evidence(m, _display_evidence(m.evidence))} |"


def render_some_of_lists(
    result: FitResult, clean: Callable[[str], str] = lambda evidence: evidence
) -> list[str]:
    """Markdown lines showing every name of each "some of" requirement; empty when there is none.
    ``clean`` rewrites an evidence string before it is shown (the gap report hides some of it)."""
    lines: list[str] = []
    for title, matches in (("required", result.required), ("nice to have", result.nice_to_have)):
        for match in matches:
            if not match.members:
                continue
            lines.append("")
            lines.append(
                f'**"Some of" list ({title})** — one requirement: ✅ with two or more in '
                "production, 🟡 with any other evidence, 🔴 with none"
            )
            lines.append("| Listed | Status | Evidence |")
            lines.append("|---|---|---|")
            for m in match.members:
                shown = _display_evidence(clean(m.evidence))
                lines.append(f"| {m.skill} | {_STATUS_EMOJI[m.status]} | {shown} |")
    return lines


def render_fit_table(result: FitResult) -> str:
    """Render a FitResult as markdown suitable for CLI or skill output."""
    lines: list[str] = []
    lines.append("## Fit Check")
    lines.append("")
    lines.append("**Required Skills**")
    lines.append("| Skill | Status | Evidence |")
    lines.append("|---|---|---|")
    for m in result.required:
        lines.append(_fit_row(m))
    if result.nice_to_have:
        lines.append("")
        lines.append("**Nice-to-Haves**")
        lines.append("| Skill | Status | Evidence |")
        lines.append("|---|---|---|")
        for m in result.nice_to_have:
            lines.append(_fit_row(m))
    lines.extend(render_some_of_lists(result))
    if result.unscored_required:
        lines.append("")
        lines.append("**Required lines not scored** (no recognizable skill — read these yourself)")
        for line in result.unscored_required:
            lines.append(f"- {line}")
    if result.low_confidence:
        lines.append("")
        lines.append(f"**Low-confidence result** — {result.low_confidence_message}")
    if result.soft_requirements:
        lines.append("")
        lines.append(
            "**Soft requirements** (education, years, title level and soft skills; listed for you to read, never scored)"
        )
        for soft in result.soft_requirements:
            label = LABELS.get(soft.kind, "Education")
            lines.append(f"- {label} — {soft.note}: {soft.line}")
            if soft.on_file:
                lines.append(f"  - On file: {soft.on_file}")
    if result.terms_to_confirm:
        lines.append("")
        lines.append(
            "**Terms to confirm** (each is also a skill name; read as ordinary English and "
            "not scored; ask the user which meaning the posting intends)"
        )
        for word, line in result.terms_to_confirm:
            lines.append(f'- "{word}" in: {line}')
    if result.possible_typos:
        lines.append("")
        lines.append(
            "**Possible typos** (a word one letter from a skill name; not scored; "
            "check the posting)"
        )
        for word, term, line in result.possible_typos:
            lines.append(f'- "{word}" may be "{term}" in: {line}')
    if result.unknown_names:
        lines.append("")
        lines.append(
            "**Names to check** (named in a list of examples but not in the skill list; not "
            "scored; read the posting)"
        )
        for name, line in result.unknown_names:
            lines.append(f'- "{name}" in: {line}')
    lines.append("")
    lines.append(f"**Fit Rating: {result.rating}**")
    lines.append(f"{result.rationale}")
    if result.location_disqualifiers or result.location_flags:
        lines.append("")
        lines.append("**Location & work arrangement**")
        for reason in result.location_disqualifiers:
            lines.append(f"- 🚫 {reason}")
        for flag in result.location_flags:
            lines.append(f"- ⚠️ {flag}")
    return "\n".join(lines)


def humanize_evidence(match: SkillMatch, *, audience: str = "letter") -> str:
    """Convert a debug-grade evidence string into prose appropriate for the audience.

    ``audience="debug"`` keeps the original machine-readable evidence label.
    ``audience="letter"`` returns candidate-friendly phrasing that does not
    overclaim course/gap skills as production experience.

    Examples:
        >>> humanize_evidence(SkillMatch("Azure", "match", "Contoso: production"))
        'hands-on experience at Contoso'
        >>> humanize_evidence(SkillMatch("Docker", "portfolio", "CookingTime: portfolio"))
        'portfolio work on CookingTime'
        >>> humanize_evidence(SkillMatch("Kubernetes", "course", "coursework or self-study"))
        'recent coursework'
        >>> humanize_evidence(SkillMatch("Rust", "gap", "no evidence"))
        'not yet demonstrated in production'
    """
    if audience == "debug":
        return match.evidence or "no evidence"

    status = match.status
    raw = (match.evidence or "").strip()
    if status == "match":
        if ":" in raw:
            label = raw.rsplit(":", 1)[0].strip()
            return f"hands-on experience at {label}" if label else "hands-on experience"
        return "hands-on experience"
    if status == "portfolio":
        if ":" in raw:
            label = raw.rsplit(":", 1)[0].strip()
            return f"portfolio work on {label}" if label else "portfolio work"
        return "portfolio work"
    if status == "course":
        return "recent coursework"
    if status == "legacy":
        # Never echo the raw evidence: it names the legacy employer and dates.
        return "earlier experience not detailed on the current resume"
    if status == "gap":
        return "not yet demonstrated in production"
    return raw or "evidence on file"


def profile_has_skill_text(skill: str, haystack: str) -> bool:
    """Reuse the fit-engine's alias-aware matching for callers like resume sort.

    This is the same logic that ``_has_skill`` uses internally: a skill matches
    the haystack if any of its tokens (after years-prefix normalization) or its
    registered aliases appear in the haystack. Single-character tokens are
    skipped to avoid false positives.
    """
    skill_lower = _normalize(skill)
    terms = _expand_terms(skill_lower)
    terms.extend(_split_compound(skill_lower))
    terms = list(dict.fromkeys(terms))
    return _match_terms(terms, haystack.lower())
