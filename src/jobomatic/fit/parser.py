"""Job-description markdown parsing shared by fit-check and gap-analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobomatic.fit.location import LocationAssessment, assess_location, is_place_name
from jobomatic.fit.soft_requirements import (
    SoftRequirement,
    body_level,
    classify,
    classify_optional,
    has_years_figure,
    is_education,
    is_eligibility,
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
    introduces_some_of,
    is_kind_term,
    names_in_list_item,
    names_mobile_in_a_list,
    phrase_expansion,
    reduce_to_terms,
    some_of_item,
    some_of_list,
    strip_skill_punctuation,
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
    # How many lines the required section held, counting the soft and unscored ones: a posting
    # with many required lines and one skill read from them was probably misread.
    required_line_count: int = 0
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
    r"qualifications|you have|who you are|"
    r"what you bring|you bring|you should (?:get in touch if|have)|about you|"
    r"your (?:skills|background|experience|profile)|ideal candidate|who we.?re looking for|"
    r"^\W*we.?re\s+looking\s+for\W*$)",
    re.IGNORECASE,
)
# "Imp:" / "Important:" on a line of its own introduces requirements. Anchored, so a heading such
# as "Implementation details" is not read as one.
_IMPORTANT_HEADING_RE = re.compile(r"^\W*(?:imp|important)\W*$", re.IGNORECASE)
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
    if not match or names_mobile_in_a_list(item):
        return item  # "...across web, backend, and mobile" is a requirement, not detail
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
    r"competenc(?:y|ies)|attributes|how you work)",
    re.IGNORECASE,
)
# "Nice-to-Have", "Nice to have", "Nice to Haves" all appear in real postings.
_NICE_HEADING_RE = re.compile(
    r"(nice[\s-]to[\s-]haves?|good[\s-]to[\s-]haves?|preferred|bonus|asset|desirable|even\s+better|"
    r"ideal\s+candidate\s+(?:would\s+)?also)",
    re.IGNORECASE,
)
# "Experience with .NET / C# is a strong asset" states one skill is optional. It is a list item,
# not a heading that opens the nice-to-have section.
_ASSET_STATEMENT_RE = re.compile(
    r"\b(?:is|are|would be)\s+(?:also\s+)?(?:a|an)?\s*(?:\w+\s+)?(?:asset|plus|bonus)\b",
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
    r"an?\s+bonus|an?\s+asset|bonus|asset|optional)\s*\)",
    re.IGNORECASE,
)
_NICE_PHRASE_RE = re.compile(
    r"\b(?:(?:is|are)\s+(?:highly\s+)?(?:preferred|desirable|desired)\b)|\bpreferred\s*\.?\s*$|"
    r"\b(?:(?:is|are|would be)\s+)?(?:preferred\s+but\s+not\s+mandatory|not\s+mandatory|"
    r"an?\s+(?:(?:strong|real|big|great|definite|huge|major|distinct)\s+)?(?:plus|asset|bonus)|"
    r"nice[\s-]to[\s-]haves?)\b",
    re.IGNORECASE,
)


# "Nice to have but strongly preferred" is not optional: the line stays required (owner's call).
_STRONGLY_PREFERRED_RE = re.compile(r"\bstrongly\s+preferred\b", re.IGNORECASE)


# "OpenAPI/Swagger (UML a plus)": a bracket that says some words are a plus applies to those words
# only; the rest of the line stays required. A bare "(a bonus)" or "(preferred)" has no words of
# its own and still marks the whole line.
_SCOPED_NICE_PAREN_RE = re.compile(
    r"\(\s*([^()]*?[A-Za-z0-9][^()]*?)\s+(?:is\s+|are\s+)?(?:an?\s+)?"
    r"(?:(?:strong|real|big|great)\s+)?(?:plus|asset|bonus)\s*\)",
    re.IGNORECASE,
)
_ARTICLE_WORDS = frozenset({"a", "an", "is", "are", "it", "this", "that", "the"})


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _split_marked_sentences(item: str) -> tuple[str, str] | None:
    """ "5+ years of HTML. Experience with Vue is a plus." -> ("5+ years of HTML.", "Experience with
    Vue ..."): a "plus" or "asset" marks only the sentence it stands in. ``None`` when the line is
    one sentence, or none or all of its sentences are marked."""
    sentences = _SENTENCE_SPLIT_RE.split(item.strip())
    if len(sentences) < 2:
        return None
    marked = [
        s for s in sentences if _NICE_PHRASE_RE.search(s) and not _STRONGLY_PREFERRED_RE.search(s)
    ]
    if not marked or len(marked) == len(sentences):
        return None
    kept = [s for s in sentences if s not in marked]
    return " ".join(kept), " ".join(marked)


def _split_scoped_nice(item: str) -> tuple[str, str] | None:
    """``(item without the bracket, the words the bracket marks optional)``, else ``None``."""
    match = _SCOPED_NICE_PAREN_RE.search(item)
    if not match or set(match.group(1).lower().split()) <= _ARTICLE_WORDS:
        return None
    rest = re.sub(r"\s+", " ", item[: match.start()] + " " + item[match.end() :]).strip(" ,;:-")
    return rest, match.group(1).strip()


def _trim_edges(text: str) -> str:
    """``text`` without punctuation at either end, keeping the leading dot of ".NET"."""
    text = re.sub(r"^[ ,;:-]+", "", text).rstrip(" ,.;:-")
    return re.sub(r"^\.+(?![A-Za-z0-9])\s*", "", text)


def _strip_nice_marker(item: str) -> tuple[str, bool]:
    """Return ``item`` without any "preferred"-style marker, and whether it had one."""
    if _STRONGLY_PREFERRED_RE.search(item):
        return item, False
    cleaned = _NICE_PREFIX_RE.sub("", item)
    cleaned = _NICE_PAREN_RE.sub(" ", cleaned)
    cleaned = _NICE_PHRASE_RE.sub(" ", cleaned)
    cleaned = _trim_edges(re.sub(r"\s+", " ", cleaned))
    return cleaned, cleaned != _trim_edges(item)


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


# Pasted postings run a heading into the text after it with no space or line break: "...the
# process.Benefits Overview", "What You'll Find HereTo do great work", "About The RoleAcme is".
# A sentence that ends and is followed at once by a capital word starts a new line; and a known
# heading followed at once by a capital word is split from what follows it.
_GLUED_SENTENCE_RE = re.compile(r"(?<=[a-z]{3}[.!?])(?=[A-Z][a-z]{2})")
# "...skills identified herein:5+ years of experience": a colon run into the figure after it
_GLUED_COLON_RE = re.compile(r"(?<=[a-z]):(?=\d+\+?\s*years)")
_GLUED_HEADING_RE = re.compile(
    r"^(\W*(?:what you.?ll find here|what you bring|what you.?ll bring|benefits overview|"
    r"why this role is unique|the tech stack|about the role|responsibilities|qualifications|"
    r"requirements|nice to haves?))(?=(?-i:[A-Z][a-z]))",
    re.IGNORECASE,
)


def _split_glued(lines: list[str]) -> list[str]:
    """``lines`` with each run-together heading or sentence put on a line of its own."""
    out: list[str] = []
    for line in lines:
        if _is_bullet(line.strip()):
            out.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        line = _GLUED_COLON_RE.sub(":\n" + indent, line)
        for piece in _GLUED_SENTENCE_RE.sub("\n", line).split("\n"):
            heading = _GLUED_HEADING_RE.match(piece)
            if heading:
                out.extend([heading.group(1), piece[heading.end() :]])
            else:
                out.append(piece)
    return out


# A pasted page that hard-wraps its bullets leaves the rest of a sentence on the next line, in lower
# case: "...translate business" / "requirements into visualization specifications".
_CONTINUATION_MIN_WORDS = 6


def _is_rest_of_a_list(line: str) -> bool:
    """ "React, NextJS, Docker": names and commas, opening on a skill. A sentence that merely
    follows a line ending in a comma is an item of its own."""
    first, comma, _ = line.partition(",")
    return bool(comma) and len(first.split()) <= 3 and bool(extract_skill_terms(first))


def _join_wrapped(lines: list[str]) -> list[str]:
    """``lines`` with each wrapped continuation joined to the long unfinished line above it."""
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and out and not _is_bullet(stripped):
            before = len(out) - 1
            while before >= 0 and not out[before].strip():
                before -= 1
            above = out[before].rstrip() if before >= 0 else ""
            # a sentence carried on in lower case, or a list carried on after its comma
            carries_on = stripped[0].islower() or (
                above.endswith(",") and before == len(out) - 1 and _is_rest_of_a_list(stripped)
            )
            if (
                carries_on
                and len(above.split()) >= _CONTINUATION_MIN_WORDS
                and not above.endswith((".", "!", "?", ";", ":"))
            ):
                out[before] = out[before].rstrip() + " " + stripped
                del out[before + 1 :]
                continue
        out.append(line)
    return out


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
    r"(what we offer|what we bring|benefits?|perks|compensation|why (?:join|work|apply|us)\b|apply now|"
    r"what you(?:\W?ll| can| will)? (?:expect|get|receive)|what we (?:provide|give)|"
    r"what.s in it for you|in return|our offer|we offer|total rewards|life at|"
    r"about (?:us|the company)|our culture|company overview|additional information|"
    r"^\W*location\W*$|"
    r"responsibilit(?:y|ies)|what you.?ll (?:be )?do(?:ing)?|salary|pay range|how to apply|"
    r"equal opportunity|culture by|our values|core values|how we work|"
    r"why (?:this role|you.?ll love)|what you.?ll find|additional perks|"
    r"(?:our|the) tech(?:nology)?(?: stack)?\W*$|our stack\W*$|"
    r"^\W*about\s+(?!you\b|the\s+(?:role|job|position|opportunity)\b|this\s+(?:role|job|position)\b))",
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
    r"equal\s+opportunity\s+employer|don.?t\s+meet\s+(?:100|every|all)\b",
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
# LinkedIn appends its category to a skill it lists: "Python (Programming Language)".
_LINKEDIN_NAME_SUFFIX_RE = re.compile(r"\s*\((?:programming language)\)", re.IGNORECASE)
_QUESTION_HEADING_RE = re.compile(
    r"^\W*(?:why\s+\w+|apply\s+now|how\s+to\s+apply)\W*$", re.IGNORECASE
)
_QUESTION_HEADING_MAX_WORDS = 5
_HEADING_MAX_WORDS = 14
_COLON_HEADING_MAX_WORDS = 16
# A longer line is a boilerplate paragraph that happens to mention the right to work.
_ELIGIBILITY_LINE_MAX_WORDS = 40
_SENTENCE_PUNCT_RE = re.compile(r"(?<!\.)[.!?][\"'\u201d\u2019)]*\s*$")
_YEARS_PREFIX_RE = re.compile(
    r"^\d+\s*\+?\s*(?:(?:[-–—]|to)\s*\d+\s*\+?\s*)?(?:years?|yrs?)\s*(?:of\s*)?",
    re.IGNORECASE,
)
# The list marker only ("- ", "• ", "1. ", "2) "); digits that belong to the line stay.
_BULLET_MARKER_RE = re.compile(r"^(?:[-•*●○◦▪▫‣]+\s*|\d+[.)]\s+)")
_LEADING_PLUS_RE = re.compile(r"^\+\s*")
_BARE_YEARS_RE = re.compile(r"^(?:years?|yrs?)\s*(?:of\s*)?", re.IGNORECASE)
_PAREN_YEARS_RE = re.compile(r"\(\d+\+?\s*years?.*\)", re.IGNORECASE)
# "CI/CD" is one practice, so its slash is not a split point (ADR 0009).
_SPLIT_COMPOUND_RE = re.compile(r"(?<!(?i:\bci))/(?!(?i:cd\b))|;|\s+or\s+|\s+and\s+")
# "SQL Server 2008 or later", "Java 11 or higher": the "or" is a version floor, not a second skill.
_VERSION_FLOOR_RE = re.compile(r"\s+or\s+(?:later|higher|newer|above|greater)\b", re.IGNORECASE)
# After a comma these words qualify the skill ("Azure experience, strongly preferred") instead of
# naming another one, so a line holding one is not a list of names.
_LIST_QUALIFIER_RE = re.compile(
    r"\b(?:preferred|required|mandatory|essential|desirable|ideally|plus|asset|bonus|nice)\b",
    re.IGNORECASE,
)
_PAREN_GROUP_SPLIT_RE = re.compile(r"\([^()]*\)")
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
# A lone "*" followed by a space is a bullet (Indeed pastes use it); "**bold**" and "*italic*" are not.
_BULLET_RE = re.compile(r"^[-•●○◦▪▫‣]|^\*\s|^\d+[.)]")

# Postings saved as label/value pairs under their own headings, e.g.
# "# Company\nExample Corp\n\n# Position\nSoftware Developer". "Postion" is
# accepted because it is a common typo in hand-saved JD files. The value may not start with "#"
# (that would be the next heading) but may contain one ("C#").
_POSITION_HEADING_RE = re.compile(
    r"^#+[ \t]*(?:position|postion|job[ \t]*title|role|title)[ \t]*\n+[ \t]*([^\n#][^\n]*)",
    re.IGNORECASE | re.MULTILINE,
)
_COMPANY_HEADING_RE = re.compile(
    r"^#+[ \t]*company[ \t]*\n+[ \t]*([^\n#][^\n]*)", re.IGNORECASE | re.MULTILINE
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
_OR_SEPARATOR_RE = re.compile(r"^\W*(?:or|and/or)\W*$", re.IGNORECASE)
_COMPANY_WORD_RE = re.compile(
    r"\b(?:Limited|Ltd|Inc|Incorporated|Corp|Corporation|LLC|LLP|Company|Group|Technologies|"
    r"Solutions|Industries|Systems|Labs)\b\.?$"
)
_FIRST_LINE_AT_RE = re.compile(r"\s+at\s+(?=[A-Z])")
_TITLE_COMPANY_SPLIT_RE = re.compile(r"\s+[—–-]\s+")
_LOCATION_BOLD_RE = re.compile(r"\*\*[Ll]ocation:\*\*\s*([^\n]+)")
_JOB_ID_BOLD_RE = re.compile(
    r"\*\*(?:[Jj]ob\s*ID|[Rr]eq(?:uisition)?\s*ID|[Jj]ob\s*Number):\*\*\s*([^\n]+)"
)


def _strip_years_prefix(item: str) -> str:
    item = strip_skill_punctuation(_YEARS_PREFIX_RE.sub("", item))
    item = _LEADING_PLUS_RE.sub("", item)
    item = strip_skill_punctuation(_BARE_YEARS_RE.sub("", item))
    item = _PAREN_YEARS_RE.sub("", item).lstrip(", ").rstrip(",. ")
    return re.sub(r"^\.+(?![A-Za-z0-9])\s*", "", item)  # the dot of ".NET" is part of its name


# "26WD100016, Principal Software Developer": a requisition number in front of the title.
_REQUISITION_PREFIX_RE = re.compile(
    r"^(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]{5,}\s*[,:]\s+|^(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]{5,}\s+[-–—]\s+"
)
# "AutoCanada is the largest Canadian owned…": a line that opens by naming the employer.
_OPENING_COMPANY_RE = re.compile(
    r"^([A-Z][A-Za-z0-9&'.-]*(?: [A-Z][A-Za-z0-9&'.-]*){0,3}) "
    r"(?:(?:is|are) (?:the|a|an|one of)\b|was founded\b)",
    re.MULTILINE,
)
_NOT_AN_OPENING_COMPANY = frozenset(
    {"we", "it", "this", "that", "there", "our", "you", "your", "position", "role", "job", "team"}
)
_REPEATED_NAME_MIN = 3
# A place or nationality repeated through a posting is not the employer.
_PLACE_WORDS = frozenset(
    {"canada", "canadian", "american", "america", "north", "united", "states", "european"}
)


_INSTITUTION_RE = re.compile(
    r"\b((?:University|College|Institute|Hospital|City|Province|Government|Ministry|School)"
    r" of [A-Z]\w+(?: [A-Z]\w+)?)"
)


def _company_from_text(text: str, title: str = "") -> str:
    """The employer's name when the posting never labels it: a first sentence of the form
    "<Name> is the…", else a capitalised word (not a skill) that appears in the text at least
    three times, mid-sentence. Empty when neither is found."""
    for match in _OPENING_COMPANY_RE.finditer(text):
        name = match.group(1).strip()
        if name.split()[0].lower() not in _NOT_AN_OPENING_COMPANY:
            return name
    institutions: dict[str, int] = {}
    for found in _INSTITUTION_RE.finditer(text):
        institutions[found.group(1)] = institutions.get(found.group(1), 0) + 1
    repeated = [name for name, n in institutions.items() if n >= 2]
    if repeated:  # "the University of Waterloo is committed ... University of Waterloo web"
        return max(repeated, key=lambda name: institutions[name])
    counts: dict[str, int] = {}
    title_words = {word.lower() for word in re.findall(r"[A-Za-z]+", title)}
    for match in re.finditer(r"(?<=[a-z,] )([A-Z][a-zA-Z]{3,}|[A-Z]{3,})\b", text):
        word = match.group(1)
        # a word of the job title ("Software" in "Senior Software Developer") is not the employer
        following = " ".join(text[match.end() : match.end() + 40].split()[:2])
        if (
            word.lower() not in title_words
            and word.lower() not in _PLACE_WORDS
            and not extract_skill_terms(word)
            # "Microsoft SQL Server", "Microsoft Azure": a vendor named before its product
            and not extract_skill_terms(f"{word} {following}")
        ):
            counts[word] = counts.get(word, 0) + 1
    best = [w for w, n in counts.items() if n >= _REPEATED_NAME_MIN]
    return _with_first_word(max(best, key=lambda w: counts[w]), text) if best else ""


def _with_first_word(name: str, text: str) -> str:
    """``name`` with the capitalised word that precedes it every time it is written mid-sentence
    ("Example Commerce … follows Example Commerce standards")."""
    before = re.findall(rf"(?:\b([A-Z][a-zA-Z]+) |(?<=[a-z,] )){re.escape(name)}\b", text)
    first = set(before)
    if len(before) >= _REPEATED_NAME_MIN and len(first) == 1 and "" not in first:
        word = before[0]
        # "Power Platform" and "Full Stack" are skills, not a company's two words
        if (
            not extract_skill_terms(f"{word} {name}")
            and word.lower() not in _NOT_AN_OPENING_COMPANY
        ):
            return f"{word} {name}"
    return name


# "Software Developer | IDENTOS Inc." ends in a period that belongs to the company name.
_CORPORATE_SUFFIX_RE = re.compile(r"\b(?:Inc|Ltd|Corp|Co|Cos|Bros|Mfg|Intl|Pty|Assoc)\.$")


# An Indeed or LinkedIn paste opens with the page's address on a line of its own ("ca.indeed.com").
_BARE_DOMAIN_RE = re.compile(
    r"^(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|ca|org|net|io)$"
)


def _looks_like_a_company_name(name: str) -> bool:
    """A short capitalised name that is not a place, "Remote" or a site address."""
    words = name.split()
    return (
        1 <= len(words) <= 4
        and all(word[:1].isupper() for word in words)
        and not any(ch.isdigit() for ch in name)
        and name.lower() not in _NOT_A_COMPANY
        and not name.lower().endswith((".com", ".ca"))
        and not is_place_name(name)
    )


# Words that make the text after "Developer / …" part of the title: "/ Team Lead", "/ Back End"
_TITLE_WORD_RE = re.compile(
    r"\b(?:senior|junior|intermediate|sr|jr|back|front|full|stack|web|mobile|software|data|cloud|"
    r"team|technical|intern|co-?op|bilingual|permanent|temporary)\b",
    re.IGNORECASE,
)


def _is_company_after_a_slash(name: str) -> bool:
    """True when what follows "Title /" names an employer, not a second title, a skill or a way
    of working ("Developer / Analyst", "Developer / C#", "Developer / Remote")."""
    return (
        _looks_like_a_company_name(name)
        and not _ROLE_WORD_RE.search(name)
        and not _TITLE_WORD_RE.search(name)
        and not extract_skill_terms(name)
    )


# "Springfield, MD" or "Toronto, Ontario": a city and its province or state
_CITY_REGION_RE = re.compile(r"^[A-Z][A-Za-z .'-]+,\s*(?:[A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?)$")


def _title_place_company(line: str) -> list[str] | None:
    """``[title, company]`` of a dashed line of three or more parts, one of them a place or a way
    of working and exactly one an employer by its corporate word ("… Group", "… Inc.")."""
    title, *rest = [part.strip() for part in _TITLE_COMPANY_SPLIT_RE.split(line)]
    if len(rest) < 2 or not _ROLE_WORD_RE.search(title):
        return None
    placed = any(
        _CITY_REGION_RE.match(part) or is_place_name(part) or part.lower() in _NOT_A_COMPANY
        for part in rest
    )
    employers = [
        part for part in rest if _COMPANY_WORD_RE.search(part) and not _ROLE_WORD_RE.search(part)
    ]
    if not placed or len(employers) != 1:
        return None
    return [title, employers[0]]


def _first_line_title_company(text: str) -> tuple[str | None, str | None]:
    """Title and company from the first line of a pasted posting, when it looks like a title.

    "Sr. Software Engineer (.NET core, Angular) | Example Co" -> both; "Backend Developer at
    Example Co" -> both; a first line that is a sentence, or names no role, gives nothing."""
    for raw in text.splitlines():
        line = raw.strip().lstrip("#*_> \t").rstrip("*_ \t")
        if not line or _BARE_DOMAIN_RE.match(line):
            continue
        if len(line) > 140 or (
            line.endswith((".", "!", "?", ":")) and not _CORPORATE_SUFFIX_RE.search(line)
        ):
            return None, None
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2:
            parts = [part.strip() for part in _FIRST_LINE_AT_RE.split(line, maxsplit=1)]
        if len(parts) < 2:
            # "Technical Lead - Acme Industries Limited": a corporate name after a dash
            dashed = [part.strip() for part in _TITLE_COMPANY_SPLIT_RE.split(line)]
            if len(dashed) == 2 and (
                _COMPANY_WORD_RE.search(dashed[1]) or _looks_like_a_company_name(dashed[1])
            ):
                parts = dashed
        if len(parts) < 2:
            # "Developer - Springfield, MD - Example Group": title, place and employer
            parts = _title_place_company(line) or parts
        if len(parts) < 2:
            # "Back End Developer / Example Co": position / company
            head, slash, tail = line.rpartition(" / ")
            if slash and _is_company_after_a_slash(tail.strip()):
                parts = [head.strip(), tail.strip()]
        if not _ROLE_WORD_RE.search(parts[0]):
            return None, None
        company = next(
            (p for p in parts[1:] if p and p.lower() not in _NOT_A_COMPANY and len(p.split()) <= 6),
            None,
        )
        return parts[0], company
    return None, None


# LinkedIn's header: "C# SQL Developer (Remote)" on one line, "HCLTech • Canada (Remote)" on the next.
_HEADER_COMPANY_RE = re.compile(r"^([^•|]{2,60}?)\s+•\s+\S")


def _header_company(text: str) -> str | None:
    """The company of a "Title" line followed by a "Company • Location" line, else ``None``."""
    lines = [raw.strip().lstrip("#*_> \t") for raw in text.splitlines() if raw.strip()]
    if len(lines) < 2 or not _ROLE_WORD_RE.search(lines[0]):
        return None
    match = _HEADER_COMPANY_RE.match(lines[1])
    if not match:
        # "Senior Software Engineer" / "Microsoft Canada Inc." / "Toronto ON - Work Remotely"
        second = lines[1].strip(" *_")
        if _CORPORATE_SUFFIX_RE.search(second) and len(second.split()) <= 6:
            return second
        return None
    name = match.group(1).strip(" *_")
    if len(name.split()) > 6 or name.lower() in _NOT_A_COMPANY:
        return None
    return name


# LinkedIn's job card: "Company logo for, ClickUp." / "ClickUp" / "Staff Frontend Engineer" / then
# "Canada · Reposted 2 weeks ago · Over 100 applicants". The title is the line above that one.
_CARD_LOGO_RE = re.compile(r"^Company logo for,?\s*(.+?)\.?$", re.IGNORECASE)
_NAME_LOGO_RE = re.compile(r"^([A-Z][\w&.' -]{1,60}?)\s+logo$")


def _full_company_name(name: str, text: str) -> str:
    """``name`` with the corporate word the posting itself writes after it ("… Group")."""
    full = re.search(
        re.escape(name) + r"\s+(?:Group|Inc\.?|Ltd\.?|Limited|Corporation|Corp\.?)(?![A-Za-z])",
        text,
    )
    return full.group(0) if full else name


_CARD_META_RE = re.compile(r"\s·\s.*\b(?:ago|applicants?|clicked apply)\b", re.IGNORECASE)


_CARD_COMPANY_MAX_WORDS = 6


def _card_header(text: str) -> tuple[str | None, str | None]:
    """Title and company of a pasted LinkedIn job card, else ``(None, None)``."""
    lines = [
        raw.strip().lstrip("#*_> \t").rstrip("*_ \t") for raw in text.splitlines() if raw.strip()
    ]
    if not lines:
        return None, None
    if (
        len(lines) >= 2
        and (named := _NAME_LOGO_RE.match(lines[0]))
        and _ROLE_WORD_RE.search(lines[1])
        and not _CARD_LOGO_RE.match(lines[0])
    ):
        return lines[1], _full_company_name(named.group(1).strip(), text)
    if not (logo := _CARD_LOGO_RE.match(lines[0])):
        # The same card without the logo line: "Render" / "Software Engineer" / "Canada · 1 day ago"
        if (
            len(lines) >= 3
            and _CARD_META_RE.search(lines[2])
            and "|" not in lines[0]
            and len(lines[0].split()) <= _CARD_COMPANY_MAX_WORDS
            and _ROLE_WORD_RE.search(lines[1])
        ):
            return lines[1], lines[0]
        return None, None
    company = logo.group(1).strip()  # "Inc.." keeps the "." of "Inc." and drops the sentence's
    for index, line in enumerate(lines[1:6], start=1):
        if _CARD_META_RE.search(line):
            title = lines[index - 1] if index >= 2 else None
            return (title if title and title.lower() != company.lower() else None), company
    return None, company


_H1_LINE_RE = re.compile(r"^#[ \t]+(\S[^\n]*)$")


def _h1_title_company(text: str) -> tuple[str | None, str | None]:
    """ "# Siemens Healthineers" followed at once by "# Senior Software Developer": the two
    top-level headings are the company and the title, in either order."""
    headings: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if headings:
                break  # a blank line ends the run of headings
            continue
        match = _H1_LINE_RE.match(line)
        if not match:
            break
        headings.append(match.group(1).strip(" *_"))
        if len(headings) == 2:
            break
    if len(headings) != 2:
        return None, None
    first, second = headings
    first_is_role = bool(_ROLE_WORD_RE.search(first))
    second_is_role = bool(_ROLE_WORD_RE.search(second))
    if second_is_role and not first_is_role and _looks_like_a_company_name(first):
        return second, first
    if first_is_role and not second_is_role and _looks_like_a_company_name(second):
        return first, second
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


def split_compound(item: str) -> list[str]:
    """The pieces a short requirement line is made of.

    Splits on "/", ";", "and" and "or" as before, and on commas when the line is a bare list of
    names ("SSRS, SSIS, Crystal Reports"). Three things are never split:

    * what is inside parentheses: "JavaScript (utilizing JSON and AJAX)" and "Microsoft .NET
      Platform (4.0 or higher)" are one requirement each, the parenthesis is detail on it;
    * a version floor: "SQL Server 2008 or later" is SQL Server, and "later" is not a skill;
    * a sentence, a "Heading: detail" line, or a comma that adds a qualifier ("Azure, preferred"),
      where the comma is punctuation and not a list.
    """
    groups: list[str] = []

    def hide(match: re.Match[str]) -> str:
        groups.append(match.group(0))
        return f"\x00{len(groups) - 1}\x00"

    masked = _PAREN_GROUP_SPLIT_RE.sub(hide, item)
    masked = _VERSION_FLOOR_RE.sub("", masked)
    pieces = _SPLIT_COMPOUND_RE.split(masked)
    if (
        "," in masked
        and ":" not in masked
        and not _is_prose(item)
        and not _LIST_QUALIFIER_RE.search(masked)
    ):
        pieces = [part for piece in pieces for part in piece.split(",")]
    restored = [re.sub(r"\x00(\d+)\x00", lambda m: groups[int(m.group(1))], p) for p in pieces]
    return [strip_skill_punctuation(p) for p in restored]


_TRAILING_BRACKET_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")


def _head_without_example_brackets(item: str) -> str:
    """ "Experience with Agile methodologies (Scrum/Kanban)" asks for Agile: the bracket only names
    examples of it. Dropped when every word in the bracket is a known skill and what is left
    reduces to one term; "Azure fundamentals (App Service, Functions)" keeps its bracket."""
    match = _TRAILING_BRACKET_RE.match(item)
    if not match:
        return item
    head, inner = match.group(1), match.group(2)
    words = [w for w in re.split(r"[\s,/&]+|\band\b|\bor\b|\betc\.?", inner) if w]
    if not words or not all(extract_skill_terms(w) for w in words):
        return item
    return head if reduce_to_terms(head) is not None else item


def _split_required_or_nice(
    item: str,
    section: str,
    required: list[str],
    nice: list[str],
    required_items: list[str],
    nice_items: list[str],
) -> None:
    item = _head_without_example_brackets(item)
    flat = required if section == "required" else nice
    items = required_items if section == "required" else nice_items
    pieces = [p for p in split_compound(item) if len(p) >= 2]
    # A short bullet that is only a choice between same-kind tools ("AWS or Azure",
    # "Entity Framework/Dapper") is one requirement met by either (ADR 0021).
    entries = extract_skill_terms(item)
    is_choice = False
    if _CHOICE_INTRO_RE.match(item) and len(entries) == 1 and " / " in entries[0]:
        # "One or more of: C#, Java": a short line that opens with the choice
        pieces = entries
        is_choice = True
    elif phrase_expansion(item):
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
    elif (
        (not entries or (len(entries) == 1 and " / " not in entries[0]))
        and _PLAIN_CHOICE_RE.fullmatch(item)
        and len(pieces) == 2
    ):
        # "Fullstack or backend development experience" names no known skill, but "or" still
        # offers a choice: one row, met by whichever the profile shows better.
        pieces = [" / ".join(pieces)]
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


_CHOICE_INTRO_RE = re.compile(
    r"^(?:any|one\s+or\s+more|at\s+least\s+one|one)\s+of\b", re.IGNORECASE
)
# Two plain phrases joined by "or" and nothing else: no "and", slash, comma or bracket.
_PLAIN_CHOICE_RE = re.compile(r"[^/,;()]+?\s+or\s+(?!and\b)[^/,;()]+?", re.IGNORECASE)
FIRST_REQUIRED_LINES_ARE_CORE = 5
# A flat line longer than this is a paragraph, not a list item.
_FLAT_ITEM_MAX_WORDS = 25
# The same bounds for a line of a copy that has no bullets or indents at all
_UNMARKED_ITEM_MIN_WORDS = 4
_UNMARKED_ITEM_MAX_WORDS = 40


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
        # "Windows Communication Foundation" holds a soft-skill word but is a skill name
        if is_soft_skill(item) and key not in (t.lower() for t in extract_skill_terms(item)):
            continue
        if key in positional:
            core.add(key)
            continue
        for term in _item_terms(item):
            if _mention_count(term, [title]) or _mention_count(term, lines) >= 2:
                core.add(key)
                break
    return frozenset(core)


# "we're seeing a growing amount of .NET work, so if you've got .NET experience, we especially
# want to hear from you": what a posting says it especially wants is a requirement, even when the
# list below calls it an asset.
_ESPECIALLY_WANTED_RE = re.compile(
    r"\b(?:especially|particularly)\s+(?:want|like|love|keen|eager|interested)\b[^.!?]{0,20}"
    r"\b(?:hear|hearing)\s+from\s+you\b",
    re.IGNORECASE,
)


def _especially_wanted(text: str) -> set[str]:
    """The lowercased skill names in the sentences where the posting says what it especially
    wants to hear about."""
    return {
        name.lower()
        for line in text.splitlines()
        for sentence in _SENTENCE_SPLIT_RE.split(line)
        if _ESPECIALLY_WANTED_RE.search(sentence)
        for entry in extract_skill_terms(sentence)
        for name in entry.split(" / ")
    }


def _move(entries: list[str], source: list[str], target: list[str]) -> None:
    for entry in entries:
        source.remove(entry)
    _add_unique(target, entries)


def _indent(line: str) -> int:
    return len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())


# A second line between the introduction and its list: "Expertise in the following tools:"
_LIST_LEAD_IN_RE = re.compile(r"\bthe following\b[^:]{0,80}:$", re.IGNORECASE)


def _is_bare_name(line: str) -> bool:
    """A line that can only be a name in a list: one capitalised word, or exactly a known skill."""
    if len(line.split()) == 1:
        return line[0].isupper() or line[0] == "."
    return [term.lower() for term in extract_skill_terms(line)] == [line.lower()]


# "Our stack spans A, B, C. You don't need all of it. You should be deep in several of these":
# the stack sentence, followed by words that make it a pool rather than a checklist
_STACK_POOL_RE = re.compile(
    r"^(?:our|the)\s+(?:tech(?:nology)?\s+)?stack\s+(?:spans|includes|covers|consists\s+of|is)\s+"
    r"(?P<names>.+?)\.\s+"
    r"(?=.*\b(?:(?:don['’]?t|do\s+not|needn['’]?t)\s+need\s+(?:all|every)|"
    r"deep\s+in\s+(?:several|some|a\s+few)|(?:some|several|a\s+few)\s+of\s+(?:these|them|it))\b)",
    re.IGNORECASE,
)


def _split_paired_names(names: str) -> str:
    """ "TypeScript/Node.js" names two skills; "CI/CD" is one."""

    def split(match: re.Match[str]) -> str:
        pair = match.group(0)
        halves = pair.split("/")
        if len(extract_skill_terms(pair)) == 1 or not all(map(extract_skill_terms, halves)):
            return pair
        return ", ".join(halves)

    return re.sub(r"[^,/]+(?:/[^,/]+)+", lambda m: split(m), names)


def _rewrite_stack_pools(lines: list[str]) -> list[str]:
    """``lines`` with a "pick several of our stack" paragraph written as the requirement it is."""
    out: list[str] = []
    for line in lines:
        found = _STACK_POOL_RE.match(line.strip())
        names = _split_paired_names(found["names"]) if found else ""
        folded = f"Experience with several of: {names}"
        if found and some_of_list(folded) is not None:
            out.extend(["Requirements:", f"- {folded}"])
        else:
            out.append(line)
    return out


def _fold_some_of_lists(lines: list[str]) -> list[str]:
    """``lines`` with "some of the following:" and the bullets or indented lines under it made
    into one line, so it is read like the same list written after the colon (ADR 0038).

    Under a bullet only deeper-indented lines belong to it; under any other line, bullets and
    indented lines do. The list is left as written unless it holds enough names to be one. A line
    under it that names nothing ("A sentence about our team") stays a line of its own."""
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        intro = line.strip()
        index += 1
        if not introduces_some_of(intro):
            out.append(line)
            continue
        names: list[str] = []
        unread: list[str] = []
        end = index
        lead_in_allowed = True
        for position in range(index, len(lines)):
            stripped = lines[position].strip()
            if not stripped:
                continue
            if lead_in_allowed and not names and _LIST_LEAD_IN_RE.search(stripped):
                lead_in_allowed = False
                continue
            deeper = _indent(lines[position]) > _indent(line)
            if _is_bullet(intro):
                belongs = deeper
            else:
                level = _indent(lines[position]) == _indent(line)
                belongs = deeper or _is_bullet(stripped) or (level and _is_bare_name(stripped))
            if not belongs or introduces_some_of(stripped):
                break
            found = names_in_list_item(_BULLET_MARKER_RE.sub("", stripped).strip())
            names.extend(found)
            if not found:
                unread.append(lines[position])
            end = position + 1
        head = _BULLET_MARKER_RE.sub("", intro).strip()
        folded = f"{head} {', '.join(names)}"
        if some_of_list(folded) is None:
            out.append(line)
            continue
        # "You have some of the following:" also opens the section, so it stays as a heading
        if not _is_bullet(intro) and (
            _REQUIRED_HEADING_RE.search(intro) or _NICE_HEADING_RE.search(intro)
        ):
            out.append(line)
        out.append(f"- {folded}")
        out.extend(unread)
        index = end
    return out


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
    list_is_marked = False  # the current section's items are bullets or indented lines
    required_line_no = 0
    required_lines_total = 0
    positional_core: set[str] = set()
    # what each optional line added to (nice, nice_items), so a whole line can become required
    optional_lines: list[tuple[list[str], list[str]]] = []
    # After a heading that ends in a colon ("Required Skills:"), plain unindented lines with no
    # end punctuation are its items: a copied page often loses the bullets and the indent.
    flat_items_ok = False

    prepared = _unglue_bullets(_split_glued(_join_wrapped(text.splitlines())))
    # a copy that lost every bullet and indent: nothing marks a list item
    unmarked = not any(
        _is_bullet(line.strip()) or line.startswith(("\t", "  ")) for line in prepared
    )
    for raw in _fold_some_of_lists(_rewrite_stack_pools(prepared)):
        stripped = raw.strip()
        lower = stripped.lower()
        if not stripped or _OR_SEPARATOR_RE.match(stripped):
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
        ) or (
            # "Why Apply?" / "Apply Now!": a short call to action is a heading, not a sentence
            not is_bullet
            and not is_indented
            and len(stripped.split()) <= _QUESTION_HEADING_MAX_WORDS
            and _QUESTION_HEADING_RE.match(stripped) is not None
        )
        # A heading is short. A long line that happens to hold a heading word ("…, Not
        # Nice-to-haves … Day To Day, You Will" or "…the above qualifications, you should still")
        # is a sentence and must not open or close a section.
        # A longer line still counts when it ends in a colon, as a heading does ("Things we're
        # looking for in terms of more specific skill-sets and experience:").
        word_count = len(stripped.split())
        keyword_heading = looks_like_heading and (
            word_count <= _HEADING_MAX_WORDS
            or (stripped.endswith(":") and word_count <= _COLON_HEADING_MAX_WORDS)
        )
        if (
            keyword_heading
            and _ASSET_STATEMENT_RE.search(stripped)
            and extract_skill_terms(stripped)
        ):
            keyword_heading = False
            states_a_skill = True
        else:
            states_a_skill = False
        # Nice-to-have is tested first: "Preferred Qualifications" and
        # "Nice-to-Have Qualifications" also contain the required-heading word
        # "qualifications", and must not be read as required skills.
        if keyword_heading and _SOFT_HEADING_RE.search(lower) and "technical" not in lower:
            section = "soft"
            list_is_marked = False
            flat_items_ok = False
            continue
        if keyword_heading and _NICE_HEADING_RE.search(lower):
            section = "nice"
            list_is_marked = False
            flat_items_ok = stripped.endswith(":")
            continue
        if keyword_heading and (
            _REQUIRED_HEADING_RE.search(lower)
            or _EXPERIENCE_HEADING_RE.match(stripped)
            or _IMPORTANT_HEADING_RE.match(stripped)
        ):
            section = "required"
            list_is_marked = False
            flat_items_ok = stripped.endswith(":")
            continue
        if keyword_heading and _SECTION_END_HEADING_RE.search(lower):
            section = None
            list_is_marked = False
            flat_items_ok = False
            continue
        if (not is_bullet and _LABEL_LINE_END_RE.match(stripped)) or _CLOSING_BOILERPLATE_RE.search(
            stripped
        ):
            section = None
            list_is_marked = False
            flat_items_ok = False
            continue
        # Content is either a real bullet, or (for postings that flatten
        # bullets to plain indented sentences when copy-pasted) any
        # non-heading-shaped line — `looks_like_heading` already excludes
        # actual heading lines, so this only picks up prose sentences sitting
        # under a recognized section.
        # A list whose items are bullets or indented lines ends at the first sentence at the left
        # margin: "We're hiring across multiple teams..." after the last item is not an item.
        if (
            section
            and list_is_marked
            and not is_bullet
            and not is_indented
            and _SENTENCE_PUNCT_RE.search(stripped)
        ):
            section = None
            list_is_marked = False
            continue
        if looks_like_heading and stripped.endswith(":"):
            flat_items_ok = False  # a heading the parser does not know: its lines are not items
        # in an unmarked copy a longer line that names a skill is an item; a short one may be a
        # sub-heading
        unmarked_item = (
            unmarked
            and _UNMARKED_ITEM_MIN_WORDS <= len(stripped.split()) <= _UNMARKED_ITEM_MAX_WORDS
            and bool(extract_skill_terms(stripped))
        )
        flat_item = (
            section in ("required", "nice")
            and looks_like_heading
            and (
                unmarked_item
                or (
                    (flat_items_ok or states_a_skill)
                    and len(stripped.split()) <= _FLAT_ITEM_MAX_WORDS
                )
            )
        )
        if section and (is_bullet or not looks_like_heading or flat_item):
            # a list under "…:" ends at the first closing sentence; items picked out of an
            # unmarked copy do not mark a list
            list_is_marked = (
                list_is_marked or is_bullet or is_indented or (flat_item and flat_items_ok)
            )
            raw_item = _LINKEDIN_NAME_SUFFIX_RE.sub("", _BULLET_MARKER_RE.sub("", stripped)).strip()
            item = _drop_term_details(_strip_years_prefix(raw_item))
            line_section = section
            if section == "required":
                required_lines_total += 1
            if section == "soft":
                soft.append(soft_skill(raw_item))
                continue
            prose = _is_prose(item)  # decided before a marker is removed, as before this rule
            if section == "required":
                if (sentences := _split_marked_sentences(item)) is not None:
                    item, optional = sentences
                    optional_terms = extract_skill_terms(_strip_nice_marker(optional)[0])
                    _add_unique(nice, optional_terms)
                    _add_unique(nice_items, optional_terms)
                if (scoped := _split_scoped_nice(item)) is not None:
                    item, optional = scoped
                    optional_terms = extract_skill_terms(optional)
                    _add_unique(nice, optional_terms)
                    _add_unique(nice_items, optional_terms)
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
            nice_before, nice_items_before = len(nice), len(nice_items)
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
            if line_section in ("required", "nice") and (pool := some_of_list(item)):
                # "some of: A, B, C" is one requirement over a pool of names (ADR 0038)
                _add_unique(required if line_section == "required" else nice, pool)
                grouped = required_items if line_section == "required" else nice_items
                _add_unique(grouped, [some_of_item(pool)])
                if line_section == "required" and (
                    required_line_no <= FIRST_REQUIRED_LINES_ARE_CORE or line_has_years
                ):
                    positional_core.add(some_of_item(pool).lower())
                elif line_section == "nice":
                    optional_lines.append((nice[nice_before:], nice_items[nice_items_before:]))
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
            elif prose and line_section == "required":
                # A required sentence naming no known skill is reported, not guessed at, whether
                # or not it kept its bullet marker: rated whole it could only ever read as a gap.
                unscored.append(item)
            elif prose and is_bullet:
                pass  # an optional bullet sentence naming no known skill is not listed
            elif (
                line_section == "required"
                and is_prose_requirement(item)
                and not extract_skill_terms(item)
            ):
                # six words with no known skill ("Outcomes oriented. You focus on impact.") would
                # be rated whole too: same rule, same list
                unscored.append(item)
            else:
                _split_required_or_nice(
                    item, line_section, required, nice, required_items, nice_items
                )
            if line_section == "required" and (
                required_line_no <= FIRST_REQUIRED_LINES_ARE_CORE or line_has_years
            ):
                positional_core.update(i.lower() for i in required_items[items_before:])
            elif line_section == "nice":
                optional_lines.append((nice[nice_before:], nice_items[nice_items_before:]))

    wanted = _especially_wanted(text)
    for flat, items in optional_lines:
        if any(name.lower() in wanted for item in items for name in _item_terms(item)):
            _move(flat, nice, required)
            _move(items, nice_items, required_items)
            positional_core.update(item.lower() for item in items)

    # "Applicants must be authorized to work in Canada" sits in closing boilerplate as often as in
    # a requirements list: list it for the user wherever it stands.
    listed = {entry.line for entry in soft}
    for raw_line in text.splitlines():
        for sentence in _SENTENCE_SPLIT_RE.split(
            _BULLET_MARKER_RE.sub("", raw_line.strip()).strip()
        ):
            if (
                sentence
                and len(sentence.split()) <= _ELIGIBILITY_LINE_MAX_WORDS
                and is_eligibility(sentence)
                and not any(sentence in seen for seen in listed)
            ):
                soft.extend(entry for entry in classify(sentence) if entry.kind == "eligibility")
                listed.add(sentence)

    first_title, first_company = _first_line_title_company(text)
    if first_title and not first_company:
        first_company = _header_company(text)
    card_title, card_company = _card_header(text)
    pair_title, pair_company = _h1_title_company(text)
    card_title = card_title or pair_title
    card_company = card_company or pair_company
    first_title = card_title or first_title
    first_company = card_company or first_company
    title_match = (
        None
        if card_title
        else _POSITION_HEADING_RE.search(text)
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
        company = (
            first_company or about_name or _company_from_text(text, title) or "Unknown Company"
        )
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
        required_line_count=required_lines_total,
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
