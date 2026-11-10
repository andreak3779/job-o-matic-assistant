"""Deterministic location / work-arrangement check for job descriptions.

The candidate can't take some postings regardless of skill fit: roles in excluded regions
(for example Quebec), hybrid or on-site roles outside the home city, remote roles limited to
Atlantic Canada, and roles that list French as a requirement. This module turns those rules
into a ``LocationAssessment`` that ``fit_engine.rate_fit`` folds into the rating: any
disqualifier forces ``Pass``; ambiguous cases only add advisory flags.

Two files feed the rules. ``src/jobomatic/fit/location_rules.json`` holds the place-name vocabulary and
is part of the code. The personal part (home city and province, which regions are excluded,
whether French-required roles are excluded) is read from the vault's
``profile/location-preferences.json`` (ADR 0013); the code repo only ships a fictional
``src/jobomatic/fit/location_preferences.example.json``.

Design constraints, in the spirit of ADR 0001/0007:

* Deterministic and testable — plain regex over the JD text, no LLM.
* Conservative on *disqualifying*: a ``Pass`` gates real applications, so it
  is only triggered by explicit location lines (``Location:`` label, the title
  line, or a short line that opens with remote/hybrid/on-site), never by an
  incidental mention such as "we have an office in Montreal" in a company
  blurb. French is the one exception and is scanned across the whole posting,
  because it is stated in requirement prose rather than a location line.
* Ambiguity (e.g. "CA-Nationwide" listed beside Quebec and Nova Scotia,
  hybrid with no stated city) is surfaced as a flag, never silently decided.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jobomatic import paths


@dataclass(frozen=True)
class LocationAssessment:
    """Outcome of checking a JD against the job-search location rules."""

    disqualifiers: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()

    @property
    def disqualified(self) -> bool:
        return bool(self.disqualifiers)


@dataclass(frozen=True)
class _Region:
    label: str
    terms: tuple[str, ...]
    abbreviations: tuple[str, ...]


@dataclass(frozen=True)
class _Rules:
    home_label: str
    home_province_label: str
    excluded: frozenset[str]
    french_excluded: bool
    home_city: tuple[str, ...]
    home_province: tuple[str, ...]
    home_province_abbr: tuple[str, ...]
    quebec: _Region
    atlantic: _Region
    other_terms: tuple[str, ...]
    other_abbr: tuple[str, ...]
    nationwide: tuple[str, ...]
    remote: tuple[str, ...]
    hybrid: tuple[str, ...]
    onsite: tuple[str, ...]
    french_language: tuple[str, ...]
    french_requirement: tuple[str, ...]
    french_softener: tuple[str, ...]


def _str_list(data: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise ValueError(f"location_rules.json {where}.{key} must be a non-empty list of strings")
    return tuple(v.lower() for v in value)


def _region(data: dict[str, Any], name: str) -> _Region:
    entry = data.get("excluded_regions", {}).get(name)
    if not isinstance(entry, dict):
        raise ValueError(f"location_rules.json excluded_regions.{name} must be an object")
    label = entry.get("label")
    if not isinstance(label, str) or not label:
        raise ValueError(f"location_rules.json excluded_regions.{name}.label must be a string")
    where = f"excluded_regions.{name}"
    return _Region(
        label, _str_list(entry, "terms", where), _str_list(entry, "abbreviations", where)
    )


PREFERENCES_FILENAME = "location-preferences.json"
_REGIONS = ("quebec", "atlantic")


def preferences_path() -> Path:
    """The candidate's location preferences, kept in the vault."""
    return paths.profile_dir() / PREFERENCES_FILENAME


def _load_preferences(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"No location preferences at {path}. Create it in the vault; "
            "src/jobomatic/fit/location_preferences.example.json shows the shape."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def load_rules(path: Path | None = None, preferences: Path | None = None) -> _Rules:
    """Load and validate the rules and the candidate's preferences; fail loudly on a bad entry."""
    if path is None:
        path = Path(__file__).with_name("location_rules.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    prefs = _load_preferences(preferences or preferences_path())
    home = prefs.get("home", {})
    label = home.get("label")
    province_label = home.get("province_label")
    if not isinstance(label, str) or not label or not isinstance(province_label, str):
        raise ValueError("location preferences home.label and home.province_label must be strings")
    excluded = prefs.get("excluded_regions", [])
    if not isinstance(excluded, list) or not set(excluded) <= set(_REGIONS):
        raise ValueError(f"location preferences excluded_regions must be a subset of {_REGIONS}")
    other = data.get("other_places", {})
    arrangement = data.get("arrangement_terms", {})
    french = data.get("french", {})
    home_city = _str_list(home, "city", "home")
    home_province = _str_list(home, "province", "home")
    home_abbr = _str_list(home, "province_abbreviations", "home")
    home_terms = {*home_city, *home_province}
    return _Rules(
        home_label=label,
        home_province_label=province_label,
        excluded=frozenset(excluded),
        french_excluded=bool(prefs.get("exclude_french_required", False)),
        home_city=home_city,
        home_province=home_province,
        home_province_abbr=home_abbr,
        quebec=_region(data, "quebec"),
        atlantic=_region(data, "atlantic"),
        # The home place is never "somewhere else", whatever the vocabulary lists.
        other_terms=tuple(
            t for t in _str_list(other, "terms", "other_places") if t not in home_terms
        ),
        other_abbr=tuple(
            a for a in _str_list(other, "abbreviations", "other_places") if a not in home_abbr
        ),
        nationwide=_str_list(data, "nationwide_terms", "root"),
        remote=_str_list(arrangement, "remote", "arrangement_terms"),
        hybrid=_str_list(arrangement, "hybrid", "arrangement_terms"),
        onsite=_str_list(arrangement, "onsite", "arrangement_terms"),
        french_language=_str_list(french, "language_terms", "french"),
        french_requirement=_str_list(french, "requirement_terms", "french"),
        french_softener=_str_list(french, "softener_terms", "french"),
    )


def _norm(text: str) -> str:
    """Lowercase, strip accents (Montréal -> montreal) and unify dashes/quotes."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower().replace("–", "-").replace("—", "-").replace("’", "'")


def _term_hits(terms: tuple[str, ...], text: str) -> list[str]:
    """Terms that appear in ``text`` as whole tokens, in config order."""
    return [t for t in terms if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text)]


def _abbr_hits(abbreviations: tuple[str, ...], text: str) -> list[str]:
    """Province codes, only in place-like positions (', QC' / '(QC' / 'CA-QC' / '| QC')."""
    return [
        a.upper()
        for a in abbreviations
        if re.search(rf"(?:,\s*|\(\s*|ca-|\|\s*){re.escape(a)}(?![a-z0-9])", text)
    ]


def _place_hits(terms: tuple[str, ...], abbreviations: tuple[str, ...], text: str) -> list[str]:
    return [t.title() for t in _term_hits(terms, text)] + _abbr_hits(abbreviations, text)


_LABEL_RE = re.compile(
    r"^[\s>*_\-•]*\**\s*"
    r"(?:(?:job|work|office|primary|posting)\s+)?"
    r"(?:locations?|work\s+arrangement|work\s+model|work\s+setup|workplace|work\s+type)"
    r"\**\s*[:|\-]\s*\**\s*(?P<value>.+)$",
    re.IGNORECASE,
)
_H1_RE = re.compile(r"^#\s+(?P<value>.+)$")
_ARRANGEMENT_LEAD_RE = re.compile(r"^[\s>*_\-•]*\**\s*(remote|hybrid|on-?site)\b", re.IGNORECASE)
_SHORT_LINE_MAX = 80


def extract_location_signals(text: str) -> list[str]:
    """Return the JD lines that explicitly state where/how the role is worked.

    Only these lines may disqualify a role: a ``Location:``-style label, the
    first H1 title, or a short line that opens with remote/hybrid/on-site.
    """
    signals: list[str] = []
    title_seen = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        label = _LABEL_RE.match(line)
        if label:
            signals.append(label.group("value").strip(" *_"))
            continue
        h1 = _H1_RE.match(line)
        if h1 and not title_seen:
            title_seen = True
            signals.append(h1.group("value").strip())
            continue
        if len(line) <= _SHORT_LINE_MAX and _ARRANGEMENT_LEAD_RE.match(line):
            signals.append(line.strip("*_ >-•"))
    return signals


def _snippet(line: str, limit: int = 100) -> str:
    line = re.sub(r"\s+", " ", line).strip(" -•*")
    return line if len(line) <= limit else line[:limit].rsplit(" ", 1)[0] + " …"


def _check_french(text: str, rules: _Rules) -> tuple[list[str], list[str]]:
    """Scan every line for French stated as a requirement (disqualifier) or as a
    softer mention — asset/preferred, or merely named (flag)."""
    disqualifiers: list[str] = []
    flags: list[str] = []
    for raw in text.splitlines():
        line = _norm(raw)
        if not _term_hits(rules.french_language, line):
            continue
        shown = _snippet(raw)
        if _term_hits(rules.french_softener, line):
            flags.append(f"French/bilingual listed as an asset: “{shown}”")
        elif _term_hits(rules.french_requirement, line):
            if rules.french_excluded:
                disqualifiers.append(f"French language required: “{shown}”")
            else:
                flags.append(f"French language required — confirm it suits you: “{shown}”")
        else:
            flags.append(f"French mentioned — confirm it is not required: “{shown}”")
    return disqualifiers, flags


def assess_location(text: str, rules: _Rules | None = None) -> LocationAssessment:
    """Check a JD's text against the job-search location rules.

    Rules, applied to the combined explicit location signals:

    1. An excluded region (Quebec) is the only place named -> disqualified.
    2. Atlantic Canada, when excluded, is the only place named, and the role is
       remote, hybrid or on-site -> disqualified.
    3. Hybrid/on-site with the home city absent, another place named, and
       remote not offered -> disqualified.
    4. French listed as a requirement anywhere in the posting, when the
       candidate excludes it -> disqualified.

    Everything ambiguous becomes a flag: nationwide-remote postings that also
    list Quebec/Atlantic provinces, hybrid with no stated city, the home
    province named without the home city, another city with no stated
    arrangement, and French merely mentioned or listed as an asset.
    """
    rules = rules or load_rules()
    home = rules.home_label
    home_province = rules.home_province_label
    disqualifiers: list[str] = []
    flags: list[str] = []

    signals = extract_location_signals(text)
    combined = _norm(" | ".join(signals))

    has_city = bool(_term_hits(rules.home_city, combined))
    has_province = bool(
        _term_hits(rules.home_province, combined) or _abbr_hits(rules.home_province_abbr, combined)
    )
    quebec = _place_hits(rules.quebec.terms, rules.quebec.abbreviations, combined)
    atlantic = _place_hits(rules.atlantic.terms, rules.atlantic.abbreviations, combined)
    other = _place_hits(rules.other_terms, rules.other_abbr, combined)
    nationwide = bool(_term_hits(rules.nationwide, combined))
    remote = bool(_term_hits(rules.remote, combined))
    hybrid = bool(_term_hits(rules.hybrid, combined))
    onsite = bool(_term_hits(rules.onsite, combined))

    if signals:
        outside_places = quebec + atlantic + other
        if (
            "quebec" in rules.excluded
            and quebec
            and not (atlantic or other or has_city or has_province or nationwide)
        ):
            disqualifiers.append(
                f"Quebec-based role ({', '.join(dict.fromkeys(quebec))}) — Quebec is excluded"
            )
        elif (
            "atlantic" in rules.excluded
            and atlantic
            and not (quebec or other or has_city or has_province or nationwide)
        ):
            if remote or hybrid or onsite:
                kind = "Remote" if remote else "Hybrid" if hybrid else "On-site"
                disqualifiers.append(
                    f"{kind} role limited to Atlantic Canada "
                    f"({', '.join(dict.fromkeys(atlantic))}) — "
                    "east of Ontario is outside the working time zones"
                )
        elif (
            (hybrid or onsite) and not remote and not nationwide and not has_city and outside_places
        ):
            kind = "Hybrid" if hybrid else "On-site"
            disqualifiers.append(
                f"{kind} role outside {home} ({', '.join(dict.fromkeys(outside_places))})"
            )

        if not disqualifiers:
            if nationwide and (quebec or atlantic):
                listed = ", ".join(dict.fromkeys(quebec + atlantic))
                flags.append(
                    f"Remote posting lists {listed} alongside a Canada-wide option — "
                    f"confirm {home_province} residents are eligible and what hours "
                    "are expected"
                )
            elif quebec and (atlantic or other or has_city or has_province):
                flags.append(
                    "Lists Quebec among several locations — confirm the role can be "
                    f"worked from {home} without French"
                )
            if (hybrid or onsite) and not remote and not (has_city or outside_places):
                if has_province:
                    flags.append(
                        f"{home_province} named without {home} — confirm the hybrid/on-site "
                        f"location is in {home}"
                    )
                else:
                    flags.append(
                        f"Hybrid/on-site with no stated city — confirm it is {home} "
                        f"(hybrid or on-site outside {home} is a Pass)"
                    )
            elif (
                not (remote or hybrid or onsite or nationwide)
                and (other or atlantic)
                and not has_city
            ):
                flags.append(
                    f"Work arrangement not stated for a location outside {home} — "
                    "confirm it is remote before applying"
                )

    french_disq, french_flags = _check_french(text, rules)
    disqualifiers.extend(french_disq)
    flags.extend(french_flags)
    return LocationAssessment(tuple(disqualifiers), tuple(flags))
