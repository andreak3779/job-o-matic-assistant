"""Pull technology/skill names out of sentence-style job-description bullets.

The fit engine (``src/jobomatic/fit/engine.py``) matches *short skill names* — "C#",
"Azure", "SQL Server" — against the profile. Many real postings instead write
requirements as full sentences ("Experience building Azure applications using
event-driven or microservice architectures"). Matched as one phrase, a sentence
never hits the profile, every such bullet reads as a genuine gap, and a
well-matched role rates ``Pass``.

``extract_skill_terms`` bridges that: it finds the vocabulary terms
(``src/jobomatic/fit/skill_vocabulary.json``) inside a sentence and returns them in the
posting's own spelling, so downstream matching and the fit table stay clean.
A sentence that contains no recognised term returns ``[]`` — the caller reports
it as *unscored* rather than guessing, so nothing is silently dropped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# "or comparable/similar/equivalent/other …" turns the preceding list into
# alternatives ("GitHub Copilot, Claude Code, Windsurf, or comparable platforms"):
# meeting any one satisfies the requirement, so it is scored as a single entry.
_ALTERNATIVES_RE = re.compile(r"\bor\s+(?:comparable|similar|equivalent|other)\b", re.IGNORECASE)
_CLAUSE_BREAK_RE = re.compile(r"\s+and\s+|[;:]")

# "tools such as A, B, or C" names examples of one category: any one of them meets the
# requirement, so the examples are scored as a single alternatives entry (ADR 0021). Unlike
# "or comparable", the list may end in "and" or "or", so the list stops at a sentence break
# or at an "and" that starts a new requirement ("... Cursor, and experience with Docker").
_EXAMPLES_RE = re.compile(
    r"\b(?:such as|for example|including|like)\b|\be\.g\.?(?![a-z0-9])|"
    # "any of the technologies the product runs on: Go, Typescript, React": any one will do
    r"\bany of\b[^:;()\n]{0,80}:|\bany of\b",
    re.IGNORECASE,
)
_PAREN_OPEN_RE = re.compile(r"\(")
_EXAMPLES_END_RE = re.compile(
    r"[;:)]|\.\s|\s+and\s+(?:experience|proficiency|knowledge|familiarity|ability|"
    r"understanding|expertise|strong|solid|a\s+good)\b",
    re.IGNORECASE,
)


def load_vocabulary(path: Path | None = None) -> tuple[str, ...]:
    """Load and validate the vocabulary; fail loudly on a malformed file (ADR 0007)."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = data.get("terms")
    if not isinstance(terms, list) or not terms or not all(isinstance(t, str) for t in terms):
        raise ValueError("skill_vocabulary.json 'terms' must be a non-empty list of strings")
    cleaned = [t.strip().lower() for t in terms]
    if any(len(t) < 2 for t in cleaned):
        raise ValueError("skill_vocabulary.json terms must be at least 2 characters")
    return tuple(dict.fromkeys(cleaned))


def load_caps_only(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> frozenset[str]:
    """Terms that count only when the posting writes them in capitals; fail loudly if unknown."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    raw = data.get("caps_only", [])
    if not isinstance(raw, list) or not all(isinstance(term, str) for term in raw):
        raise ValueError("skill_vocabulary.json 'caps_only' must be a list of strings")
    terms = frozenset(term.strip().lower() for term in raw)
    for term in sorted(terms - known):
        raise ValueError(f"caps_only term {term!r} is not in 'terms'")
    return terms


def load_category_terms(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> frozenset[str]:
    """Terms that name a kind of tool; fail loudly if one is not a vocabulary term."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    raw = data.get("category_terms", [])
    if not isinstance(raw, list) or not all(isinstance(term, str) for term in raw):
        raise ValueError("skill_vocabulary.json 'category_terms' must be a list of strings")
    terms = frozenset(term.strip().lower() for term in raw)
    for term in sorted(terms - known):
        raise ValueError(f"category term {term!r} is not in 'terms'")
    return terms


def load_umbrella_terms(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> frozenset[str]:
    """Terms too broad to join their examples; fail loudly if unknown or also a category term."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    raw = data.get("umbrella_terms", [])
    if not isinstance(raw, list) or not all(isinstance(term, str) for term in raw):
        raise ValueError("skill_vocabulary.json 'umbrella_terms' must be a list of strings")
    terms = frozenset(term.strip().lower() for term in raw)
    for term in sorted(terms - known):
        raise ValueError(f"umbrella term {term!r} is not in 'terms'")
    categories = load_category_terms(path, vocabulary=tuple(known))
    for term in sorted(terms & categories):
        raise ValueError(f"{term!r} is both an umbrella term and a category term")
    return terms


def load_phrase_expansions(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> dict[str, tuple[str, ...]]:
    """``{phrase: terms it stands for}``; fail loudly on a term the vocabulary does not know."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    raw = data.get("phrase_expansions", {})
    if not isinstance(raw, dict):
        raise ValueError("skill_vocabulary.json 'phrase_expansions' must be an object")
    out: dict[str, tuple[str, ...]] = {}
    for phrase, terms in raw.items():
        if (
            not isinstance(terms, list)
            or len(terms) < 2
            or not all(isinstance(t, str) for t in terms)
        ):
            raise ValueError(f"phrase expansion {phrase!r} needs a list of at least two terms")
        cleaned = tuple(t.strip().lower() for t in terms)
        for term in cleaned:
            if term not in known:
                raise ValueError(f"phrase expansion {phrase!r}: {term!r} is not in 'terms'")
        out[str(phrase).strip().lower()] = cleaned
    return out


def load_umbrellas(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> dict[str, tuple[str, ...]]:
    """``{umbrella term: its parts}`` from the vocabulary file; fail loudly on a bad entry."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    umbrella_terms = load_umbrella_terms(path, vocabulary=tuple(known))
    raw = data.get("umbrellas", {})
    if not isinstance(raw, dict):
        raise ValueError("skill_vocabulary.json 'umbrellas' must be an object")
    resolved: dict[str, tuple[str, ...]] = {}
    for name, parts in raw.items():
        key = str(name).strip().lower()
        if key not in umbrella_terms:
            raise ValueError(f"umbrella {key!r} is not an umbrella term")
        if isinstance(parts, str):
            continue  # resolved below
        if not isinstance(parts, list) or not parts or not all(isinstance(p, str) for p in parts):
            raise ValueError(f"umbrella {key!r} needs a non-empty list of parts")
        cleaned = tuple(dict.fromkeys(p.strip().lower() for p in parts))
        for part in cleaned:
            if part not in known:
                raise ValueError(f"umbrella {key!r}: part {part!r} is not in 'terms'")
            if part == key or part in raw:
                raise ValueError(f"umbrella {key!r}: part {part!r} is itself an umbrella")
        resolved[key] = cleaned
    for name, parts in raw.items():
        if isinstance(parts, str):
            key, target = str(name).strip().lower(), parts.strip().lower()
            if key not in umbrella_terms:
                raise ValueError(f"umbrella {key!r} is not an umbrella term")
            if target not in resolved:
                raise ValueError(f"umbrella {key!r} points at {target!r}, which has no parts")
            resolved[key] = resolved[target]
    return resolved


def umbrella_parts(skill: str) -> tuple[str, ...] | None:
    """The parts an umbrella skill is scored by ("AI" -> LLM, RAG, …), or ``None`` for a skill
    that is not an umbrella."""
    return _UMBRELLAS.get(skill.strip().lower())


def load_alternative_groups(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> dict[str, str]:
    """``{term: group name}`` from the vocabulary file; fail loudly on a bad group (ADR 0007)."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    groups = data.get("alternative_groups", {})
    if not isinstance(groups, dict):
        raise ValueError("skill_vocabulary.json 'alternative_groups' must be an object")
    group_of: dict[str, str] = {}
    for name, members in groups.items():
        if not isinstance(members, list) or len(members) < 2:
            raise ValueError(f"alternative group {name!r} needs a list of at least two terms")
        for member in members:
            term = str(member).strip().lower()
            if term not in known:
                raise ValueError(f"alternative group {name!r}: {term!r} is not in 'terms'")
            if term in group_of:
                raise ValueError(
                    f"{term!r} is in two alternative groups: {group_of[term]!r}, {name!r}"
                )
            group_of[term] = name
    return group_of


def load_list_only(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> frozenset[str]:
    """Terms that count only as a capitalised word inside a list of terms; fail loudly if unknown."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    raw = data.get("list_only", [])
    if not isinstance(raw, list) or not all(isinstance(term, str) for term in raw):
        raise ValueError("skill_vocabulary.json 'list_only' must be a list of strings")
    terms = frozenset(term.strip().lower() for term in raw)
    for term in sorted(terms - known):
        raise ValueError(f"list_only term {term!r} is not in 'terms'")
    return terms


def load_kind_nouns(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> frozenset[str]:
    """Terms that, right after a more specific term, only name its kind ("OAuth authentication")."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    raw = data.get("kind_nouns", [])
    if not isinstance(raw, list) or not all(isinstance(term, str) for term in raw):
        raise ValueError("skill_vocabulary.json 'kind_nouns' must be a list of strings")
    terms = frozenset(term.strip().lower() for term in raw)
    for term in sorted(terms - known):
        raise ValueError(f"kind_nouns term {term!r} is not in 'terms'")
    return terms


def load_or_other(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> dict[str, str]:
    """``{phrase: group name}`` for "or other <phrase>"; fail loudly on an unknown group."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = set(load_alternative_groups(path, vocabulary=vocabulary).values())
    raw = data.get("or_other", {})
    if not isinstance(raw, dict):
        raise ValueError("skill_vocabulary.json 'or_other' must be an object")
    phrase_group: dict[str, str] = {}
    for group, phrases in raw.items():
        if group not in groups:
            raise ValueError(f"or_other group {group!r} is not an alternative group")
        if not isinstance(phrases, list) or not all(isinstance(p, str) for p in phrases):
            raise ValueError(f"or_other group {group!r} needs a list of phrases")
        for phrase in phrases:
            key = phrase.strip().lower()
            if key in phrase_group:
                raise ValueError(f"or_other phrase {key!r} is listed twice")
            phrase_group[key] = group
    return phrase_group


def load_caps_only_quiet(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> dict[str, str]:
    """Terms that count only in capitals and are never queried when written otherwise, with the
    skill each stands for ("rest" -> "REST API"); fail loudly if unknown."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    raw = data.get("caps_only_quiet", {})
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in raw.items()
    ):
        raise ValueError("skill_vocabulary.json 'caps_only_quiet' must map strings to strings")
    quiet = {k.strip().lower(): v.strip() for k, v in raw.items()}
    for term in sorted(set(quiet) - known):
        raise ValueError(f"caps_only_quiet term {term!r} is not in 'terms'")
    return quiet


def load_subsumed(
    path: Path | None = None, vocabulary: tuple[str, ...] | None = None
) -> dict[str, frozenset[str]]:
    """Terms that already name the terms inside them ("ruby on rails" -> ruby, rails)."""
    if path is None:
        path = Path(__file__).with_name("skill_vocabulary.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    known = set(vocabulary if vocabulary is not None else load_vocabulary(path))
    raw = data.get("subsumed", {})
    result: dict[str, frozenset[str]] = {}
    for key, parts in raw.items():
        names = {key.lower(), *(part.lower() for part in parts)}
        for name in sorted(names - known):
            raise ValueError(f"subsumed term {name!r} is not in 'terms'")
        result[key.lower()] = frozenset(part.lower() for part in parts)
    return result


def strip_skill_punctuation(text: str) -> str:
    """``text`` without the spaces and punctuation around it, keeping the dot of ".NET".

    "Git." and ", SQL," lose their punctuation; ".NET Core" keeps its leading dot, because it is
    part of the name; "..." and ". " at the start still go."""
    text = re.sub(r"^[ ,/:;]+|[ ,./:;]+$", "", text)
    return re.sub(r"^\.+(?![A-Za-z0-9])\s*", "", text)


def _compile(terms: tuple[str, ...]) -> re.Pattern[str]:
    # Longest first so "azure devops" wins over "azure" at the same position.
    alternation = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alternation})(?:e?s)?(?![a-z0-9])")


_VOCABULARY = load_vocabulary()
_TERM_RE = _compile(_VOCABULARY)
_GROUP_OF = load_alternative_groups(vocabulary=_VOCABULARY)
_CAPS_ONLY = load_caps_only(vocabulary=_VOCABULARY)
_CAPS_ONLY_QUIET = load_caps_only_quiet(vocabulary=_VOCABULARY)
_CATEGORY_TERMS = load_category_terms(vocabulary=_VOCABULARY)
_UMBRELLA_TERMS = load_umbrella_terms(vocabulary=_VOCABULARY)
_UMBRELLAS = load_umbrellas(vocabulary=_VOCABULARY)
_PHRASE_EXPANSIONS = load_phrase_expansions(vocabulary=_VOCABULARY)
_LIST_ONLY = load_list_only(vocabulary=_VOCABULARY)
_KIND_NOUNS = load_kind_nouns(vocabulary=_VOCABULARY)
_OR_OTHER = load_or_other(vocabulary=_VOCABULARY)
_SUBSUMED = load_subsumed(vocabulary=_VOCABULARY)
_MEMBERS_OF: dict[str, list[str]] = {}
for _term, _group in _GROUP_OF.items():
    _MEMBERS_OF.setdefault(_group, []).append(_term)
_OR_OTHER_RE = re.compile(
    r"\bor\s+(?:any\s+)?(?:other|similar)\s+("
    + "|".join(re.escape(p) for p in sorted(_OR_OTHER, key=len, reverse=True))
    + r")(?![a-z0-9])",
    re.IGNORECASE,
)
# What may sit between two terms of a list for a list-only term to count: ", " / "/" / " or ".
_LIST_LINK_RE = re.compile(r"\s*(?:,\s*(?:(?:or|and)\s+)?|/)\s*|\s+(?:or|and)\s+", re.IGNORECASE)

# What may sit between two terms of one run: "A/B", "A / B", "A or B", "A, B", "A, B, or C".
# "and" is not allowed, so "A and B" is two requirements. A run only counts as alternatives
# when at least one link is a "/" or an "or" (a bare comma list names nothing about choice).
_RUN_LINK_RE = re.compile(r"\s*/\s*|\s*,\s*(?:or\s+)?|\s+(?:and/)?or\s+", re.IGNORECASE)
_CHOICE_LINK_RE = re.compile(r"/|\bor\b", re.IGNORECASE)


def _group_of(term_text: str) -> str | None:
    """The alternatives group of a matched term (its plural 's'/'es' is ignored)."""
    key = term_text.lower()
    for candidate in (
        key,
        key[:-2] if key.endswith("es") else "",
        key[:-1] if key.endswith("s") else "",
    ):
        if candidate in _GROUP_OF:
            return _GROUP_OF[candidate]
    return None


def is_kind_term(text: str) -> bool:
    """True when ``text`` is a term that names a KIND of tool (NoSQL, monitoring, AI), whose
    list after a colon holds the real requirements ("Monitoring: Datadog, Splunk")."""
    key = text.strip().lower()
    stems = {key, key[:-2] if key.endswith("es") else "", key[:-1] if key.endswith("s") else ""}
    return bool(stems & (_CATEGORY_TERMS | _UMBRELLA_TERMS))


def phrase_expansion(sentence: str) -> list[str]:
    """The terms a phrase in ``sentence`` stands for ("AI-assisted automation" -> AI, workflow
    automation), in the posting's order, or ``[]`` when it holds no such phrase."""
    flat = re.sub(r"[-\s]+", " ", sentence.lower())
    found: list[str] = []
    for phrase, terms in _PHRASE_EXPANSIONS.items():
        if phrase in flat:
            found.extend(_display(t) for t in terms if _display(t) not in found)
    return found


def _display(term: str) -> str:
    """A vocabulary term written for display ("aws" -> "AWS", "ef core" -> "EF Core")."""
    if " " not in term and len(term) <= 4:
        return term.upper()
    return " ".join(w.upper() if len(w) <= 2 else w.capitalize() for w in term.split())


def _drop_kind_nouns(sentence: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """ "OAuth authentication" asks for OAuth: the kind word right after a specific term is dropped."""
    kept: list[tuple[int, int]] = []
    for index, span in enumerate(spans):
        if sentence[span[0] : span[1]].lower() in _KIND_NOUNS and index > 0:
            previous = spans[index - 1]
            if (
                sentence[previous[0] : previous[1]].lower() not in _KIND_NOUNS
                and not sentence[previous[1] : span[0]].strip()
                and sentence[previous[1] : span[0]]
            ):
                continue
        kept.append(span)
    return kept


_GO_LANGUAGE_BEFORE_RE = re.compile(
    r"\b(?:using|in|with|of|and|knowledge of|experience (?:in|with)|proficiency in|fluency in)\s+$",
    re.IGNORECASE,
)


# "Go on the backend": a role named after the word makes it the language ("Experience with Go" alone
# stays ambiguous).
_GO_LANGUAGE_AFTER_RE = re.compile(
    r"\s+(?:on|for|as)\s+the\s+(?:back-?end|server|api|services?)\b", re.IGNORECASE
)


def _drop_unlisted_list_only(sentence: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Keep a list-only term ("Go") only when it is capitalised and sits in a list of terms."""
    others = [s for s in spans if sentence[s[0] : s[1]].lower() not in _LIST_ONLY]
    kept: list[tuple[int, int]] = []
    for span in spans:
        text = sentence[span[0] : span[1]]
        if text.lower() not in _LIST_ONLY:
            kept.append(span)
            continue
        if text != text.capitalize():
            continue
        # "using Go on the backend", "experience in Go": the language, not the verb
        if _GO_LANGUAGE_BEFORE_RE.search(
            sentence[max(0, span[0] - 30) : span[0]]
        ) and _GO_LANGUAGE_AFTER_RE.match(sentence[span[1] : span[1] + 40]):
            kept.append(span)
            continue
        before = [o for o in others if o[1] <= span[0]]
        after = [o for o in others if o[0] >= span[1]]
        joined_before = bool(before) and _LIST_LINK_RE.fullmatch(sentence[before[-1][1] : span[0]])
        joined_after = bool(after) and _LIST_LINK_RE.fullmatch(sentence[span[1] : after[0][0]])
        if joined_before or joined_after:
            kept.append(span)
    return kept


def _expand_or_other(sentence: str, out: list[str]) -> list[str]:
    """ "AWS, or other cloud platforms": the entry holding AWS grows to every cloud platform."""
    match = _OR_OTHER_RE.search(sentence)
    if not match:
        return out
    group = _OR_OTHER[match.group(1).lower()]
    for index, entry in enumerate(out):
        parts = entry.split(" / ")
        if _group_of(parts[0]) != group:
            continue
        have = {part.lower() for part in parts}
        extra = [_display(m) for m in _MEMBERS_OF[group] if m not in have]
        out[index] = " / ".join([*parts, *extra])
        # the kind named in the phrase ("CI/CD" in "or other CI/CD tools") is a label, not a skill
        label = match.group(1).lower()
        return [e for i, e in enumerate(out) if i == index or not label.startswith(e.lower())]
    return out


def _name(sentence: str, span: tuple[int, int], known: set[str]) -> str:
    """The skill as the posting spells it, but with a plural ending dropped when only the
    singular is a vocabulary term ("HTMLS" -> "HTML", "Web APis" -> "Web API"). The fit
    engine adds the plural when it searches the profile, so the singular finds both."""
    text = sentence[span[0] : span[1]]
    lower = text.lower()
    if lower in _CAPS_ONLY_QUIET:
        return _CAPS_ONLY_QUIET[lower]
    if lower in known:
        return text
    for suffix in ("es", "s"):
        if lower.endswith(suffix) and lower[: -len(suffix)] in known:
            return text[: -len(suffix)]
    return text


def _category_label(
    sentence: str, spans: list[tuple[int, int]], marker_start: int
) -> tuple[tuple[int, int], bool] | None:
    """The category or umbrella term just before "such as", and whether it joins the examples.

    ``("NoSQL", True)`` in "NoSQL databases such as MongoDB": a category term (a kind of tool)
    joins its examples. ``("AI", False)`` in "AI-assisted tools such as Copilot": an umbrella
    term is too broad to join (any AI project would meet it), so it is dropped and the examples
    carry the requirement. A product ("Python libraries such as Pandas") is neither, so it is
    left alone. The term must be at most four words before the marker with no comma or "and"
    between."""
    before = [span for span in spans if span[1] <= marker_start]
    if not before:
        return None
    label = before[-1]
    text = sentence[label[0] : label[1]].lower()
    stems = {
        text,
        text[:-2] if text.endswith("es") else "",
        text[:-1] if text.endswith("s") else "",
    }
    joins = bool(stems & _CATEGORY_TERMS)
    if not joins and not stems & _UMBRELLA_TERMS:
        return None
    between = sentence[label[1] : marker_start]
    if len(between.split()) > 4 or re.search(r"[,;:]|\band\b|\s[-–—]\s", between, re.IGNORECASE):
        return None
    return label, joins


def _alternative_runs(
    sentence: str, spans: list[tuple[int, int]], taken: set[tuple[int, int]]
) -> list[list[tuple[int, int]]]:
    """Runs of two or more same-group terms joined by "/" or "or" (never "and")."""
    runs: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    group: str | None = None

    def close() -> None:
        links = [sentence[a[1] : b[0]] for a, b in zip(current, current[1:], strict=False)]
        if len(current) >= 2 and any(_CHOICE_LINK_RE.search(link) for link in links):
            runs.append(current)

    for span in spans:
        if span in taken:
            close()
            current, group = [], None
            continue
        this_group = _group_of(sentence[span[0] : span[1]])
        link = sentence[current[-1][1] : span[0]] if current else ""
        if current and this_group == group and _RUN_LINK_RE.fullmatch(link):
            current.append(span)
            continue
        close()
        current, group = ([span], this_group) if this_group else ([], None)
    close()
    return runs


# "Java/Spring/Hibernate or React/TypeScript": slash-joined stacks offered as a choice. The terms
# need not share a group (Java is a language, React a front-end framework): the "or" between the
# two "/" lists says any one stack will do, so the whole chain is one row met by its best term.
_CHAIN_LINK_RE = re.compile(r"\s*/\s*|\s*,\s*(?:or\s+)?|\s+or\s+", re.IGNORECASE)


def _choice_chains(
    sentence: str, spans: list[tuple[int, int]], taken: set[tuple[int, int]]
) -> list[list[tuple[int, int]]]:
    chains: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []

    def close() -> None:
        links = [sentence[a[1] : b[0]] for a, b in zip(current, current[1:], strict=False)]
        # three terms, or two after a comma: "security data management, logging, or monitoring"
        if len(current) < 3 and not any(re.search(r",\s*or\s", link) for link in links):
            return
        # "A, B, or C" and "A/B or C" offer a choice whatever group the terms are in
        if any(re.search(r"\bor\b", link, re.IGNORECASE) for link in links):
            chains.append(list(current))

    for span in spans:
        if span in taken:
            close()
            current = []
            continue
        link = sentence[current[-1][1] : span[0]] if current else ""
        if current and _CHAIN_LINK_RE.fullmatch(link):
            current.append(span)
            continue
        close()
        current = [span]
    close()
    return chains


# "SQL and/or NoSQL", "Java or another object-oriented language": either one meets the requirement,
# whatever group the two terms are in, so they are one row met by the better evidence.
_EITHER_LINK_RE = re.compile(r"\s+(?:and/or|or\s+(?:another|any\s+other))\s+", re.IGNORECASE)


def _either_runs(
    sentence: str, spans: list[tuple[int, int]], taken: set[tuple[int, int]]
) -> list[list[tuple[int, int]]]:
    runs: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []

    def close() -> None:
        if len(current) >= 2:
            runs.append(list(current))

    for span in spans:
        if span in taken:
            close()
            current = []
            continue
        link = sentence[current[-1][1] : span[0]] if current else ""
        if current and _EITHER_LINK_RE.fullmatch(link):
            current.append(span)
            continue
        close()
        current = [span]
    close()
    return runs


# "solid JavaScript" praises the language; "Solid CI/CD practices" stays a question for the user.
_ADJECTIVE_BEFORE_GROUPS = frozenset(
    {"server-side language", "javascript family", "front-end framework", "relational database"}
)
_NEGATED_BEFORE_RE = re.compile(
    r"\bwithout\s+(?:(?:the\s+)?(?:reliance|use|need)\s+(?:on|of)\s+)?$", re.IGNORECASE
)

# "including concepts like layout, specificity, and accessibility": the examples illustrate the
# skill named before them, they are not further requirements.
_CONCEPT_EXAMPLES_RE = re.compile(
    r"\b(?:including|such as|like|e\.g\.?)\s+(?:concepts|topics|areas|aspects|principles)\b|"
    r"\b(?:concepts|topics|areas|aspects)\s+(?:like|such as|including)\b",
    re.IGNORECASE,
)


# "modern web frameworks such as Next.js": the examples stand for any framework of that kind.
_FRAMEWORK_LABEL_RE = re.compile(
    r"(?:web |front-?end |frontend |modern |ui )*frameworks?\s*$", re.IGNORECASE
)


def _expand_framework_examples(
    sentence: str, examples: re.Match[str] | None, out: list[str]
) -> list[str]:
    if examples is None or not _FRAMEWORK_LABEL_RE.search(sentence[: examples.start()]):
        return out
    after = sentence.lower()[examples.end() :]
    for index, entry in enumerate(out):
        parts = entry.split(" / ")
        if all(_group_of(part) == "front-end framework" for part in parts) and any(
            part.lower() in after for part in parts
        ):
            have = {part.lower() for part in parts}
            extra = [_display(m) for m in _MEMBERS_OF["front-end framework"] if m not in have]
            out[index] = " / ".join([*parts, *extra])
            break
    return out


def _drop_covered_umbrellas(terms: list[str]) -> list[str]:
    """ "AI" is not asked for separately when the same sentence names tools that make it up."""
    parts_present = {
        part.lower()
        for term in terms
        if " / " in term
        for part in term.split(" / ")
        if umbrella_parts(part.lower()) is None
    }
    kept = []
    for term in terms:
        parts = umbrella_parts(term.lower())
        if parts is not None and parts_present & set(parts):
            continue
        kept.append(term)
    return kept


def _drop_subsumed(terms: list[str]) -> list[str]:
    present = {term.lower() for term in terms}
    hidden = {part for key, parts in _SUBSUMED.items() if key in present for part in parts}
    return [term for term in terms if term.lower() not in hidden]


# "back-end (Node.js, Golang)", "tools (GitHub Copilot, Claude similar)": a bracket after a general
# noun lists examples of it, and any one of them meets the requirement.
_GENERAL_NOUN_BEFORE_PAREN_RE = re.compile(
    r"(?:back-?end|front-?end|databases?|tools?|technologies|platforms?|frameworks?|languages?|"
    r"infrastructure|services|stack|containerization|orchestration)\s*$",
    re.IGNORECASE,
)


def _bracket_example_runs(
    sentence: str, spans: list[tuple[int, int]], taken: set[tuple[int, int]]
) -> list[list[tuple[int, int]]]:
    runs: list[list[tuple[int, int]]] = []
    for open_paren in re.finditer(r"\(", sentence):
        close = sentence.find(")", open_paren.end())
        if close == -1 or not _GENERAL_NOUN_BEFORE_PAREN_RE.search(sentence[: open_paren.start()]):
            continue
        inner = sentence[open_paren.end() : close]
        if "/" in inner or re.search(r"\band\b|&", inner, re.IGNORECASE):
            # "(JavaScript/TypeScript, Vue/React)" has rows of its own; "(WSDL, SOAP, and XML)"
            # asks for all of them
            continue
        inside = [
            span
            for span in spans
            if open_paren.end() <= span[0] and span[1] <= close and span not in taken
        ]
        if len(inside) >= 2:
            runs.append(inside)
    return runs


# "Solid understanding of…" says the understanding is good; it is not SOLID, the design principles.
_SOLID_ADJECTIVE_RE = re.compile(
    r"\bsolid(?=\s+(?:understanding|experience|knowledge|grasp|foundations?|background|proficiency|"
    r"command|expertise|familiarity)\b)",
    re.IGNORECASE,
)


def find_terms_to_confirm(sentence: str) -> list[str]:
    """Words that are also skills ("solid" / SOLID) but are written here in a form that reads as
    ordinary English. They are not scored; the caller asks the user which meaning is intended."""
    found: list[str] = []
    adjective = {m.start() for m in _SOLID_ADJECTIVE_RE.finditer(sentence)}
    lower = sentence.lower()
    for solid in re.finditer(r"\bsolid\s+", lower):  # "solid JavaScript": the adjective again
        following = lower[solid.end() :]
        named = _TERM_RE.match(following)
        if named and _group_of(named.group()) in _ADJECTIVE_BEFORE_GROUPS:
            adjective.add(solid.start())
    for match in _TERM_RE.finditer(sentence.lower()):
        if match.start() in adjective:
            continue
        word = match.group()
        term = word if word in _CAPS_ONLY else word[:-1] if word[:-1] in _CAPS_ONLY else ""
        if term and not sentence[match.start() : match.end()].isupper() and term not in found:
            found.append(term)
    return found


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
# Both the word and the term must be this long. Shorter ones sit one letter from too many ordinary
# words ("sprint" and "spring", "signal" and "SignalR", "informs" and "WinForms"), and a flag that
# fires on every posting that mentions a sprint is worse than none.
_TYPO_MIN_LENGTH = 8


def _one_edit_apart(a: str, b: str) -> bool:
    """True when ``a`` becomes ``b`` by one insertion, deletion, substitution or swap."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
        if len(diffs) == 1:
            return True
        i = diffs[0]
        return len(diffs) == 2 and diffs[1] == i + 1 and a[i] == b[i + 1] and a[i + 1] == b[i]
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return any(short == long[:i] + long[i + 1 :] for i in range(len(long)))


_SINGLE_WORD_TERMS = tuple(t for t in _VOCABULARY if t.isalpha() and len(t) >= _TYPO_MIN_LENGTH)


def _is_known_form(lower: str, known: set[str]) -> bool:
    """A vocabulary term, its plural or singular, or a term with a version number ("python3")."""
    stem = lower.rstrip("0123456789")
    return any(
        form in known for form in (lower, stem, lower[:-1], lower[:-2], lower + "s", lower + "es")
    )


_NAME_SPLIT_RE = re.compile(r",|;|/|\s+or\s+|\s+and\s+", re.IGNORECASE)


def find_unknown_names(sentence: str) -> list[str]:
    """Capitalised names in a list of examples ("such as MuleSoft", "…, Foo, or similar") that
    are not in the vocabulary. They are not scored; the caller shows them so the user can see
    what the posting named that the skill list does not know."""
    segments: list[str] = []
    examples = _EXAMPLES_RE.search(sentence)
    if examples:
        tail = sentence[examples.end() :]
        end = _EXAMPLES_END_RE.search(tail)
        segments.append(tail[: end.start() if end else len(tail)])
    alt = _ALTERNATIVES_RE.search(sentence)
    if alt:
        before = sentence[: alt.start()]
        first_comma = before.find(",")
        if first_comma >= 0:  # the words before the first comma are the sentence, not a name
            segments.append(before[first_comma + 1 :])
    found: list[str] = []
    for segment in segments:
        for piece in _NAME_SPLIT_RE.split(segment):
            name = piece.strip(" :()").rstrip(". ")
            if not name or not name[0].isupper() or len(name.split()) > 3:
                continue
            if extract_skill_terms(name) or name.lower() in (n.lower() for n in found):
                continue
            found.append(name)
    return found


def find_possible_typos(sentence: str) -> list[tuple[str, str]]:
    """``(word, term)`` pairs: a word the vocabulary does not know that is one letter from a long
    vocabulary term ("Typscript" -> "typescript"). Reported for the user to check; never scored."""
    known = set(_VOCABULARY)
    found: list[tuple[str, str]] = []
    for match in _WORD_RE.finditer(sentence):
        word = match.group()
        lower = word.lower()
        if len(lower) < _TYPO_MIN_LENGTH or _is_known_form(lower, known):
            continue
        term = next((t for t in _SINGLE_WORD_TERMS if _one_edit_apart(lower, t)), None)
        if term and all(lower != w.lower() for w, _ in found):
            found.append((word, term))
    return found


def extract_skill_terms(sentence: str, vocabulary: tuple[str, ...] | None = None) -> list[str]:
    """Return the skill terms found in ``sentence``, in its own spelling, de-duplicated.

    Terms joined by "or comparable/similar/…", and the examples listed after "such as" /
    "e.g." / "including" / "like", come back as ONE entry, ``"A / B / C"``, because the fit
    engine scores a ``/``-joined skill by its best evidence (any alternative suffices). So do
    two or more terms of one alternatives group (ORMs, cloud platforms, front-end frameworks,
    ...; see ``skill_vocabulary.json``) joined by "/" or "or", never by "and".
    """
    pattern = _TERM_RE if vocabulary is None else _compile(vocabulary)
    matches = list(pattern.finditer(sentence.lower()))
    if not matches:
        return []

    spans = [(m.start(), m.end()) for m in matches]
    if vocabulary is None:  # ordinary English words count only in capitals ("SOLID", not "Solid")
        spans = [
            (s, e)
            for s, e in spans
            if sentence[s:e].lower() not in _CAPS_ONLY or sentence[s:e].isupper()
        ]
        if not spans:
            return []
    if vocabulary is None:  # "REST" is the skill; "the rest of the team" is not
        spans = [
            (s, e)
            for s, e in spans
            if sentence[s:e].lower() not in _CAPS_ONLY_QUIET or sentence[s:e].isupper()
        ]
        if not spans:
            return []
    if vocabulary is None:
        spans = _drop_kind_nouns(sentence, _drop_unlisted_list_only(sentence, spans))
        if not spans:
            return []
    # "comfortable working directly with T-SQL without reliance on Entity Framework": not asked for
    spans = [
        (s, e) for s, e in spans if not _NEGATED_BEFORE_RE.search(sentence[max(0, s - 40) : s])
    ]
    if not spans:
        return []
    concept = _CONCEPT_EXAMPLES_RE.search(sentence)
    if concept and any(e <= concept.start() for _, e in spans):
        spans = [(s, e) for s, e in spans if e <= concept.start()]
    known = set(_VOCABULARY if vocabulary is None else vocabulary)
    alternatives: list[tuple[int, int]] = []
    dropped: set[tuple[int, int]] = set()  # umbrella labels, replaced by their examples
    alt = _ALTERNATIVES_RE.search(sentence)
    examples = _EXAMPLES_RE.search(sentence)
    if examples is None and vocabulary is None:
        # "the Power Platform ecosystem (Power Apps, Power BI, SharePoint)": a bracket after a
        # category term lists examples of it, exactly as "such as" would.
        for paren in _PAREN_OPEN_RE.finditer(sentence):
            label = _category_label(sentence, spans, paren.start())
            if label and label[1]:
                examples = paren
                break
    if alt:
        before = sentence[: alt.start()]
        breaks = list(_CLAUSE_BREAK_RE.finditer(before))
        clause_start = breaks[-1].end() if breaks else 0
        if examples and clause_start < examples.end() <= alt.start():
            clause_start = examples.end()  # the label before "such as" is not an alternative
        alternatives = [(s, e) for s, e in spans if clause_start <= s and e <= alt.start()]
        # "Generative AI, GitHub Copilot, or equivalent AI coding tools": the "AI" after the
        # marker names the kind of tool the alternatives are, not a further requirement.
        tail_end = _CLAUSE_BREAK_RE.search(sentence, alt.end())
        dropped.update(
            (s, e)
            for s, e in spans
            if s >= alt.end()
            and (tail_end is None or e <= tail_end.start())
            and sentence[s:e].lower() in _UMBRELLA_TERMS
        )
        found = _category_label(sentence, spans, examples.start()) if examples else None
        if found and alternatives and found[0] not in alternatives:
            if found[1]:
                alternatives = [found[0], *alternatives]
            else:
                dropped.add(found[0])
    elif examples:
        tail = sentence[examples.end() :]
        end = _EXAMPLES_END_RE.search(tail)
        stop = examples.end() + (end.start() if end else len(tail))
        alternatives = [(s, e) for s, e in spans if examples.end() <= s and e <= stop]
        found = _category_label(sentence, spans, examples.start())
        if found and alternatives:
            if found[1]:
                alternatives = [found[0], *alternatives]
            else:
                dropped.add(found[0])

    out: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        key = text.lower()
        if key not in seen:
            seen.add(key)
            out.append(text)

    if len(alternatives) >= 2:
        add(" / ".join(_name(sentence, span, known) for span in alternatives))
    chains = _choice_chains(sentence, spans, set(alternatives))
    chained = {span for chain in chains for span in chain}
    either = _either_runs(sentence, spans, set(alternatives) | chained)
    either += _bracket_example_runs(
        sentence, spans, set(alternatives) | chained | {s for run in either for s in run}
    )
    eithered = {span for run in either for span in run}
    runs = _alternative_runs(sentence, spans, set(alternatives) | chained | eithered)
    runs = sorted([*runs, *chains, *either], key=lambda run: run[0])
    run_starting_at = {run[0]: run for run in runs}
    in_a_run = {span for run in runs for span in run}
    for span in spans:
        if span in dropped or (len(alternatives) >= 2 and span in alternatives):
            continue
        if span in run_starting_at:
            add(" / ".join(_name(sentence, run_span, known) for run_span in run_starting_at[span]))
        elif span not in in_a_run:
            add(_name(sentence, span, known))
    if vocabulary is not None:
        return out
    expanded = phrase_expansion(sentence)
    for term in expanded:
        if term.lower() not in {o.lower() for o in out}:
            out.append(term)
    out = _expand_framework_examples(sentence, examples, out)
    return _drop_covered_umbrellas(_drop_subsumed(_expand_or_other(sentence, out)))


# Words that frame a skill without adding to it: "Strong Postgresql skills", "Knowledge of Git".
_FILLER_WORDS = frozenset(
    "strong good solid excellent great working hands-on handson proven deep basic advanced "
    "practical demonstrated extensive proficient proficiency familiarity familiar knowledge "
    "framework frameworks library libraries language languages technology technologies tool tools "
    "platform platforms some firm awareness aware required mandatory essential desirable "
    "application applications "
    "knowledgeable experience experienced skills skill understanding expertise background "
    "command ability with of in using the a an and or to development methodology professional "
    "methodologies practices pipeline pipelines work programming".split()
)


def reduce_to_terms(phrase: str) -> list[str] | None:
    """Return the skill terms of a short requirement that is only a term plus filler.

    "Strong Postgresql skills" gives ``["Postgresql"]``; "Good SQL knowledge" gives ``["SQL"]``.
    Returns ``None`` when the phrase holds no known term or more than one ("CD with GitHub
    Actions" stays whole; an "A / B" alternatives entry counts as one), holds no filler (nothing to strip), or
    holds any other word ("Azure fundamentals" keeps its "fundamentals"), so a meaningful word is
    never thrown away. Never scored here: this only decides what the engine is asked to find.
    """
    terms = extract_skill_terms(phrase)
    if len(terms) != 1:  # two terms joined by "with"/"and" are a different requirement
        return None
    rest = phrase.lower()
    for term in terms:
        for part in term.split(" / "):
            rest = re.sub(re.escape(part.lower()) + r"s?(?![a-z0-9])", " ", rest)
    words = re.findall(r"[a-z0-9'-]+", rest)
    if not words or any(w not in _FILLER_WORDS for w in words):
        return None
    return terms


# Words that offer a choice or an example instead of listing requirements. A sentence holding one
# is left to the alternatives rules above ("A / B" entries) or rated whole.
_CHOICE_WORDS_RE = re.compile(
    r"\bor\b|/|\be\.g\.|\bsuch as\b|\blike\b|\bincluding\b|\bsimilar\b|\bcomparable\b|"
    r"\bequivalent\b|\bother\b|\beither\b|\bpreferably\b",
    re.IGNORECASE,
)


# What may sit between two terms of a plain list: ", " / ", and " / " and " / " & ".
_LIST_SEPARATOR_RE = re.compile(r"\s*(?:,\s*(?:and\s+)?|&\s*)|\s+and\s+", re.IGNORECASE)


def conjoined_terms(sentence: str) -> list[str] | None:
    """Return the terms of a requirement that is only a LIST of skills plus filler.

    "Experience with Azure and REST APIs" gives ``["Azure", "REST API"]``: the posting asks for
    both, so each is its own requirement and a missing one shows as a gap instead of hiding
    behind the other. Like ``reduce_to_terms`` it returns ``None`` whenever it would have to
    reinterpret the sentence:

    * fewer than two terms, or an alternatives entry ("A / B");
    * anything but a comma or "and" between two terms ("Monitoring and observability with Azure
      Monitor" and "xunit testing" are descriptions, not lists);
    * a parenthesis ("Accessibility (WCAG)" is one requirement explained, not two);
    * a choice or examples ("or", "such as", "e.g.");
    * a meaningful word before the first term or after the last ("Azure fundamentals").

    Never scored here: this only decides what the engine is asked to find.
    """
    terms = extract_skill_terms(sentence)
    if len(terms) < 2 or any(" / " in term for term in terms) or "(" in sentence:
        return None
    lower = sentence.lower()
    spans: list[tuple[int, int]] = []
    for term in terms:
        found = re.search(
            r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?:e?s)?(?![a-z0-9])", lower
        )
        if found is None:
            return None
        spans.append((found.start(), found.end()))
    spans.sort()
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        if not _LIST_SEPARATOR_RE.fullmatch(lower[end:start]):
            return None
    edges = lower[: spans[0][0]] + " " + lower[spans[-1][1] :]
    if _CHOICE_WORDS_RE.search(edges):
        return None
    if any(w not in _FILLER_WORDS for w in re.findall(r"[a-z0-9'-]+", edges)):
        return None
    return terms
