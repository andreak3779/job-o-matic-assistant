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
        # a currency code in place of the "$" (Clover Health posting)
        ("base salary range for this role is: CAD 134,000 - 175,000.", 134000, 175000, "annual"),
        ("Salary: CAD 120,000", 120000, 120000, "annual"),
        # the code after each number (Samsara, Quantum World postings)
        ("base pay is below.: $126,225 CAD - $184,800 CAD", 126225, 184800, "annual"),
        ("100K CAD/yr - 115K CAD/yr", 100000, 115000, "annual"),
        ("Rate: $40/hr - $60/hr", 40, 60, "hourly"),
        # a range written "between … and …" (eluta.ca posting)
        ("hourly rates starting between $40 and $60 CAD.", 40, 60, "hourly"),
        ("Salary between $76,000 and $94,000 per year", 76000, 94000, "annual"),
        ("Rate between $40/hr and $60/hr", 40, 60, "hourly"),
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


def test_a_currency_code_without_a_dollar_sign_is_read_as_that_currency() -> None:
    [cad] = find_pay("Base salary range: CAD 134,000 - 175,000")
    [usd] = find_pay("Base salary range: USD 134,000 - 175,000")
    assert (cad.currency, usd.currency) == ("CAD", "USD")


@pytest.mark.parametrize(
    "text",
    [
        "CAD 5 million in funding",  # not pay
        "Offices in CAD 134,000 square feet",  # no pay word, period unstated
        "We pay a CAD 5,000 signing bonus.",
    ],
)
def test_a_currency_code_alone_does_not_make_a_number_pay(text) -> None:
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


@pytest.mark.parametrize(
    "text", ["about 100K employees", "raised $50M in 2025", "5+ years, 100k users"]
)
def test_a_k_figure_without_a_currency_code_or_dollar_sign_is_not_pay(text) -> None:
    assert find_pay(text) == []


@pytest.mark.parametrize(
    "text,low,high,period",
    [
        ("60 CAD/hr - 65 CAD/hr", 60, 65, "hourly"),
        ("Pay 80 CAD per hour", 80, 80, "hourly"),
        ("100K CAD/yr - 115K CAD/yr", 100000, 115000, "annual"),
    ],
)
def test_pay_with_a_code_and_no_dollar_sign(text, low, high, period) -> None:
    [pay] = find_pay(text)
    assert (pay.low, pay.high, pay.period) == (low, high, period)


@pytest.mark.parametrize(
    "text",
    ["Job Type: Fixed term contract", "Fixed-term position", "a fixed term role"],
)
def test_a_fixed_term_posting_counts_as_a_contract(text) -> None:
    assert is_contract_posting(text) is True


def test_the_same_figure_written_twice_warns_once() -> None:
    assessment = assess_salary("Rates: CA$40.00 per hour\nPay: $40.00 per hour", MINS)
    assert len(assessment.flags) == 1
    assert len(assessment.posted) == 1


def test_an_hourly_and_an_annual_figure_for_one_salary_do_not_warn() -> None:
    text = "Salary range: $41.26-$57.11 Hourly, $79,060.02-$109,437.90 Annually."
    assessment = assess_salary(text, MINS)
    assert not assessment.flags
    assert not assessment.below


def test_a_contract_at_a_low_hourly_rate_is_below_the_minimum() -> None:
    text = "Structure: Contract, 1 opening\nRates: $40.00 per hour"
    assert assess_salary(text, MINS).below


def test_between_a_figure_and_a_plain_number_is_not_a_range() -> None:
    [pay] = find_pay("Salary between $76,000 and 10 days of vacation")
    assert (pay.low, pay.high) == (76000, 76000)
