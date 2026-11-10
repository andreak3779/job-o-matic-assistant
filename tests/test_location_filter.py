"""Tests for jobomatic.fit.location — the job-search location / work-arrangement rules.

Each case is a minimal JD snippet. Disqualifiers force a Pass in the fit
engine; flags are advisory only, so the "must not disqualify" cases matter as
much as the "must disqualify" ones: a false Pass blocks a real application.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobomatic.fit.location import (
    LocationAssessment,
    assess_location,
    extract_location_signals,
    load_rules,
)


def _jd(location: str, extra: str = "") -> str:
    return f"# Senior Developer\n\n**Company:** Acme\n**Location:** {location}\n\n{extra}"


# ── Disqualifiers ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "location",
    [
        "Montreal, QC",
        "Montréal, QC (Hybrid)",
        "Quebec City, Quebec",
        "Remote — Montreal, QC",
        "Laval, QC (On-site)",
        "Remote (CA-QC)",
    ],
)
def test_quebec_only_is_disqualified(location: str) -> None:
    result = assess_location(_jd(location))
    assert result.disqualified
    assert any("Quebec" in d for d in result.disqualifiers)


@pytest.mark.parametrize(
    "location",
    [
        "Toronto, ON (Hybrid)",
        "Calgary, AB — On-site",
        "Hybrid - Vancouver, BC",
        "Ottawa, Ontario (in-office 3 days)",
        "Toronto, Calgary, or Montreal (Hybrid)",
    ],
)
def test_hybrid_or_onsite_outside_springfield_is_disqualified(location: str) -> None:
    result = assess_location(_jd(location))
    assert result.disqualified, result
    assert any("outside Springfield" in d for d in result.disqualifiers)


@pytest.mark.parametrize(
    "location",
    [
        "Remote - Nova Scotia",
        "Remote (Halifax, NS)",
        "Remote — New Brunswick",
        "Moncton, NB (Hybrid)",
    ],
)
def test_atlantic_only_is_disqualified(location: str) -> None:
    result = assess_location(_jd(location))
    assert result.disqualified, result
    assert any("Atlantic Canada" in d for d in result.disqualifiers)


def test_hybrid_in_home_region_outside_home_city_is_flagged_not_disqualified() -> None:
    # "Shelbyville, MD (Hybrid)" is outside Springfield, but "Midland" alone can't be
    # told apart from Springfield — so it's a flag, never a Pass.
    result = assess_location(_jd("Midland (Hybrid)"))
    assert not result.disqualified
    assert any("Midland named without Springfield" in f for f in result.flags)


@pytest.mark.parametrize(
    "requirement",
    [
        "- Fluent in English and French",
        "- French language skills required",
        "- Bilingual (French/English) is mandatory",
        "- Must be able to communicate in French and English",
        "- Excellent written and spoken French",
    ],
)
def test_french_requirement_is_disqualified_even_when_remote(requirement: str) -> None:
    result = assess_location(_jd("Remote (Canada)", f"## Requirements\n{requirement}\n"))
    assert result.disqualified
    assert any("French language required" in d for d in result.disqualifiers)


# ── Must NOT disqualify ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "location",
    [
        "Springfield, MD",
        "Springfield, MD (Hybrid)",
        "Springfield, Midland — On-site",
        "Remote",
        "Remote (Canada)",
        "Remote - Ontario",
        "Remote — Alberta",
        "Remote (British Columbia)",
        "Springfield or Toronto (Hybrid)",
        "Toronto, ON or Remote",
    ],
)
def test_acceptable_locations_are_clean_or_flag_only(location: str) -> None:
    result = assess_location(_jd(location))
    assert not result.disqualified, result


@pytest.mark.parametrize(
    "location", ["Springfield, MD (Hybrid)", "Springfield, MD", "Remote (Canada)", "Remote"]
)
def test_clean_locations_have_no_flags(location: str) -> None:
    assert assess_location(_jd(location)) == LocationAssessment()


def test_incidental_quebec_mention_in_company_blurb_does_not_disqualify() -> None:
    """Only explicit location lines may disqualify — never a company blurb."""
    text = _jd(
        "Remote (Canada)",
        "## About us\nWe are a remote-first company with an office in Montreal and "
        "a hybrid team in Toronto.\n",
    )
    assert not assess_location(text).disqualified


def test_qc_meaning_quality_control_in_body_is_ignored() -> None:
    text = _jd("Remote (Canada)", "## Requirements\n- QC, UAT, and release sign-off\n")
    assert assess_location(text) == LocationAssessment()


def test_no_location_information_is_not_disqualified() -> None:
    assert assess_location("# Dev\n\n## Requirements\n- C#\n") == LocationAssessment()


# ── Flags (ambiguous — verify, don't decide) ─────────────────────────────────


def test_quest_style_nationwide_remote_listing_quebec_and_atlantic_is_flagged() -> None:
    result = assess_location(
        _jd("Remote in Canada (CA-NS-Remote | CA-NB-Remote | CA-QC-Remote | CA-Nationwide)")
    )
    assert not result.disqualified
    assert any("confirm Midland" in f for f in result.flags)


def test_insight_style_hybrid_cities_with_remote_canada_wide_is_flagged() -> None:
    result = assess_location(
        _jd("Toronto, Calgary, or Montreal, with remote Canada-wide opportunities")
    )
    assert not result.disqualified
    assert result.flags


def test_hybrid_with_no_city_is_flagged() -> None:
    result = assess_location(_jd("Hybrid"))
    assert not result.disqualified
    assert any("no stated city" in f for f in result.flags)


def test_city_outside_springfield_with_no_arrangement_is_flagged_not_disqualified() -> None:
    result = assess_location(_jd("Toronto, ON"))
    assert not result.disqualified
    assert any("arrangement not stated" in f for f in result.flags)


def test_french_as_asset_is_flagged_not_disqualified() -> None:
    result = assess_location(
        _jd("Remote (Canada)", "## Nice to have\n- Bilingualism (French/English) is an asset\n")
    )
    assert not result.disqualified
    assert any("asset" in f for f in result.flags)


def test_french_named_without_requirement_wording_is_flagged() -> None:
    result = assess_location(_jd("Remote (Canada)", "## Nice to have\n- French\n"))
    assert not result.disqualified
    assert any("French mentioned" in f for f in result.flags)


# ── Signal extraction ────────────────────────────────────────────────────────


def test_extract_location_signals_picks_label_title_and_leading_arrangement_lines() -> None:
    text = (
        "# Senior Dev — Montreal (Hybrid)\n\n"
        "Location: Montréal, QC\n"
        "Hybrid - 3 days in the office\n"
        "We love long prose lines that mention remote work in passing but are far too "
        "long to count as a location line.\n"
    )
    signals = extract_location_signals(text)
    assert "Senior Dev — Montreal (Hybrid)" in signals
    assert "Montréal, QC" in signals
    assert "Hybrid - 3 days in the office" in signals
    assert len(signals) == 3


# ── Rules file validation (ADR 0007: fail loud) ──────────────────────────────


def _rules_data() -> dict:
    return json.loads(
        (
            Path(__file__).parents[1] / "src" / "jobomatic" / "fit" / "location_rules.json"
        ).read_text()
    )


def test_shipped_rules_file_loads() -> None:
    rules = load_rules()
    assert "springfield" in rules.home_city  # from the (fictional) test vault preferences
    assert "montreal" in rules.quebec.terms


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda d: d["excluded_regions"]["quebec"].update(terms=[]),
            "excluded_regions.quebec.terms",
        ),
        (lambda d: d["french"].update(softener_terms=[1]), "french.softener_terms"),
        (lambda d: d.pop("nationwide_terms"), "nationwide_terms"),
    ],
)
def test_malformed_rules_fail_loudly(tmp_path: Path, mutate, match: str) -> None:
    data = _rules_data()
    mutate(data)
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_rules(path)


# ── Personal preferences come from the vault (ADR 0013) ──────────────────────


def _prefs(**overrides) -> dict:
    data = json.loads(
        (
            Path(__file__).parents[1]
            / "src"
            / "jobomatic"
            / "fit"
            / "location_preferences.example.json"
        ).read_text()
    )
    data.update(overrides)
    return data


def _load_with(tmp_path: Path, prefs: dict):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps(prefs), encoding="utf-8")
    return load_rules(preferences=path)


def test_missing_preferences_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No location preferences"):
        load_rules(preferences=tmp_path / "nope.json")


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"excluded_regions": ["mars"]}, "excluded_regions"),
        (
            {
                "home": {
                    "label": "",
                    "province_label": "X",
                    "city": ["x"],
                    "province": ["x"],
                    "province_abbreviations": ["xx"],
                }
            },
            "home.label",
        ),
        (
            {
                "home": {
                    "label": "X",
                    "province_label": "Y",
                    "city": "x",
                    "province": ["y"],
                    "province_abbreviations": ["yy"],
                }
            },
            "home.city",
        ),
    ],
)
def test_malformed_preferences_fail_loudly(tmp_path: Path, overrides: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _load_with(tmp_path, _prefs(**overrides))


def test_home_place_is_never_treated_as_somewhere_else(tmp_path: Path) -> None:
    prefs = _prefs(
        home={
            "label": "Edmonton",
            "city": ["edmonton"],
            "province_label": "Alberta",
            "province": ["alberta"],
            "province_abbreviations": ["ab"],
        }
    )
    rules = _load_with(tmp_path, prefs)
    assert "edmonton" not in rules.other_terms and "ab" not in rules.other_abbr
    assert assess_location(_jd("Edmonton, AB (Hybrid)"), rules) == LocationAssessment()


def test_regions_not_excluded_do_not_disqualify(tmp_path: Path) -> None:
    rules = _load_with(tmp_path, _prefs(excluded_regions=[]))
    assert not assess_location(_jd("Montreal, QC"), rules).disqualified
    assert assess_location(_jd("Montreal, QC"), load_rules()).disqualified


def test_french_required_only_disqualifies_when_the_candidate_excludes_it(tmp_path: Path) -> None:
    text = _jd("Remote (Canada)", "## Requirements\n- French is required\n")
    assert assess_location(text, load_rules()).disqualified
    relaxed = assess_location(text, _load_with(tmp_path, _prefs(exclude_french_required=False)))
    assert not relaxed.disqualified
    assert any("French language required" in f for f in relaxed.flags)


def test_messages_name_the_configured_home_not_a_hard_coded_city() -> None:
    result = assess_location(_jd("Toronto, ON (Hybrid)"))
    assert result.disqualified and "outside Springfield" in result.disqualifiers[0]
