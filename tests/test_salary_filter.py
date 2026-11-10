import pytest

from jobomatic.fit.constraints import SearchConstraints
from jobomatic.fit.salary import assess_salary, find_pay, is_contract_posting, render_salary_screen

MINS = SearchConstraints(min_permanent_base_cad=85000, min_contract_hourly_cad=60)


@pytest.mark.parametrize(
    "text,low,high,period",
    [
        ("Salary range: $90,000 - $110,000 per year", 90000, 110000, "annual"),
        ("Compensation: $72k–$85k", 72000, 85000, "annual"),
        ("Pay: C$75,000 to C$95,000 annually", 75000, 95000, "annual"),
        ("Salary $90-110k", 90000, 110000, "annual"),
        ("Rate: $60-$75/hr", 60, 75, "hourly"),
        ("We pay $45 per hour", 45, 45, "hourly"),
    ],
)
def test_finds_pay(text, low, high, period) -> None:
    [pay] = find_pay(text)
    assert (pay.low, pay.high, pay.period) == (low, high, period)


@pytest.mark.parametrize(
    "text",
    [
        "Salary Range\nNot provided in posting",
        "We raised $50 million in Series B.",
        "A $5,000 signing bonus.",
        "Signing bonus of $5,000.",
        "$2,000 annual learning budget",
        "$1,200 relocation",
        "Revenue of $300 in the first week",
        "No money mentioned here at all",
    ],
)
def test_ignores_things_that_are_not_pay(text) -> None:
    assert find_pay(text) == []


def test_bonus_next_to_salary_does_not_hide_the_salary() -> None:
    [pay] = find_pay("Signing bonus of $5,000. Base $85,000/yr")
    assert pay.high == 85000


def test_no_posted_pay_gives_an_empty_assessment() -> None:
    a = assess_salary("Salary Range\nNot provided in posting", MINS)
    assert a == a.__class__() and not a.below
    assert render_salary_screen(a, configured=True) == ""


def test_permanent_below_minimum() -> None:
    a = assess_salary("Salary range: $60,000 - $75,000 per year", MINS)
    assert a.below and "$75,000" in a.below_minimum[0] and "$85,000" in a.below_minimum[0]


def test_permanent_at_or_above_minimum_is_fine() -> None:
    assert not assess_salary("Salary: $72,000 - $95,000 per year", MINS).below
    assert not assess_salary("Salary: $72,000 - $85,000 per year", MINS).below  # top end == minimum


def test_range_straddling_the_minimum_is_not_below() -> None:
    assert not assess_salary("Salary $75k-$95k", MINS).below


def test_contract_rate_below_minimum() -> None:
    a = assess_salary("Contract role. Rate: $50-$55/hr", MINS)
    assert a.below and "/hr contract" in a.below_minimum[0]
    assert "tops out at $55/hr" in a.below_minimum[0]  # the top end, not the whole range


def test_contract_rate_above_minimum() -> None:
    assert not assess_salary("6-month contract. $62-$70/hr", MINS).below


def test_hourly_on_a_non_contract_role_is_flagged_not_judged() -> None:
    a = assess_salary("Permanent role at $45 per hour", MINS)
    assert not a.below
    assert any("contract rate or an hourly wage" in f for f in a.flags)


def test_usd_is_flagged_not_judged() -> None:
    a = assess_salary("Salary: US$60,000 - US$72,000", MINS)
    assert not a.below and any("USD" in f for f in a.flags)


def test_below_only_when_every_comparable_figure_is_below() -> None:
    text = "Level 1 salary $60,000 per year. Level 2 salary $95,000 per year."
    assert not assess_salary(text, MINS).below


def test_pay_without_configured_constraints_only_flags() -> None:
    a = assess_salary("Salary: $50,000 per year", None)
    assert not a.below and a.flags and a.posted
    assert "no minimums are configured" in a.flags[0]


def test_partially_configured_constraints() -> None:
    only_hourly = SearchConstraints(min_contract_hourly_cad=60)
    assert not assess_salary("Salary: $50,000 per year", only_hourly).below


@pytest.mark.parametrize(
    "text,expected",
    [
        ("This is a contract role.", True),
        ("6 month contract", True),
        ("Job type: Contract", True),
        ("We are hiring a contractor", True),
        ("Full-time permanent. Employment contract provided on offer.", False),
    ],
)
def test_contract_detection(text, expected) -> None:
    assert is_contract_posting(text) is expected


def test_render_marks_below_and_asks_to_confirm() -> None:
    out = render_salary_screen(assess_salary("Salary: $60,000 per year", MINS), configured=True)
    assert "Salary screen" in out and "🔴" in out and "Ask the user whether to continue" in out


def test_render_confirms_when_ok() -> None:
    out = render_salary_screen(assess_salary("Salary: $95,000 per year", MINS), configured=True)
    assert "✅" in out
