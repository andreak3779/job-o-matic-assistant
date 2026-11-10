from jobomatic.fit.constraints import SearchConstraints
from jobomatic.privacy.private_values import find_leaks

# Deliberately not any real configured value: this file is tracked.
MINS = SearchConstraints(min_permanent_base_cad=85000, min_contract_hourly_cad=60)


def test_finds_a_base_minimum_in_each_common_spelling() -> None:
    files = {
        "a.md": "Base is $85,000 for permanent roles.",
        "b.md": "minimum 85000",
        "c.md": "around 85k base",
    }
    leaks = find_leaks(MINS, files)
    assert {leak.split(":")[0] for leak in leaks} == {"a.md", "b.md", "c.md"}
    assert all("permanent base minimum" in leak for leak in leaks)


def test_finds_the_hourly_minimum() -> None:
    leaks = find_leaks(MINS, {"a.md": "ok\ncontract at $60/hr\n", "b.md": "$60 per hour"})
    assert "a.md:2 (contract hourly minimum)" in leaks and any(
        item.startswith("b.md") for item in leaks
    )


def test_reports_path_and_line_but_never_the_value() -> None:
    [leak] = find_leaks(MINS, {"skills/x.md": "line one\nBase: $85,000"})
    assert leak == "skills/x.md:2 (permanent base minimum)"
    assert "85" not in leak


def test_does_not_flag_look_alike_numbers() -> None:
    files = {
        "a.md": "850,000 users, 185000 rows, $860/hr is absurd, 60% coverage, 60 courses",
        "b.md": "version 1.85000",
    }
    assert find_leaks(MINS, files) == []


def test_unset_minimums_flag_nothing() -> None:
    assert find_leaks(SearchConstraints(), {"a.md": "$85,000 and $60/hr"}) == []
