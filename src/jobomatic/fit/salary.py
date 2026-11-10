"""Deterministic posted-pay screen for job descriptions.

Finds the pay a posting states and compares it with the walk-away minimums in
``jobomatic.fit.constraints``. Like ``src/jobomatic/fit/location.py`` it is plain regex, no
LLM, and conservative — but unlike location it never forces a ``Pass``: a role
paying below the minimum might still be worth a conversation, so the result is a
*flag the user must confirm past* (ADR 0011), not a rating override.

Conservative means a false "below minimum" (which blocks document generation) is
treated as worse than a missed one:

* an amount only counts if it carries a ``$`` and is not clearly something else
  (bonus, budget, funding, "$10M");
* a posting is "below" only if *every* comparable pay figure in it is below;
* USD, unclear hourly-versus-contract, and unparseable pay become advisory
  flags, never a "below minimum" verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jobomatic.fit.constraints import SearchConstraints

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_PAY_RE = re.compile(
    r"(?<![A-Za-z])(?:(?P<cur1>USD|CAD|US|CA|C|A)\s?)?\$\s?(?P<lo>" + _NUM + r")\s?(?P<lok>[kK])?"
    r"(?:\s*(?:-|–|—|to)\s*(?:(?P<cur2>USD|CAD|US|CA|C|A)\s?)?\$?\s?(?P<hi>"
    + _NUM
    + r")\s?(?P<hik>[kK])?)?"
    r"(?![\w])"
)
_HOURLY_RE = re.compile(r"/\s?h(?:ou)?r|per\s+hour|an\s+hour|hourly|/\s?hour", re.IGNORECASE)
_ANNUAL_RE = re.compile(
    r"/\s?y(?:ea)?r|per\s+(?:year|annum)|a\s+year|annual|yearly|p\.a\.|/\s?annum", re.IGNORECASE
)
_TRAILING_CURRENCY_RE = re.compile(r"^\s*(USD|CAD)\b")
# Something that follows the amount and shows it is not pay: "$5,000 signing bonus",
# "$50 million", "$2M".
_AFTER_SKIP_RE = re.compile(
    r"^\s*(?:(?:annual|yearly)\s+)?(?:signing|sign-on|relocation|bonus|stipend|allowance|"
    r"learning|wellness|budget|million|billion|m\b|mm\b|bn\b|b\b)",
    re.IGNORECASE,
)
# Something just before the amount that shows it is not pay: "annual budget of $2,000",
# "raised $50".
_BEFORE_SKIP_RE = re.compile(
    r"(?:bonus|equity|stipend|allowance|budget|funding|raised|revenue|valuation|"
    r"reimbursement|credit|referral)\W+(?:\w+\W+){0,2}$",
    re.IGNORECASE,
)
_PAY_WORD_RE = re.compile(
    r"(?:salary|pay|compensation|rate|base|wage|range|remuneration)\W", re.IGNORECASE
)
_CONTRACT_RE = re.compile(
    r"\b(?:contract (?:role|position|opportunity|basis|assignment|term|to hire)|"
    r"contract-to-hire|contractor|freelance|c2c|corp[- ]to[- ]corp|\d+[- ]months? contract|"
    r"(?:employment|job)?\s*type\W+contract)\b",
    re.IGNORECASE,
)
_PLAUSIBLE_HOURLY_MAX = 500
_PLAUSIBLE_ANNUAL_MIN = 20_000


@dataclass(frozen=True)
class Pay:
    """One pay figure found in a posting."""

    low: float
    high: float
    period: str  # "annual" or "hourly"
    currency: str  # "CAD" (assumed when unstated) or "USD"
    inferred_period: bool
    shown: str

    @property
    def top_label(self) -> str:
        return f"${self.high:,.0f}{'/hr' if self.period == 'hourly' else '/year'}"

    @property
    def label(self) -> str:
        unit = "/hr" if self.period == "hourly" else "/year"
        if self.low == self.high:
            return f"${self.high:,.0f}{unit}"
        return f"${self.low:,.0f}–${self.high:,.0f}{unit}"


@dataclass(frozen=True)
class SalaryAssessment:
    """Outcome of comparing a posting's pay with the walk-away minimums."""

    posted: tuple[str, ...] = ()
    below_minimum: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()

    @property
    def below(self) -> bool:
        return bool(self.below_minimum)


def _scaled(num: str, k: str | None) -> float:
    value = float(num.replace(",", ""))
    return value * 1000 if k else value


def find_pay(text: str) -> list[Pay]:
    """Every plausible pay figure in ``text`` (empty when the posting states none)."""
    found: list[tuple[Pay, bool]] = []
    for match in _PAY_RE.finditer(text):
        before = text[max(0, match.start() - 30) : match.start()]
        after = text[match.end() : match.end() + 25]
        if _AFTER_SKIP_RE.match(after) or _BEFORE_SKIP_RE.search(before):
            continue
        low = _scaled(match["lo"], match["lok"])
        # "$90-110k": a lone k on the upper bound applies to both ends.
        high_k = match["hik"] or (match["lok"] if match["hi"] is None else None)
        high = _scaled(match["hi"], high_k) if match["hi"] else low
        if match["hi"] and match["hik"] and not match["lok"] and low < 1000 <= high:
            low *= 1000
        low, high = sorted((low, high))

        explicit_hourly = bool(_HOURLY_RE.search(after))
        explicit_annual = bool(_ANNUAL_RE.search(after)) or bool(match["lok"] or match["hik"])
        if explicit_hourly and not explicit_annual:
            period, inferred = "hourly", False
        elif explicit_annual and not explicit_hourly:
            period, inferred = "annual", False
        elif high < _PLAUSIBLE_HOURLY_MAX:
            period, inferred = "hourly", True
        else:
            period, inferred = "annual", True
        # Reject figures that cannot be a developer's pay in that period — a stated
        # "$2,000 a year" is a budget or a typo, not a salary to screen against.
        if period == "hourly" and high >= _PLAUSIBLE_HOURLY_MAX:
            continue
        if period == "annual" and high < _PLAUSIBLE_ANNUAL_MIN:
            continue

        code = (match["cur1"] or match["cur2"] or "").upper()
        trailing = _TRAILING_CURRENCY_RE.match(text[match.end() : match.end() + 8])
        if trailing:
            code = trailing.group(1)
        currency = "USD" if code in ("USD", "US") else "CAD"

        pay = Pay(low, high, period, currency, inferred, match.group(0).strip())
        stated_as_pay = not inferred or bool(
            _PAY_WORD_RE.search(text[max(0, match.start() - 60) : match.start()])
        )
        found.append((pay, stated_as_pay))

    # Only figures clearly stated as pay count: an explicit period, or a pay word
    # just before them. A bare "$300" somewhere in a posting is far more likely noise
    # than a salary, and a wrong "below minimum" verdict blocks real work.
    return [p for p, ok in found if ok]


def is_contract_posting(text: str) -> bool:
    return bool(_CONTRACT_RE.search(text))


def assess_salary(text: str, constraints: SearchConstraints | None) -> SalaryAssessment:
    """Compare the pay stated in ``text`` with ``constraints``.

    No posted pay -> an empty assessment (the screen has nothing to say). Pay posted
    but no constraints configured -> an advisory flag only.
    """
    pays = find_pay(text)
    if not pays:
        return SalaryAssessment()

    posted = tuple(dict.fromkeys(p.label + (" USD" if p.currency == "USD" else "") for p in pays))
    if constraints is None:
        return SalaryAssessment(
            posted=posted,
            flags=("Pay is posted but no minimums are configured — compare it by hand.",),
        )

    contract = is_contract_posting(text)
    flags: list[str] = []
    comparable: list[tuple[Pay, float, str]] = []  # (pay, minimum, minimum label)
    for pay in pays:
        if pay.currency == "USD":
            flags.append(f"{pay.label} is in USD — compare it with your CAD minimum by hand.")
        elif pay.period == "annual":
            if constraints.min_permanent_base_cad is not None:
                comparable.append(
                    (
                        pay,
                        constraints.min_permanent_base_cad,
                        f"${constraints.min_permanent_base_cad:,.0f} base",
                    )
                )
        elif contract:
            if constraints.min_contract_hourly_cad is not None:
                comparable.append(
                    (
                        pay,
                        constraints.min_contract_hourly_cad,
                        f"${constraints.min_contract_hourly_cad:,.0f}/hr contract",
                    )
                )
        else:
            flags.append(
                f"{pay.label} is an hourly figure on a role not described as a contract — "
                "confirm whether it is a contract rate or an hourly wage."
            )

    below: list[str] = []
    if comparable and all(pay.high < minimum for pay, minimum, _ in comparable):
        pay, _, label = max(comparable, key=lambda c: c[0].high)
        below.append(f"Posted pay tops out at {pay.top_label}, below your {label} minimum.")
    return SalaryAssessment(posted=posted, below_minimum=tuple(below), flags=tuple(flags))


def render_salary_screen(assessment: SalaryAssessment, configured: bool) -> str:
    """Markdown block for fit-check output; empty when there is nothing to report."""
    if not assessment.posted:
        return ""
    lines = ["\n**Salary screen**", f"- Posted: {', '.join(assessment.posted)}"]
    if assessment.below:
        lines.extend(f"- 🔴 {reason}" for reason in assessment.below_minimum)
        lines.append("- Ask the user whether to continue before generating documents.")
    elif configured and not assessment.flags:
        lines.append("- ✅ At or above your minimum.")
    lines.extend(f"- ⚠️ {flag}" for flag in assessment.flags)
    return "\n".join(lines) + "\n"
