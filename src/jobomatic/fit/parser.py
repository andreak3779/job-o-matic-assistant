"""Job-description markdown parsing shared by fit-check and gap-analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobomatic.fit.location import LocationAssessment, assess_location
from jobomatic.fit.soft_requirements import (
    SoftRequirement,
    body_level,
    classify,
    classify_optional,
    has_years_figure,
    is_education,
    soft_skill,
    title_level,
)
from jobomatic.fit.soft_skills import is_soft_skill
from jobomatic.fit.terms import (
    conjoined_terms,
    extract_skill_terms,
    find_possible_typos,
    find_terms_to_confirm,
    find_unknown_names,
    is_kind_term,
    phrase_expansion,
    reduce_to_terms,
)


@dataclass(frozen=True)
class ParsedJD:
    """Structured result of parsing a JD markdown file."""

    required: list[str]
    nice_to_have: list[str]
    title: str
    company: str
    location: str | None = None
    job_id: str | None = None
    # Location / work-arrangement / French-requirement assessment. Pass it to
    # ``rate_fit(..., location=parsed.location_check)`` so the rating honours the
    # job-search location rules.
    location_check: LocationAssessment = field(default_factory=LocationAssessment)
    # Sentence-style required bullets in which no known skill term was found
    # (e.g. "Computer science degree or equivalent practical experience"). They
    # are not scored — ``rate_parsed_jd`` carries them onto ``FitResult`` so
    # reports list them instead of silently dropping them.
    unscored_required: tuple[str, ...] = ()
    # Ordinary English words that are also skills ("Solid understanding of CI/CD": adjective, or
    # the SOLID principles?), as (word, the line it appeared in), first line per word. Not scored:
    # the user is asked which meaning the posting intends. See ``find_terms_to_confirm``.
    terms_to_confirm: tuple[tuple[str, str], ...] = ()
    # (word, vocabulary term, line): a word one letter from a long skill name ("Typscript" for
    # "typescript"). Not scored and never corrected for the user: it is reported so they can check.
    possible_typos: tuple[tuple[str, str, str], ...] = ()
    # (name, line): a capitalised name in a list of examples ("such as MuleSoft") that is not in
    # the skill list. Not scored: it is shown so the user can see what the posting named.
    unknown_names: tuple[tuple[str, str], ...] = ()
    # Education and years-of-experience lines from the required section (ADR 0021): listed for the
    # user to read, never scored. A line that also names a known skill is still scored for it.
    soft_requirements: tuple[SoftRequirement, ...] = ()
    # Lowercased required items that are CORE requirements (ADR 0021, step C2): named in the title,
    # on one of the first five required lines, on a line with a years figure, or mentioned on two
    # or more lines of the posting. Soft-skill lines are never core. Pass to ``rate_fit`` as
    # ``core_skills``; ``rate_parsed_jd`` does.
    core_skills: frozenset[str] = frozenset()
    # Same items as ``required`` / ``nice_to_have``, except that a long prose
    # requirement ("Solid backend programming experience in C#/.NET, or a
    # comparable language such as Java") stays one whole item instead of being
    # chopped into fragments that can't be matched individually. Rate fit from
    # these; keep using ``required`` / ``nice_to_have`` where flat keywords are
    # wanted. Empty means "same as required / nice_to_have".
    required_items: list[str] = field(default_factory=list)
    nice_items: list[str] = field(default_factory=list)

    @property
    def required_for_rating(self) -> list[str]:
        """Required items to pass to ``rate_fit`` (whole prose items, not fragments)."""
        return self.required_items or self.required

    @property
    def nice_for_rating(self) -> list[str]:
        """Nice-to-have items to pass to ``rate_fit``."""
        return self.nice_items or self.nice_to_have


_REQUIRED_HEADING_RE = re.compile(
    r"(requirements?|must[\s-]haves?|what you.*need|what you.?ll bring|"
    r"(?:what|things) we.?re looking for|essential|required skills?|"
    r"(?:required|minimum|basic|key) (?:qualifications?|skills?|experience)|"
    r"desired (?:skills?|qualifications?|experience)|"
    r"qualifications|you have|who you are)",
    re.IGNORECASE,
)
# A bare "Experience" heading ("Experience", "Relevant Experience:") opens the requirements list.
_EXPERIENCE_HEADING_RE = re.compile(
    r"^\W*(?:relevant\s+|required\s+)?experience\W*$", re.IGNORECASE
)
# "React: Components, Hooks, routing…": a known skill, a colon, then detail about it.
_TERM_DETAIL_RE = re.compile(r"^([^:]{1,40}):\s+\S")


def _drop_term_details(item: str) -> str:
    """ "React: Components, Hooks, …" asks for React: the detail after the colon is not scored.
    Only for a short head that is exactly one known skill and not a kind of tool ("Monitoring:
    Datadog, Splunk" keeps its list, because the list is the requirement)."""
    match = _TERM_DETAIL_RE.match(item)
    if not match:
        return item
    head = match.group(1).strip()
    terms = extract_skill_terms(head)
    if (
        len(head.split()) <= 3
        and len(terms) == 1
        and " / " not in terms[0]
        and not is_kind_term(terms[0])
    ):
        return head
    return item


# A section of qualities, not tools (ADR 0023): its lines are listed as soft skills, never scored.
_SOFT_HEADING_RE = re.compile(
    r"(soft skills?|personal (?:qualities|attributes|characteristics)|interpersonal skills|"
    r"competenc(?:y|ies)|attributes)",
    re.IGNORECASE,
)
# "Nice-to-Have", "Nice to have", "Nice to Haves" all appear in real postings.
_NICE_HEADING_RE = re.compile(
    r"(nice[\s-]to[\s-]haves?|good[\s-]to[\s-]haves?|preferred|bonus|asset|desirable)",
    re.IGNORECASE,
)
# A single line that marks itself optional while sitting under a required heading (ADR 0021):
# "Preferred: experience with Kubernetes", "Terraform (preferred)", "Kubernetes is a plus".
# The marker is removed from the line before skills are read from it.
_NICE_PREFIX_RE = re.compile(
    r"^\W*(?:preferred|nice[\s-]to[\s-]haves?|bonus|asset)\s*:\s*", re.IGNORECASE
)
_NICE_PAREN_RE = re.compile(
    r"\(\s*(?:preferred\s+but\s+not\s+mandatory|not\s+mandatory|preferred|nice[\s-]to[\s-]haves?|"
    r"an?\s+bonus|an?\s+asset|bonus|asset)\s*\)",
    re.IGNORECASE,
)
_NICE_PHRASE_RE = re.compile(
    r"\b(?:(?:is|are|would be)\s+)?(?:preferred\s+but\s+not\s+mandatory|not\s+mandatory|"
    r"an?\s+(?:(?:strong|real|big|great|definite|huge|major|distinct)\s+)?(?:plus|asset|bonus)|"
    r"nice[\s-]to[\s-]haves?)\b",
    re.IGNORECASE,
)


# "Nice to have but strongly preferred" is not optional: the line stays required (owner's call).
_STRONGLY_PREFERRED_RE = re.compile(r"\bstrongly\s+preferred\b", re.IGNORECASE)


def _strip_nice_marker(item: str) -> tuple[str, bool]:
    """Return ``item`` without any "preferred"-style marker, and whether it had one."""
    if _STRONGLY_PREFERRED_RE.search(item):
        return item, False
    cleaned = _NICE_PREFIX_RE.sub("", item)
    cleaned = _NICE_PAREN_RE.sub(" ", cleaned)
    cleaned = _NICE_PHRASE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
    return cleaned, cleaned != item.strip(" ,.;:-")


# "8+ years of experience, preferably in SaaS": only what follows the word is optional; the part
# before it stays required (owner's call, ADR 0021).
_PREFERABLY_RE = re.compile(r"\b(?:preferably|ideally)\b[\s,:]*", re.IGNORECASE)


def _split_preferably(item: str) -> tuple[str, str] | None:
    """``(required part, optional part)`` for a line with "preferably"/"ideally", else ``None``."""
    match = _PREFERABLY_RE.search(item)
    if not match or _STRONGLY_PREFERRED_RE.search(item):
        return None
    return item[: match.start()].strip(" ,;:-"), item[match.end() :].strip()


# Two bullets run together when a posting is copied ("…lifecycle.- Experience in designing…"):
# a full stop, then a dash with no space before it, then a capital letter.
_GLUED_BULLET_RE = re.compile(r"(?<=[.!?])-\s+(?=[A-Z])")


def _unglue_bullets(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        parts = _GLUED_BULLET_RE.split(line)
        indent = line[: len(line) - len(line.lstrip())]
        out.append(parts[0])
        out.extend(f"{indent}- {part}" for part in parts[1:])
    return out


# Common non-requirement section headings that follow a requirements list in
# real-world postings (benefits/perks/company-blurb sections). Without this,
# `section` never resets once set, so a heading-shaped line the parser
# doesn't otherwise recognize (e.g. "What we offer") leaves the *following*
# section's bullets miscategorized as required/nice-to-have indefinitely —
# see tests/fixtures for a real posting that silently absorbed its entire
# benefits list as "required skills" this way.
_SECTION_END_HEADING_RE = re.compile(
    r"(what we offer|benefits?|perks|compensation|why (?:join|work)|"
    r"about (?:us|the company)|our culture|company overview|"
    r"responsibilit(?:y|ies)|what you.?ll do|salary|pay range|how to apply|"
    r"equal opportunity|culture by|our values|core values|how we work)",
    re.IGNORECASE,
)
# A label line ("Location: …", "Reports To: …") closes the skills list: what follows is not a skill.
_LABEL_LINE_END_RE = re.compile(
    r"^\W*(?:work\s+)?(?:location|reports?\s+to|job\s+type|employment\s+type|hours|schedule|"
    r"work\s+arrangement|salary|pay)\s*:",
    re.IGNORECASE,
)
# Closing boilerplate of a posting: never a requirement, wherever the section state stands.
_CLOSING_BOILERPLATE_RE = re.compile(
    r"committed\s+to\s+(?:inclusion|diversity|equity|equal)|encourages?\s+applications|"
    r"thank\s+(?:you\s+to\s+)?all\s+applicants|active\s+job\s+opening|"
    r"equal\s+opportunity\s+employer",
    re.IGNORECASE,
)
# A heading-shaped line doesn't end in sentence punctuation — "## Nice to
# Have" / "**Requirements:**" don't, but a prose sentence that happens to
# mention "a bonus" or "nice to have" in passing does. This alone can't tell
# a heading from prose in general, but it's a cheap, low-risk guard against
# the specific, demonstrated failure mode of a descriptive sentence hijacking
# section-detection mid-paragraph (see tests/test_jd_parser.py's baseline
# characterization tests).
# A trailing ellipsis ("You have...") is a heading flourish, not sentence-ending
# punctuation — the lookbehind keeps "..." from counting as a full stop.
_SENTENCE_PUNCT_RE = re.compile(r"(?<!\.)[.!?]\s*$")
_YEARS_PREFIX_RE = re.compile(
    r"^\d+\s*\+?\s*(?:(?:[-–—]|to)\s*\d+\s*\+?\s*)?(?:years?|yrs?)\s*(?:of\s*)?",
    re.IGNORECASE,
)
# The list marker only ("- ", "• ", "1. ", "2) "); digits that belong to the line stay.
_BULLET_MARKER_RE = re.compile(r"^(?:[-•*]+\s*|\d+[.)]\s+)")
_LEADING_PLUS_RE = re.compile(r"^\+\s*")
_BARE_YEARS_RE = re.compile(r"^(?:years?|yrs?)\s*(?:of\s*)?", re.IGNORECASE)
_PAREN_YEARS_RE = re.compile(r"\(\d+\+?\s*years?.*\)", re.IGNORECASE)
# "CI/CD" is one practice, so its slash is not a split point (ADR 0009).
_SPLIT_COMPOUND_RE = re.compile(r"(?<!(?i:\bci))/(?!(?i:cd\b))|;|\s+or\s+|\s+and\s+")
# A bullet longer than this is a sentence ("Experience building Azure applications
# using event-driven architectures"), not a skill name ("SQL Server / T-SQL query
# optimization"). Sentences get skill terms extracted from them (src/jobomatic/fit/terms.py);
# short bullets keep the original split-on-and/or/slash behaviour unchanged.
_PROSE_MIN_WORDS = 6
# Items this long are rated as one whole requirement, not split into fragments.
# Tied to _PROSE_MIN_WORDS so the cut-offs can't drift apart. The difference is
# intentional: that one uses ``>`` on the word count without parentheticals (term
# extraction), this one ``>=`` on the full count including them (whole-item rating).
_PROSE_REQUIREMENT_MIN_WORDS = _PROSE_MIN_WORDS
_BULLET_RE = re.compile(r"^[-•]|^\d+[.)]")

# Postings saved as label/value pairs under their own headings, e.g.
# "# Company\nExample Corp\n\n# Position\nSoftware Developer". "Postion" is
# accepted because it is a common typo in hand-saved JD files.
_POSITION_HEADING_RE = re.compile(
    r"^#+[ \t]*(?:position|postion|job[ \t]*title|role|title)[ \t]*\n+[ \t]*([^\n#]+)",
    re.IGNORECASE | re.MULTILINE,
)
_COMPANY_HEADING_RE = re.compile(
    r"^#+[ \t]*company[ \t]*\n+[ \t]*([^\n#]+)", re.IGNORECASE | re.MULTILINE
)
_TITLE_H1_RE = re.compile(r"(?:^#\s+)([^\n]+)", re.IGNORECASE | re.MULTILINE)
# "Role: Web Developer" / "**Company:** Example Co": the label must start the line and end in a
# colon, so the word "role" inside a sentence ("a fully remote role open to...") never counts.
_LABEL_TITLE_RE = re.compile(
    r"^\W*(?:job[ \t]*title|position|postion|role|title)[ \t]*:[ \t]*([^\n]+)$",
    re.IGNORECASE | re.MULTILINE,
)
_LABEL_COMPANY_RE = re.compile(
    r"^\W*(?:company(?:[ \t]*name)?|employer|organi[sz]ation)[ \t]*:[ \t]*([^\n]+)$",
    re.IGNORECASE | re.MULTILINE,
)
_COMPANY_BOLD_RE = re.compile(r"\*\*[Cc]ompany:\*\*\s*([^\n]+)")
# "About Example Co" on a line of its own ("About the job", "About us" are not company names).
_ABOUT_COMPANY_RE = re.compile(
    r"^About[ \t]+([A-Z][\w&.\-]*(?:[ \t]+[A-Z][\w&.\-]*){0,3})[ \t]*$", re.MULTILINE
)
_ABOUT_NOT_A_COMPANY = frozenset({"us", "the", "this", "our", "you", "your", "me"})
# A plain-text paste (a copied web page) begins with "Title | Company" or "Title at Company".
_ROLE_WORD_RE = re.compile(
    r"\b(?:developer|engineer|programmer|architect|analyst|administrator|consultant|specialist|"
    r"designer|tester|manager|lead|devops|sre|scientist|technologist|coordinator|technician|"
    r"qa|swe)\b",
    re.IGNORECASE,
)
_NOT_A_COMPANY = frozenset(
    {"remote", "hybrid", "on-site", "onsite", "full-time", "part-time", "contract", "canada"}
)
_FIRST_LINE_AT_RE = re.compile(r"\s+at\s+(?=[A-Z])")
_TITLE_COMPANY_SPLIT_RE = re.compile(r"\s+[—–-]\s+")
_LOCATION_BOLD_RE = re.compile(r"\*\*[Ll]ocation:\*\*\s*([^\n]+)")
_JOB_ID_BOLD_RE = re.compile(
    r"\*\*(?:[Jj]ob\s*ID|[Rr]eq(?:uisition)?\s*ID|[Jj]ob\s*Number):\*\*\s*([^\n]+)"
)


def _strip_years_prefix(item: str) -> str:
    item = _YEARS_PREFIX_RE.sub("", item).strip(" ,./:;")
    item = _LEADING_PLUS_RE.sub("", item)
    item = _BARE_YEARS_RE.sub("", item).strip(" ,./:;")
    item = _PAREN_YEARS_RE.sub("", item).strip(",. ")
    return item


# "26WD100016, Principal Software Developer": a requisition number in front of the title.
_REQUISITION_PREFIX_RE = re.compile(
    r"^(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]{5,}\s*[,:]\s+|^(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]{5,}\s+[-–—]\s+"
)
# "AutoCanada is the largest Canadian owned…": a line that opens by naming the employer.
_OPENING_COMPANY_RE = re.compile(
    r"^([A-Z][A-Za-z0-9&'.-]*(?: [A-Z][A-Za-z0-9&'.-]*){0,3}) (?:is|are) (?:the|a|an|one of)\b",
    re.MULTILINE,
)
_NOT_AN_OPENING_COMPANY = frozenset(
    {"we", "it", "this", "that", "there", "our", "you", "your", "position", "role", "job", "team"}
)
_REPEATED_NAME_MIN = 3


def _company_from_text(text: str) -> str:
    """The employer's name when the posting never labels it: a first sentence of the form
    "<Name> is the…", else a capitalised word (not a skill) that appears in the text at least
    three times, mid-sentence. Empty when neither is found."""
    for match in _OPENING_COMPANY_RE.finditer(text):
        name = match.group(1).strip()
        if name.split()[0].lower() not in _NOT_AN_OPENING_COMPANY:
            return name
    counts: dict[str, int] = {}
    for match in re.finditer(r"(?<=[a-z,] )([A-Z][a-zA-Z]{3,})\b", text):
        word = match.group(1)
        if not extract_skill_terms(word):
            counts[word] = counts.get(word, 0) + 1
    best = [w for w, n in counts.items() if n >= _REPEATED_NAME_MIN]
    return max(best, key=lambda w: counts[w]) if best else ""


def _first_line_title_company(text: str) -> tuple[str | None, str | None]:
    """Title and company from the first line of a pasted posting, when it looks like a title.

    "Sr. Software Engineer (.NET core, Angular) | Example Co" -> both; "Backend Developer at
    Example Co" -> both; a first line that is a sentence, or names no role, gives nothing."""
    for raw in text.splitlines():
        line = raw.strip().lstrip("#*_> \t").rstrip("*_ \t")
        if not line:
            continue
        if len(line) > 140 or line.endswith((".", "!", "?", ":")):
            return None, None
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2:
            parts = [part.strip() for part in _FIRST_LINE_AT_RE.split(line, maxsplit=1)]
        if not _ROLE_WORD_RE.search(parts[0]):
            return None, None
        company = next(
            (p for p in parts[1:] if p and p.lower() not in _NOT_A_COMPANY and len(p.split()) <= 6),
            None,
        )
        return parts[0], company
    return None, None


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


_PAREN_GROUP_RE = re.compile(r"\([^)]*\)")


def _is_prose(item: str) -> bool:
    """True for a sentence-style bullet. A trailing parenthetical list — "Strong
    Azure fundamentals (App Service, Functions, Cosmos DB)" — is detail on a short
    skill name, so it isn't counted toward the word limit."""
    return len(_PAREN_GROUP_RE.sub(" ", item).split()) > _PROSE_MIN_WORDS


def _add_unique(target: list[str], values: list[str]) -> None:
    seen = {v.lower() for v in target}
    for value in values:
        if value.lower() not in seen:
            seen.add(value.lower())
            target.append(value)


def is_prose_requirement(text: str) -> bool:
    """True for a sentence-style requirement that must be rated whole.

    Splitting "Strong Azure fundamentals (App Service, Functions, Cosmos DB)" on
    and/or/slash yields fragments that match nothing. Unlike ``_is_prose`` this
    counts parenthetical words: they are the evidence the matcher needs.
    """
    return len(text.split()) >= _PROSE_REQUIREMENT_MIN_WORDS


def _split_required_or_nice(
    item: str,
    section: str,
    required: list[str],
    nice: list[str],
    required_items: list[str],
    nice_items: list[str],
) -> None:
    flat = required if section == "required" else nice
    items = required_items if section == "required" else nice_items
    pieces = [p.strip(" ,./:;") for p in _SPLIT_COMPOUND_RE.split(item)]
    pieces = [p for p in pieces if len(p) >= 2]
    # A short bullet that is only a choice between same-kind tools ("AWS or Azure",
    # "Entity Framework/Dapper") is one requirement met by either (ADR 0021).
    entries = extract_skill_terms(item)
    is_choice = False
    if phrase_expansion(item):
        # "AI-assisted automation techniques" stands for AI and workflow automation: two rows
        pieces = entries
        is_choice = True
    elif (listed := conjoined_terms(item)) is not None:
        # "Experience with Azure and REST APIs" asks for both: one row each, so a gap in one is
        # not hidden by evidence for the other. Kept out of the whole-sentence path below.
        pieces = listed
        is_choice = True
    elif len(entries) == 1 and " / " in entries[0]:
        if [p.lower() for p in pieces] == [t.lower() for t in entries[0].split(" / ")]:
            pieces = entries
            is_choice = True
        else:
            # "Experience with Azure or Google Cloud": the same choice with filler words around it.
            whole = reduce_to_terms(item)
            if whole and " / " in whole[0]:
                pieces = whole
                is_choice = True
    # "Strong Postgresql skills" asks for Postgresql: search for the term, not the whole phrase.
    reduced: list[str] = []
    for piece in pieces:
        reduced.extend(reduce_to_terms(piece) or [piece])
    # A requirement the posting names twice (an Experience list and a Must-Have list both ask for
    # React) is one requirement: it must not count twice toward coverage.
    already = {item.lower() for item in items}
    pieces = [piece for piece in reduced if piece.lower() not in already]
    flat.extend(piece for piece in pieces if piece.lower() not in {f.lower() for f in flat})
    if is_prose_requirement(item) and not is_choice:
        items.append(item)
    else:
        items.extend(pieces)


FIRST_REQUIRED_LINES_ARE_CORE = 5


def _item_terms(item: str) -> list[str]:
    """The skill names inside a required item ("A / B" gives both; a sentence gives its terms)."""
    found = [part for term in extract_skill_terms(item) for part in term.split(" / ")]
    return found or [item]


def _mention_count(term: str, lines: list[str]) -> int:
    pattern = re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(term.lower()) + r"s?(?![A-Za-z0-9])", re.IGNORECASE
    )
    return sum(1 for line in lines if pattern.search(line))


def _core_skills(items: list[str], positional: set[str], title: str, text: str) -> frozenset[str]:
    """Which required items are core (ADR 0021): positional, in the title, or mentioned twice."""
    lines = text.splitlines()
    core: set[str] = set()
    for item in items:
        key = item.lower()
        if is_soft_skill(item):
            continue
        if key in positional:
            core.add(key)
            continue
        for term in _item_terms(item):
            if _mention_count(term, [title]) or _mention_count(term, lines) >= 2:
                core.add(key)
                break
    return frozenset(core)


def parse_jd(text: str) -> ParsedJD:
    """Naively extract required, nice skills, title and company from JD text.

    Returns cleaned skill phrases that are short enough to be meaningful tokens
    for substring matching against the profile.
    """
    required: list[str] = []
    nice: list[str] = []
    unscored: list[str] = []
    to_confirm: list[tuple[str, str]] = []
    soft: list[SoftRequirement] = []
    typos: list[tuple[str, str, str]] = []
    unknown: list[tuple[str, str]] = []
    required_items: list[str] = []
    nice_items: list[str] = []
    section: str | None = None
    required_line_no = 0
    positional_core: set[str] = set()

    for raw in _unglue_bullets(text.splitlines()):
        stripped = raw.strip()
        lower = stripped.lower()
        if not stripped:
            continue
        is_bullet = _is_bullet(stripped)
        # Postings pasted from a web page often flatten bullets to indented
        # lines with no marker and no trailing punctuation. Indentation is the
        # only signal that such a line is list content rather than a heading.
        is_indented = raw[:1] == "\t" or raw.startswith("  ")
        # A bullet is content, never a section heading, even if its own text
        # happens to contain a heading-like phrase (e.g. a required-skill
        # bullet noting something is "nice to have but preferred").
        looks_like_heading = (
            not is_bullet and not is_indented and not _SENTENCE_PUNCT_RE.search(stripped)
        )
        # Nice-to-have is tested first: "Preferred Qualifications" and
        # "Nice-to-Have Qualifications" also contain the required-heading word
        # "qualifications", and must not be read as required skills.
        if looks_like_heading and _SOFT_HEADING_RE.search(lower) and "technical" not in lower:
            section = "soft"
            continue
        if looks_like_heading and _NICE_HEADING_RE.search(lower):
            section = "nice"
            continue
        if looks_like_heading and (
            _REQUIRED_HEADING_RE.search(lower) or _EXPERIENCE_HEADING_RE.match(stripped)
        ):
            section = "required"
            continue
        if looks_like_heading and _SECTION_END_HEADING_RE.search(lower):
            section = None
            continue
        if (not is_bullet and _LABEL_LINE_END_RE.match(stripped)) or _CLOSING_BOILERPLATE_RE.search(
            stripped
        ):
            section = None
            continue
        # Content is either a real bullet, or (for postings that flatten
        # bullets to plain indented sentences when copy-pasted) any
        # non-heading-shaped line — `looks_like_heading` already excludes
        # actual heading lines, so this only picks up prose sentences sitting
        # under a recognized section.
        if section and (is_bullet or not looks_like_heading):
            raw_item = _BULLET_MARKER_RE.sub("", stripped).strip()
            item = _drop_term_details(_strip_years_prefix(raw_item))
            line_section = section
            if section == "soft":
                soft.append(soft_skill(raw_item))
                continue
            prose = _is_prose(item)  # decided before a marker is removed, as before this rule
            if section == "required":
                item, marked = _strip_nice_marker(item)
                if marked:
                    line_section = "nice"
                elif (split := _split_preferably(item)) is not None:
                    item, optional = split
                    if optional:
                        optional_terms = extract_skill_terms(optional)
                        _add_unique(nice, optional_terms)
                        _add_unique(nice_items, optional_terms)
                    if not item:  # "Preferably experience with X": the whole line is optional
                        continue
            # A quality, not a tool (ADR 0023): listed, never scored. A line that also names a
            # skill, or an education/years line, takes the ordinary path below instead.
            if (
                line_section in ("required", "nice")
                and is_soft_skill(item)
                and not extract_skill_terms(item)
                and not classify(raw_item)
            ):
                soft.append(soft_skill(raw_item))
                continue
            items_before = len(required_items)
            line_has_years = False
            if line_section == "required":
                required_line_no += 1
                line_has_years = has_years_figure(raw_item)
                lines_soft = classify(raw_item)
                if lines_soft:
                    soft.extend(lines_soft)
                    if not extract_skill_terms(item):
                        continue  # nothing to score on this line: listed, not counted as a gap
            if line_section == "nice" and is_education(raw_item):
                # a certificate or training line: listed, never scored (what it names is what the
                # certificate covers, not skills the user is asked to have used)
                soft.extend(classify_optional(raw_item))
                continue
            for name in find_unknown_names(item):
                if name.lower() not in {seen.lower() for seen, _ in unknown}:
                    unknown.append((name, item))
            for typo, term in find_possible_typos(item):
                if typo.lower() not in {seen.lower() for seen, _, _ in typos}:
                    typos.append((typo, term, item))
            for word in find_terms_to_confirm(item):
                if word not in {seen for seen, _ in to_confirm}:
                    to_confirm.append((word, item))
            terms = extract_skill_terms(item) if prose else []
            if terms:
                _add_unique(required if line_section == "required" else nice, terms)
                _add_unique(required_items if line_section == "required" else nice_items, terms)
            elif prose and is_bullet:
                # A real bullet sentence naming no known skill is reported, not
                # guessed at. Unmarked lines (bullets flattened by copy-paste)
                # take the split path below instead, so they still get rated.
                if line_section == "required":
                    unscored.append(item)
            else:
                _split_required_or_nice(
                    item, line_section, required, nice, required_items, nice_items
                )
            if line_section == "required" and (
                required_line_no <= FIRST_REQUIRED_LINES_ARE_CORE or line_has_years
            ):
                positional_core.update(i.lower() for i in required_items[items_before:])

    first_title, first_company = _first_line_title_company(text)
    title_match = (
        _POSITION_HEADING_RE.search(text)
        or _TITLE_H1_RE.search(text)
        or _LABEL_TITLE_RE.search(text)
    )
    if title_match:
        title = title_match.group(1).strip(" *_\t")
    else:
        title = first_title or "Unknown Role"
    title = _TITLE_COMPANY_SPLIT_RE.split(title, maxsplit=1)[0].strip()
    title = _REQUISITION_PREFIX_RE.sub("", title).strip() or title
    if (level := title_level(title) or body_level(title, text)) is not None:
        soft.insert(0, level)

    company_match = (
        _COMPANY_BOLD_RE.search(text)
        or _COMPANY_HEADING_RE.search(text)
        or _LABEL_COMPANY_RE.search(text)
    )
    if company_match:
        company = company_match.group(1).strip(" *_\t")
    else:
        about = _ABOUT_COMPANY_RE.search(text)
        about_name = about.group(1).strip() if about else ""
        if about_name.split()[0:1] and about_name.split()[0].lower() in _ABOUT_NOT_A_COMPANY:
            about_name = ""
        company = first_company or about_name or _company_from_text(text) or "Unknown Company"
    company = _TITLE_COMPANY_SPLIT_RE.split(company, maxsplit=1)[0].strip()

    location_match = _LOCATION_BOLD_RE.search(text)
    location = location_match.group(1).strip() if location_match else None

    job_id_match = _JOB_ID_BOLD_RE.search(text)
    job_id = job_id_match.group(1).strip() if job_id_match else None

    return ParsedJD(
        required=required,
        nice_to_have=nice,
        title=title,
        company=company,
        location=location,
        job_id=job_id,
        location_check=assess_location(text),
        unscored_required=tuple(unscored),
        terms_to_confirm=tuple(to_confirm),
        possible_typos=tuple(typos),
        unknown_names=tuple(unknown),
        soft_requirements=tuple(soft),
        core_skills=_core_skills(required_items or required, positional_core, title, text),
        required_items=required_items,
        nice_items=nice_items,
    )


def looks_unknown(value: str | None) -> bool:
    """Return True if ``value`` is an empty string or a ``Unknown …`` placeholder.

    ``parse_jd`` returns ``"Unknown Company"`` / ``"Unknown Role"`` when it
    can't extract those fields, but a JD markdown file with a blank
    ``**Company:**`` line parses to ``""``. Callers that want to treat both
    the same way (i.e. "this isn't really a JD") can use this helper.
    """
    if not value:
        return True
    return value.startswith("Unknown")
