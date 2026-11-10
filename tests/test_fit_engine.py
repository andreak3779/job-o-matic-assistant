"""Tests for jobomatic.fit.engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic.fit.engine import (
    FitResult,
    SkillMatch,
    _count_statuses,
    _derive_rating,
    _expand_terms,
    _load_aliases,
    humanize_evidence,
    rate_fit,
    render_fit_table,
    skill_match_terms,
)
from tests.profile_fixtures import (
    Education,
    Project,
    SkillCategory,
    WorkExperience,
    make_profile,
)


def _minimal_profile(**overrides):
    return make_profile(
        education=[Education(institution="School", credential="BS", dates="2020")], **overrides
    )


def test_rate_fit_strong_when_all_required_match_and_nice_present() -> None:
    profile = _minimal_profile(
        resolved_framing_gaps=["kubernetes", "terraform"],
        ats_keywords={"cloud": ["docker"]},
    )
    result = rate_fit(
        required=[".net", "azure", "kubernetes"],
        nice_to_have=["docker", "terraform", "python"],
        profile=profile,
    )
    assert result.rating == "Strong"
    assert result.rationale.startswith("All 3 required skills covered")
    statuses = {m.skill: m.status for m in result.required + result.nice_to_have}
    assert statuses[".net"] == "match"
    assert statuses["azure"] == "match"
    assert statuses["kubernetes"] == "match"
    assert statuses["docker"] == "course"
    assert statuses["terraform"] == "match"


def test_rate_fit_good_when_all_required_with_minor_course_signals() -> None:
    # Only azure is in the profile via technical_skills (course evidence).
    result = rate_fit(
        required=["azure"],
        nice_to_have=[],
        profile=_minimal_profile(),
    )
    assert result.rating == "Good"
    assert "All required skills covered" in result.rationale


def test_rate_fit_stretch_for_genuine_gap_and_course_signals() -> None:
    profile = _minimal_profile()
    result = rate_fit(
        required=[".net", "azure", "golang", "react"],
        nice_to_have=[],
        profile=profile,
    )
    assert result.rating == "Stretch"
    assert any(m.skill == "golang" and m.status == "gap" for m in result.required)


def test_rate_fit_pass_when_too_many_gaps() -> None:
    profile = _minimal_profile()
    result = rate_fit(
        required=["java", "golang", "rust", "terraform", "kubernetes"],
        nice_to_have=[],
        profile=profile,
    )
    assert result.rating == "Pass"
    assert "coverage 0% of 5 required skills" in result.rationale


def test_portfolio_evidence_returns_portfolio_status() -> None:
    profile = _minimal_profile()
    result = rate_fit(required=["python"], nice_to_have=[], profile=profile)
    assert result.required[0].status == "portfolio"
    assert "AI Demo" in result.required[0].evidence


def test_course_evidence_returns_course_status() -> None:
    profile = _minimal_profile(
        portfolio_projects=[], ats_keywords={"ai": ["openai", "prompt engineering"]}
    )
    result = rate_fit(required=["prompt engineering"], nice_to_have=[], profile=profile)
    assert result.required[0].status == "course"


def test_count_statuses_sums_correctly() -> None:
    matches = [
        SkillMatch("a", "match", ""),
        SkillMatch("b", "match", ""),
        SkillMatch("c", "portfolio", ""),
        SkillMatch("d", "gap", ""),
    ]
    counts = _count_statuses(matches)
    assert counts == {"match": 2, "portfolio": 1, "course": 0, "legacy": 0, "gap": 1}


def test_alias_matching_expands_co_occurring_terms() -> None:
    profile = _minimal_profile(
        portfolio_projects=[
            Project(
                name="CookingTime",
                description="Legacy WinForms modernization to Blazor WebAssembly",
                stack=[".net 10", "blazor webassembly", "xunit"],
                url="https://example.com/cookingtime",
                skills_evidence=["blazor webassembly", "legacy modernization"],
            )
        ],
        ats_keywords={"cloud": ["kubernetes", "docker"]},
        known_genuine_gaps=[],
    )
    result = rate_fit(
        required=["c# / .net core / asp.net core web api", "legacy system modernization", "docker"],
        nice_to_have=["kubernetes / container orchestration"],
        profile=profile,
    )
    statuses = {m.skill: m.status for m in result.required + result.nice_to_have}
    assert statuses["c# / .net core / asp.net core web api"] != "gap"
    assert statuses["legacy system modernization"] != "gap"
    assert statuses["docker"] != "gap"
    assert statuses["kubernetes / container orchestration"] != "gap"


def test_multi_token_skill_splitting_on_slash_and_or() -> None:
    # rate_fit keeps original phrases; splitting happens internally during matching.
    profile = _minimal_profile(
        portfolio_projects=[
            Project(
                name="API",
                description="REST API",
                stack=["aspnetcore"],
                url="https://example.com/api",
                skills_evidence=["rest api"],
            )
        ]
    )
    result = rate_fit(
        required=["angular or react frontend development"],
        nice_to_have=["sql server / t-sql query optimization"],
        profile=profile,
    )
    assert any("angular or react frontend development" == m.skill for m in result.required)
    assert any("sql server / t-sql query optimization" == m.skill for m in result.nice_to_have)


def test_years_prefix_is_normalized() -> None:
    profile = _minimal_profile(
        headline="Dev",
        technical_skills=[SkillCategory(category="Lang", skills=["c#"])],
        experience=[
            WorkExperience(
                title="Dev",
                company="Contoso",
                location="",
                dates="2023–Present",
                bullets=["c# .net core"],
            )
        ],
    )
    result = rate_fit(required=["5+ years c# / .net core"], nice_to_have=[], profile=profile)
    assert result.required[0].status == "match"


class TestDeriveRating:
    def test_strong_all_required_match_with_two_nice(self) -> None:
        matches = [SkillMatch("a", "match", "")]
        nice = [SkillMatch("b", "match", ""), SkillMatch("c", "portfolio", "")]
        rating, _ = _derive_rating(matches, nice)
        assert rating == "Strong"

    def test_good_all_required_with_two_or_fewer_course(self) -> None:
        matches = [SkillMatch("a", "match", "")]
        nice = [SkillMatch("b", "course", "")]
        rating, _ = _derive_rating(matches, nice)
        assert rating == "Good"

    def test_pass_for_two_core_gaps_even_with_high_coverage(self) -> None:
        matches = [SkillMatch(c, "match", "") for c in "abcdefgh"] + [
            SkillMatch("x", "gap", "", core=True),
            SkillMatch("y", "gap", "", core=True),
        ]
        rating, rationale = _derive_rating(matches, [])
        assert rating == "Pass"
        assert "2 core requirements" in rationale
        assert "Core gap(s): x, y" in rationale

    def test_stretch_for_one_core_gap_whatever_the_coverage(self) -> None:
        matches = [SkillMatch(c, "match", "") for c in "abcdefghi"] + [
            SkillMatch("x", "gap", "", core=True)
        ]
        rating, rationale = _derive_rating(matches, [])
        assert rating == "Stretch"
        assert "Core gap(s): x" in rationale

    def test_a_tail_gap_with_high_coverage_is_worth_a_try(self) -> None:
        matches = [SkillMatch(c, "match", "") for c in "abcdefghi"] + [SkillMatch("x", "gap", "")]
        rating, rationale = _derive_rating(matches, [])
        assert rating == "Worth a try"
        assert "coverage 90%" in rationale

    def test_one_required_skill_that_is_course_only_is_stretch_by_coverage(self) -> None:
        """Half coverage (a lone 🟡) is 50%: Stretch, where the old count rules said Good."""
        rating, rationale = _derive_rating([SkillMatch("a", "course", "")], [])
        assert rating == "Stretch"
        assert "coverage 50%" in rationale

    def test_pass_when_no_required_skills_provided(self) -> None:
        """An empty required list is a hard-coded "Pass — No required skills
        provided" — the exact rule that produced a spurious Pass rating on a
        real posting whose bullets `parse_jd` failed to capture (fixed
        separately in src/jobomatic/fit/parser.py). Locking in this branch directly
        at the fit_engine level, independent of how the required list ends
        up empty."""
        rating, rationale = _derive_rating([], [SkillMatch("a", "match", "")])
        assert rating == "Pass"
        assert rationale == "No required skills provided"

    def test_three_course_only_skills_with_no_gaps_is_worth_a_try_when_coverage_allows(
        self,
    ) -> None:
        """Was Stretch under the old count rules whatever the rest of the posting looked like."""
        matches = [SkillMatch(c, "match", "") for c in "abcd"] + [
            SkillMatch("e", "course", ""),
            SkillMatch("f", "course", ""),
            SkillMatch("g", "portfolio", ""),
        ]
        rating, rationale = _derive_rating(matches, [])
        assert rating == "Worth a try"
        assert "3 course/portfolio/legacy-only" in rationale

    def test_two_course_only_skills_with_no_gaps_can_still_be_strong(self) -> None:
        matches = [SkillMatch(c, "match", "") for c in "abcd"] + [
            SkillMatch("e", "course", ""),
            SkillMatch("f", "course", ""),
        ]
        nice = [SkillMatch("n1", "match", ""), SkillMatch("n2", "match", "")]
        assert _derive_rating(matches, nice)[0] == "Strong"
        assert _derive_rating(matches, [])[0] == "Good"

    def test_all_course_only_required_skills_are_stretch_by_coverage(self) -> None:
        matches = [SkillMatch(c, "course", "") for c in "abc"]
        assert _derive_rating(matches, [])[0] == "Stretch"  # 50%


def _rows(matches: int, course: int, gaps: int) -> list[SkillMatch]:
    """Required rows with exactly this mix; coverage is (2 * matches + course) / (2 * rows)."""
    return (
        [SkillMatch(f"m{i}", "match", "") for i in range(matches)]
        + [SkillMatch(f"c{i}", "course", "") for i in range(course)]
        + [SkillMatch(f"g{i}", "gap", "") for i in range(gaps)]
    )


class TestCoverageBoundaries:
    """The 40% and 60% cut-offs and the core-gap counts, pinned (ADR 0021)."""

    def test_just_under_40_percent_is_pass_and_exactly_40_is_stretch(self) -> None:
        assert _derive_rating(_rows(39, 1, 60), [])[0] == "Pass"  # 39.5%
        assert _derive_rating(_rows(40, 0, 60), [])[0] == "Stretch"  # 40%

    def test_just_under_60_percent_is_stretch_and_exactly_60_is_worth_a_try(self) -> None:
        rating, rationale = _derive_rating(_rows(59, 1, 40), [])  # 59.5%
        assert rating == "Stretch"
        assert "coverage 59%" in rationale  # shown rounded down, so it never reads as 60%
        assert _derive_rating(_rows(60, 0, 40), [])[0] == "Worth a try"  # 60%

    def test_a_legacy_row_counts_as_half_like_a_course_row(self) -> None:
        rows = [SkillMatch("a", "legacy", "x"), SkillMatch("b", "gap", "")]
        assert "coverage 25%" in _derive_rating(rows, [])[1]

    def test_core_gap_counts_zero_one_two(self) -> None:
        base = [SkillMatch(f"s{i}", "match", "") for i in range(12)]
        zero = base + [SkillMatch("x", "gap", "")]
        one = base + [SkillMatch("x", "gap", "", core=True)]
        two = base + [SkillMatch("x", "gap", "", core=True), SkillMatch("y", "gap", "", core=True)]
        assert [_derive_rating(r, [])[0] for r in (zero, one, two)] == [
            "Worth a try",
            "Stretch",
            "Pass",
        ]

    def test_two_versus_three_course_level_skills_without_gaps(self) -> None:
        base = [SkillMatch(f"s{i}", "match", "") for i in range(8)]
        nice = [SkillMatch("n1", "match", ""), SkillMatch("n2", "match", "")]
        two = base + [SkillMatch("c1", "course", ""), SkillMatch("c2", "course", "")]
        three = two + [SkillMatch("c3", "course", "")]
        assert _derive_rating(two, nice)[0] == "Strong"
        assert _derive_rating(three, nice)[0] == "Worth a try"

    def test_a_legacy_row_still_caps_a_fully_covered_posting_at_good(self) -> None:
        rows = [SkillMatch(f"s{i}", "match", "") for i in range(9)] + [
            SkillMatch("l", "legacy", "x")
        ]
        nice = [SkillMatch("n1", "match", ""), SkillMatch("n2", "match", "")]
        assert _derive_rating(rows, nice)[0] == "Good"

    def test_the_thresholds_are_named_constants(self) -> None:
        from jobomatic.fit.engine import PASS_BELOW_PERCENT, STRETCH_BELOW_PERCENT

        assert (PASS_BELOW_PERCENT, STRETCH_BELOW_PERCENT) == (40, 60)


class TestAliasRegistry:
    def test_registry_loads_from_shared_directory(self) -> None:
        aliases = _load_aliases()
        assert "c#" in aliases
        assert ".net" in aliases["c#"]

    def test_registry_returns_empty_for_missing_path(self) -> None:
        aliases = _load_aliases(Path("/nonexistent/aliases.json"))
        assert aliases == {}

    def test_expand_terms_uses_loaded_aliases(self) -> None:
        terms = _expand_terms("c#")
        assert ".net" in terms
        assert "dotnet" in terms

    def test_all_values_are_nonempty_lists_of_strings(self) -> None:
        aliases = _load_aliases()
        for key, values in aliases.items():
            assert isinstance(key, str) and key.strip(), (
                f"alias key must be non-empty string: {key!r}"
            )
            assert isinstance(values, list) and values, (
                f"alias values for {key!r} must be non-empty list"
            )
            for value in values:
                assert isinstance(value, str) and value.strip(), (
                    f"alias value for {key!r} must be non-empty string: {value!r}"
                )

    def test_no_key_aliases_to_itself(self) -> None:
        aliases = _load_aliases()
        for key, values in aliases.items():
            assert key not in values, f"alias key {key!r} must not alias to itself"

    def test_malformed_alias_value_raises_value_error(self, tmp_path: Path) -> None:
        """A non-list value (e.g. ``"C#": "csharp"`` where a list was
        intended — an easy hand-editing slip) must fail loudly at load time,
        not silently iterate the string character-by-character into bogus
        single-letter aliases that quietly corrupt every fit-check rating."""
        bad_path = tmp_path / "aliases.json"
        bad_path.write_text('{"aliases": {"C#": "csharp"}}', encoding="utf-8")
        with pytest.raises(ValueError, match="C#"):
            _load_aliases(bad_path)


class TestEvidenceHelpers:
    def test_skill_match_is_grounded_for_match_and_portfolio(self) -> None:
        assert SkillMatch("x", "match", "c: production").is_grounded is True
        assert SkillMatch("x", "portfolio", "p: portfolio").is_grounded is True
        assert SkillMatch("x", "course", "coursework").is_grounded is False
        assert SkillMatch("x", "gap", "no evidence").is_grounded is False

    def test_evidence_strength_order(self) -> None:
        assert SkillMatch("x", "match", "").evidence_strength == 0
        assert SkillMatch("x", "portfolio", "").evidence_strength == 1
        assert SkillMatch("x", "course", "").evidence_strength == 2
        assert SkillMatch("x", "legacy", "").evidence_strength == 3
        assert SkillMatch("x", "gap", "").evidence_strength == 4

    def test_fit_result_grounded_required_filters_by_status(self) -> None:
        result = _derive_rating(
            [
                SkillMatch("a", "match", "Contoso: production"),
                SkillMatch("b", "portfolio", "Demo: portfolio"),
                SkillMatch("c", "course", "coursework"),
                SkillMatch("d", "gap", "no evidence"),
            ],
            [],
        )[0]
        # _derive_rating only returns rating/rationale; build FitResult manually for helpers.
        from jobomatic.fit.engine import FitResult

        fit = FitResult(
            rating=result,
            required=[
                SkillMatch("a", "match", "Contoso: production"),
                SkillMatch("b", "portfolio", "Demo: portfolio"),
                SkillMatch("c", "course", "coursework"),
                SkillMatch("d", "gap", "no evidence"),
            ],
            nice_to_have=[],
            rationale="test",
        )
        assert [m.skill for m in fit.grounded_required] == ["a", "b"]
        assert [m.skill for m in fit.ungrounded_required] == ["c", "d"]
        assert fit.evidence_sources() == ["Contoso", "Demo"]

    def test_humanize_evidence_stricter_for_course_and_gap(self) -> None:
        assert (
            humanize_evidence(SkillMatch("x", "match", "Contoso: production"))
            == "hands-on experience at Contoso"
        )
        assert (
            humanize_evidence(SkillMatch("x", "portfolio", "Demo: portfolio"))
            == "portfolio work on Demo"
        )
        assert humanize_evidence(SkillMatch("x", "course", "coursework")) == "recent coursework"
        assert (
            humanize_evidence(SkillMatch("x", "gap", "no evidence"))
            == "not yet demonstrated in production"
        )
        assert humanize_evidence(SkillMatch("x", "gap", ""), audience="debug") == "no evidence"


class TestRenderFitTable:
    """Matches job_description_fit/SKILL.md's Step 4 output template."""

    def test_headings_and_status_cells_match_skill_md_template(self) -> None:
        result = FitResult(
            rating="Good",
            required=[SkillMatch("Azure", "match", "Contoso: production")],
            nice_to_have=[SkillMatch("Docker", "course", "coursework or self-study")],
            rationale="test rationale",
        )
        table = render_fit_table(result)
        assert "**Nice-to-Haves**" in table
        assert "Nice-to-Have Skills" not in table
        # Bare emoji in the status cell, not "✅ match" / "🟡 course".
        assert "| Azure | ✅ | Contoso, production |" in table
        assert "| Docker | 🟡 | coursework or self-study |" in table

    def test_evidence_display_uses_comma_not_colon_separator(self) -> None:
        # Matches the SKILL.md example: "Acme Software, production".
        assert (
            render_fit_table(
                FitResult(
                    rating="Strong",
                    required=[SkillMatch("C#", "match", "Acme Software: production")],
                    nice_to_have=[],
                    rationale="",
                )
            ).find("Acme Software, production")
            != -1
        )


def test_match_terms_requires_whole_token():
    from jobomatic.fit.engine import _match_terms

    assert not _match_terms(["rag"], "designed cloud storage layer")
    assert not _match_terms(["ci"], "acme group")
    assert not _match_terms(["llm"], "corner hardware store")
    assert _match_terms(["azure app service"], "deployed to azure app services")
    assert _match_terms([".net core"], "built on .net core apis")
    assert _match_terms(["c#"], "wrote c# and sql")


class TestLegacyTier:
    """The legacy_experience tier is a last-resort tier (🕰️), capped below Strong."""

    _LEGACY = [
        WorkExperience(
            title="Programmer",
            company="OldCo",
            location="",
            dates="2003 – 2005",
            bullets=["Built PowerBuilder apps on Sybase"],
        )
    ]

    def test_fires_when_nothing_else_matches(self) -> None:
        profile = _minimal_profile(legacy_experience=self._LEGACY)
        result = rate_fit(required=["powerbuilder"], nice_to_have=[], profile=profile)
        match = result.required[0]
        assert match.status == "legacy"
        assert "OldCo (2003 – 2005)" in match.evidence
        assert not match.is_grounded

    def test_current_evidence_wins_over_legacy(self) -> None:
        legacy = [
            WorkExperience(
                title="Dev", company="OldCo", location="", dates="2005", bullets=["Built .NET APIs"]
            )
        ]
        profile = _minimal_profile(legacy_experience=legacy)
        result = rate_fit(required=[".net"], nice_to_have=[], profile=profile)
        assert result.required[0].status == "match"

    def test_course_tier_still_beats_legacy(self) -> None:
        profile = _minimal_profile(
            legacy_experience=self._LEGACY, ats_keywords={"legacy": ["sybase"]}
        )
        result = rate_fit(required=["sybase"], nice_to_have=[], profile=profile)
        assert result.required[0].status == "course"

    def test_legacy_entries_without_company_are_ignored(self) -> None:
        gap_entry = [
            WorkExperience(title="Career Gap", company="", dates="2001", bullets=["PowerBuilder"])
        ]
        profile = _minimal_profile(legacy_experience=gap_entry)
        result = rate_fit(required=["powerbuilder"], nice_to_have=[], profile=profile)
        assert result.required[0].status == "gap"

    def test_legacy_caps_rating_at_good(self) -> None:
        profile = _minimal_profile(legacy_experience=self._LEGACY)
        result = rate_fit(
            required=[".net", "azure", "powerbuilder"],
            nice_to_have=["python", "openai"],
            profile=profile,
        )
        assert result.rating == "Good"
        assert "capped below Strong" in result.rationale

    def test_three_combined_legacy_and_course_signals_is_stretch(self) -> None:
        profile = _minimal_profile(
            legacy_experience=self._LEGACY, ats_keywords={"x": ["docker", "terraform"]}
        )
        result = rate_fit(
            required=["powerbuilder", "docker", "terraform"], nice_to_have=[], profile=profile
        )
        assert result.rating == "Stretch"  # 50% coverage: a legacy and two course rows
        assert "coverage 50%" in result.rationale

    def test_real_gap_still_dominates_legacy(self) -> None:
        profile = _minimal_profile(legacy_experience=self._LEGACY)
        result = rate_fit(required=["powerbuilder", "cobol"], nice_to_have=[], profile=profile)
        assert result.rating == "Pass"  # 25% coverage: a legacy row is half, a gap is nothing
        assert "coverage 25%" in result.rationale

    def test_empty_legacy_leaves_behavior_unchanged(self) -> None:
        result = rate_fit(required=["powerbuilder"], nice_to_have=[], profile=_minimal_profile())
        assert result.required[0].status == "gap"

    def test_render_fit_table_uses_clock_emoji(self) -> None:
        profile = _minimal_profile(legacy_experience=self._LEGACY)
        table = render_fit_table(rate_fit(["powerbuilder"], [], profile))
        assert "| powerbuilder | 🕰️ |" in table

    def test_humanize_evidence_never_echoes_legacy_employer(self) -> None:
        match = SkillMatch("powerbuilder", "legacy", "OldCo (2003 – 2005): legacy experience")
        text = humanize_evidence(match)
        assert "OldCo" not in text
        assert "2003" not in text


# ── Location / work-arrangement override ─────────────────────────────────────


def test_rate_fit_without_location_is_unchanged_skills_only_rating() -> None:
    result = rate_fit(required=["azure"], nice_to_have=[], profile=_minimal_profile())
    assert result.rating == "Good"
    assert result.skill_rating == "Good"
    assert result.location_disqualifiers == ()
    assert result.location_flags == ()
    assert not result.location_disqualified


def test_location_disqualifier_forces_pass_but_keeps_skill_matches() -> None:
    from jobomatic.fit.location import LocationAssessment

    profile = _minimal_profile(
        resolved_framing_gaps=["kubernetes", "terraform"],
        ats_keywords={"cloud": ["docker"]},
    )
    kwargs = dict(
        required=[".net", "azure", "kubernetes"],
        nice_to_have=["docker", "terraform", "python"],
        profile=profile,
    )
    assert rate_fit(**kwargs).rating == "Strong"

    location = LocationAssessment(
        disqualifiers=("Quebec-based role (Montreal, QC) — Quebec is excluded",)
    )
    result = rate_fit(**kwargs, location=location)

    assert result.rating == "Pass"
    assert result.skill_rating == "Strong"
    assert result.skills_only_rating == "Strong"
    assert result.location_disqualified
    assert result.rationale.startswith("Outside job-search constraints")
    assert "Quebec-based role" in result.rationale
    assert "Skills alone would rate Strong" in result.rationale
    # Per-skill matches are still reported so gap reports can show them.
    assert {m.skill: m.status for m in result.required}[".net"] == "match"


def test_location_flags_are_carried_without_changing_rating() -> None:
    from jobomatic.fit.location import LocationAssessment

    location = LocationAssessment(flags=("Hybrid with no stated city — confirm it is Springfield",))
    result = rate_fit(
        required=["azure"], nice_to_have=[], profile=_minimal_profile(), location=location
    )
    assert result.rating == "Good"
    assert result.location_flags == location.flags
    assert not result.location_disqualified


def test_render_fit_table_lists_location_disqualifiers_and_flags() -> None:
    from jobomatic.fit.location import LocationAssessment

    location = LocationAssessment(
        disqualifiers=("Hybrid role outside Springfield (Toronto)",),
        flags=("French/bilingual listed as an asset: “Bilingual is an asset”",),
    )
    result = rate_fit(
        required=["azure"], nice_to_have=[], profile=_minimal_profile(), location=location
    )
    table = render_fit_table(result)
    assert "**Fit Rating: Pass**" in table
    assert "**Location & work arrangement**" in table
    assert "- 🚫 Hybrid role outside Springfield (Toronto)" in table
    assert "- ⚠️ French/bilingual listed as an asset" in table


def test_render_fit_table_omits_location_section_when_nothing_to_report() -> None:
    result = rate_fit(required=["azure"], nice_to_have=[], profile=_minimal_profile())
    assert "Location & work arrangement" not in render_fit_table(result)


def test_skills_only_rating_falls_back_to_rating_for_hand_built_results() -> None:
    result = FitResult(rating="Stretch", required=[], nice_to_have=[], rationale="")
    assert result.skills_only_rating == "Stretch"


# ── rate_parsed_jd / unscored lines ──────────────────────────────────────────


def test_rate_parsed_jd_applies_location_and_carries_unscored_lines() -> None:
    from jobomatic.fit.engine import rate_parsed_jd
    from jobomatic.fit.parser import parse_jd

    parsed = parse_jd(
        "# Dev\n\n**Location:** Montreal, QC (Hybrid)\n\n## Requirements\n"
        "- Azure\n- A line naming no technology whatsoever in any recognized form\n"
    )
    result = rate_parsed_jd(parsed, _minimal_profile())
    assert result.rating == "Pass"
    assert result.location_disqualified
    assert result.unscored_required == (
        "A line naming no technology whatsoever in any recognized form",
    )


def test_unscored_lines_never_change_the_rating() -> None:
    base = rate_fit(required=["azure"], nice_to_have=[], profile=_minimal_profile())
    with_unscored = rate_fit(
        required=["azure"],
        nice_to_have=[],
        profile=_minimal_profile(),
        unscored_required=("Computer science degree",),
    )
    assert with_unscored.rating == base.rating
    assert with_unscored.rationale == base.rationale
    assert with_unscored.unscored_required == ("Computer science degree",)


def test_render_fit_table_lists_unscored_lines_only_when_present() -> None:
    plain = rate_fit(required=["azure"], nice_to_have=[], profile=_minimal_profile())
    assert "not scored" not in render_fit_table(plain)

    result = rate_fit(
        required=["azure"],
        nice_to_have=[],
        profile=_minimal_profile(),
        unscored_required=("Computer science degree or equivalent",),
    )
    table = render_fit_table(result)
    assert "**Required lines not scored**" in table
    assert "- Computer science degree or equivalent" in table


@pytest.mark.parametrize(
    "jd_skill,profile_skill",
    [("secure development", "secure coding"), ("distributed systems", "microservices")],
)
def test_registered_synonyms_resolve_to_profile_evidence(jd_skill: str, profile_skill: str) -> None:
    profile = _minimal_profile(ats_keywords={"x": [profile_skill]})
    result = rate_fit(required=[jd_skill], nice_to_have=[], profile=profile)
    assert result.required[0].status == "course"


# ── Prose requirements ──────────────────────────────────────────────────────
# Sentence-style requirements ("Solid backend programming experience in C#/.NET,
# or a comparable language such as Java") used to be chopped into fragments, each
# matched on its own, so a well-evidenced requirement showed up as many gaps.


def test_prose_candidates_extract_short_skill_phrases() -> None:
    from jobomatic.fit.engine import _prose_candidates

    got = _prose_candidates(
        "Solid backend programming experience in C#/.NET, or a comparable language such as Java"
    )
    assert "c#" in got
    assert ".net" in got  # leading dot must survive
    assert "java" in got
    assert not any(c in {"or", "equivalent", "experience"} for c in got)


def test_prose_candidates_drop_filler_only_fragments() -> None:
    from jobomatic.fit.engine import _prose_candidates

    assert "equivalent" not in _prose_candidates("BS in Computer Science (or equivalent)")


def test_prose_requirement_is_one_row_covered_by_best_phrase() -> None:
    profile = _minimal_profile()
    result = rate_fit(
        ["Solid backend programming experience in .NET, or a comparable language such as Java"],
        [],
        profile,
    )
    assert len(result.required) == 1
    assert result.required[0].status == "match"
    assert ".net" in result.required[0].evidence  # the phrase that carried it is shown


def test_prose_requirement_with_no_matching_phrase_is_still_a_gap() -> None:
    profile = _minimal_profile()
    result = rate_fit(
        ["Experience operating large-scale distributed ledger infrastructure in production"],
        [],
        profile,
    )
    assert result.required[0].status == "gap"


def test_legacy_evidence_ranks_between_course_and_gap() -> None:
    from jobomatic.fit.engine import SkillMatch

    def strength(status: str) -> int:
        return SkillMatch(skill="x", status=status, evidence="").evidence_strength  # type: ignore[arg-type]

    assert strength("course") < strength("legacy") < strength("gap")


def test_the_long_blazor_phrase_matches_blazor_evidence_through_an_alias() -> None:
    profile = _minimal_profile(
        portfolio_projects=[
            Project(
                name="CookingTime",
                description="Legacy WinForms modernization to Blazor WebAssembly",
                stack=["blazor webassembly"],
                url="https://example.com/cookingtime",
            )
        ]
    )
    result = rate_fit(required=["asp.net core blazor", "blazor"], nice_to_have=[], profile=profile)
    assert [m.status for m in result.required] == ["portfolio", "portfolio"]


def test_asp_net_mvc_and_asp_net_core_mvc_find_each_other_in_the_profile() -> None:
    profile = _minimal_profile(
        portfolio_projects=[
            Project(
                name="MoviesApp",
                description="Movie catalogue",
                stack=["asp.net core mvc"],
                url="https://example.com/movies",
            )
        ]
    )
    result = rate_fit(required=["asp.net mvc", "mvc"], nice_to_have=[], profile=profile)
    assert [m.status for m in result.required] == ["portfolio", "portfolio"]


def test_a_plural_requirement_finds_the_singular_in_the_profile() -> None:
    profile = _minimal_profile(ats_keywords={"web": ["html", "css"]})
    # the parser now hands the engine "html" for a posting's "HTMLS"; it must still be found
    result = rate_fit(required=["html"], nice_to_have=[], profile=profile)
    assert result.required[0].status != "gap"


def test_terms_to_confirm_are_carried_and_never_change_the_rating() -> None:
    base = rate_fit(required=["azure"], nice_to_have=[], profile=_minimal_profile())
    with_terms = rate_fit(
        required=["azure"],
        nice_to_have=[],
        profile=_minimal_profile(),
        terms_to_confirm=(("solid", "Solid understanding of CI/CD practices"),),
    )
    assert with_terms.rating == base.rating
    assert with_terms.rationale == base.rationale
    assert with_terms.terms_to_confirm == (("solid", "Solid understanding of CI/CD practices"),)


def test_render_fit_table_lists_terms_to_confirm() -> None:
    from jobomatic.fit.engine import render_fit_table

    result = rate_fit(
        required=["azure"],
        nice_to_have=[],
        profile=_minimal_profile(),
        terms_to_confirm=(("solid", "Solid understanding of CI/CD practices"),),
    )
    table = render_fit_table(result)
    assert "**Terms to confirm**" in table
    assert '- "solid" in: Solid understanding of CI/CD practices' in table
    assert "Terms to confirm" not in render_fit_table(
        rate_fit(required=["azure"], nice_to_have=[], profile=_minimal_profile())
    )


def test_possible_typos_are_carried_listed_and_never_change_the_rating() -> None:
    from jobomatic.fit.engine import render_fit_table

    base = rate_fit(required=["azure"], nice_to_have=[], profile=_minimal_profile())
    flagged = rate_fit(
        required=["azure"],
        nice_to_have=[],
        profile=_minimal_profile(),
        possible_typos=(("Typscript", "typescript", "Experience with Typscript"),),
    )
    assert flagged.rating == base.rating and flagged.rationale == base.rationale
    table = render_fit_table(flagged)
    assert "**Possible typos**" in table
    assert '- "Typscript" may be "typescript" in: Experience with Typscript' in table
    assert "Possible typos" not in render_fit_table(base)


# ── low-confidence result (ADR 0021, step C1) ────────────────────────────────


def _rated(required: list[str]):
    from jobomatic.bootstrap import load_profile
    from jobomatic.fit.engine import rate_fit

    return rate_fit(required, [], load_profile())


def test_more_than_half_red_is_low_confidence_and_exactly_half_is_not() -> None:
    # The demo candidate has no evidence for these made-up skills and does have C# and SQL.
    known = ["C#", "SQL"]
    unknown = ["zzqq1", "zzqq2"]
    assert not _rated(known + unknown).low_confidence  # 2 of 4 = 50%: not "more than half"
    assert _rated(known[:1] + unknown + ["zzqq3"]).low_confidence  # 3 of 4
    assert not _rated(known).low_confidence


def test_a_three_skill_posting_with_all_skills_met_is_not_low_confidence() -> None:
    assert not _rated(["C#", "SQL"]).low_confidence


def test_low_confidence_never_changes_the_rating() -> None:
    result = _rated(["zzqq1", "zzqq2", "zzqq3"])
    assert result.low_confidence
    assert result.rating == "Pass"  # the count rules decided that, not the warning


def test_the_fit_table_shows_the_low_confidence_notice_only_when_it_applies() -> None:
    from jobomatic.fit.engine import LOW_CONFIDENCE_MESSAGE, render_fit_table

    assert LOW_CONFIDENCE_MESSAGE in render_fit_table(_rated(["zzqq1", "zzqq2", "C#"]))
    assert LOW_CONFIDENCE_MESSAGE not in render_fit_table(_rated(["C#", "SQL"]))


class TestLifecycleAliases:
    """ "Product development lifecycle", "software development life cycle" and SDLC are one skill."""

    def test_every_wording_searches_for_every_other(self) -> None:
        wordings = [
            "sdlc",
            "software development lifecycle",
            "software development life cycle",
            "product development lifecycle",
            "product development life cycle",
            "pdlc",
        ]
        for wording in wordings:
            terms = skill_match_terms(wording)
            assert all(other in terms for other in wordings), wording


def test_render_fit_table_lists_names_to_check_and_the_title_level() -> None:
    from jobomatic.fit.engine import render_fit_table
    from jobomatic.fit.soft_requirements import SoftRequirement

    result = rate_fit(
        required=["azure"],
        nice_to_have=[],
        profile=_minimal_profile(),
        unknown_names=(("Frobnicator", "tools such as Frobnicator"),),
        soft_requirements=(
            SoftRequirement("level", "Software Lead", "senior title — check this yourself"),
        ),
    )
    table = render_fit_table(result)
    assert "**Names to check**" in table
    assert '- "Frobnicator" in: tools such as Frobnicator' in table
    assert "- Level — senior title — check this yourself: Software Lead" in table


class TestUmbrellaSkills:
    """ADR 0022: "AI" is met by evidence in its parts, never by the bare word."""

    def test_the_bare_word_alone_is_not_evidence(self) -> None:
        profile = _minimal_profile(ats_keywords={"general": ["ai"]})
        (row,) = rate_fit(required=["AI"], nice_to_have=[], profile=profile).required
        assert row.status == "gap"

    def test_evidence_in_a_part_meets_the_umbrella_and_names_the_part(self) -> None:
        profile = _minimal_profile(ats_keywords={"ai": ["vector databases"]})
        (row,) = rate_fit(required=["AI"], nice_to_have=[], profile=profile).required
        assert row.status == "course"
        assert "[via vector database" in row.evidence

    def test_the_best_of_several_parts_wins_with_no_cap(self) -> None:
        profile = _minimal_profile(
            ats_keywords={"ai": ["vector databases", "llm"]},
            resolved_framing_gaps=["claude code"],
        )
        (row,) = rate_fit(required=["AI"], nice_to_have=[], profile=profile).required
        assert row.status == "match"  # the resolved framing gap, not capped one tier down
        assert "[via claude code]" in row.evidence

    def test_generative_ai_uses_the_same_parts(self) -> None:
        profile = _minimal_profile(ats_keywords={"ai": ["embeddings"]})
        (row,) = rate_fit(required=["Generative AI"], nice_to_have=[], profile=profile).required
        assert row.status == "course" and "[via embeddings]" in row.evidence

    def test_a_requirement_that_is_not_an_umbrella_is_scored_as_before(self) -> None:
        profile = _minimal_profile(ats_keywords={"cloud": ["docker"]})
        (row,) = rate_fit(required=["docker"], nice_to_have=[], profile=profile).required
        assert row.status == "course" and "via" not in row.evidence
