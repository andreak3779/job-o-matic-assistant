"""The gates: when documents may be generated for a posting (ADR 0003, 0008, 0010, 0011, 0021).

Both interfaces, the command line and the MCP server, call these, so a rule holds no matter who
asks. The gates need the fit rules, the applications log and the salary constraints, which the
modules may not call from each other, so they sit here, one level above them.

What each gate decides:

- **Location**: a posting outside the job-search location rules is refused, never overridable
  (ADR 0008).
- **Fit rating** (resume and cover letter only): ``Strong`` and ``Good`` pass. ``Worth a try`` and
  ``Stretch`` are refused until the user says so (``confirm_gaps``). A skills ``Pass`` is never
  overridable (ADR 0021, decision F4).
- **Duplicate**: a posting already applied to inside the window is refused until the user says so
  (``confirm_reapply``, ADR 0010).
- **Pay**: stated pay below the user's minimum is refused until the user says so
  (``confirm_below_minimum``, ADR 0011).

An override is a decision the user makes, never a default; callers pass it only after the user has
said so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jobomatic import applications
from jobomatic.fit.constraints import SearchConstraints, load_constraints
from jobomatic.fit.engine import FitResult, rate_parsed_jd
from jobomatic.fit.parser import parse_jd
from jobomatic.fit.salary import assess_salary
from jobomatic.profile.model import Profile

PASSING_RATINGS = frozenset({"Strong", "Good"})
OVERRIDABLE_RATINGS = frozenset({"Worth a try", "Stretch"})

CONFIRM_GAPS = "confirm_gaps"
CONFIRM_REAPPLY = "confirm_reapply"
CONFIRM_BELOW_MINIMUM = "confirm_below_minimum"


class GateRefusal(Exception):
    """A gate said no. ``override`` names the confirmation that would let it through, if any."""

    def __init__(self, reason: str, override: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.override = override

    def __str__(self) -> str:
        if self.override is None:
            return self.reason
        flag = "--" + self.override.replace("_", "-")
        return (
            f"{self.reason}\nOnly if the user says so, run again with {self.override} "
            f"(command line: {flag}; tool: {self.override}=true)."
        )


@dataclass
class GateResult:
    """What passed, and what the caller should show the user alongside the documents."""

    fit: FitResult | None = None
    notes: list[str] = field(default_factory=list)


def check_location(jd_text: str) -> None:
    """Refuse on a location Pass only, never on skill fit (ADR 0008).

    For the tools that are not skill-gated (job-site letter, cold outreach given a posting): a
    role in an excluded region, on-site or hybrid outside the home city, or requiring French can't
    be taken however the letter is worded.
    """
    parsed = parse_jd(jd_text)
    if parsed.location_check.disqualified:
        reasons = "; ".join(parsed.location_check.disqualifiers)
        raise GateRefusal(
            "This role is outside the job-search location rules — refusing to generate: "
            f"{reasons}.\nSkills are not the blocker. Run fit-check for the full breakdown."
        )


def check_fit(jd_text: str, profile: Profile, *, confirm_gaps: bool = False) -> GateResult:
    """Refuse a rating below Good unless the user confirmed past a Stretch or Worth a try."""
    result = rate_parsed_jd(parse_jd(jd_text), profile)
    if result.rating in PASSING_RATINGS:
        return GateResult(fit=result)
    if result.location_disqualified:
        raise GateRefusal(
            f"Fit rating is {result.rating} — refusing to generate resume/cover letter.\n"
            f"{result.rationale}\n"
            "This role is outside the job-search location rules (an excluded region, on-site "
            "or hybrid outside the home city, Atlantic-only remote, or French required). "
            "Skills are not the blocker, and this cannot be confirmed past."
        )
    if result.rating in OVERRIDABLE_RATINGS:
        if confirm_gaps:
            note = (
                f"Proceeding past a {result.rating} rating at the user's request. "
                f"{result.rationale}"
            )
            return GateResult(fit=result, notes=[note])
        raise GateRefusal(
            f"Fit rating is {result.rating} (below Good) — not generating resume/cover letter "
            f"yet.\n{result.rationale}\nList the gaps for the user and ask whether to go ahead.",
            CONFIRM_GAPS,
        )
    raise GateRefusal(
        f"Fit rating is {result.rating} — refusing to generate resume/cover letter.\n"
        f"{result.rationale}\nA Pass on skills cannot be confirmed past: run fit-check for the "
        "full breakdown, or supply a stronger-fit posting."
    )


def check_duplicate(
    jd_text: str, *, confirm_reapply: bool = False, log_path: Path | None = None
) -> list[str]:
    """Refuse a posting already applied to inside the duplicate window (ADR 0010).

    Returns advisory notes (the no-response pattern, a repeat outside the window).
    """
    try:
        check = applications.check_jd_text(jd_text, path=log_path)
    except ValueError as exc:  # a corrupt log must stop generation, not be ignored
        raise GateRefusal(f"applications log is unreadable: {exc}") from exc
    notes = list(check.notes)
    if check.blocking and not confirm_reapply:
        raise GateRefusal(
            f"{check.summary()}\nNot generating: a cold re-application days or weeks after the "
            "first reads as a duplicate. Tell the user, and offer a warmer route (a referral or "
            "direct recruiter contact) or skipping it.",
            CONFIRM_REAPPLY,
        )
    if check.verdict in ("duplicate", "repeat"):
        notes.append(check.summary())
    return notes


def check_pay(
    jd_text: str,
    *,
    confirm_below_minimum: bool = False,
    constraints: SearchConstraints | None = None,
    load: bool = True,
) -> list[str]:
    """Refuse a stated pay below the user's minimum, unless confirmed (ADR 0011).

    A flag the user confirms past, not a Pass. No posted pay, or no configured minimums, never
    blocks. ``constraints`` may be passed in; otherwise they are read from the vault.
    """
    if constraints is None and load:
        try:
            constraints = load_constraints()
        except ValueError as exc:
            raise GateRefusal(f"private/search-constraints.json is invalid: {exc}") from exc
    assessment = assess_salary(jd_text, constraints)
    if assessment.below and not confirm_below_minimum:
        raise GateRefusal(
            f"{' '.join(assessment.below_minimum)}\nAsk the user whether to continue.",
            CONFIRM_BELOW_MINIMUM,
        )
    notes = list(assessment.flags)
    if assessment.below:
        notes.extend(assessment.below_minimum)
    return notes


def check_documents(
    jd_text: str,
    profile: Profile,
    *,
    confirm_gaps: bool = False,
    confirm_reapply: bool = False,
    confirm_below_minimum: bool = False,
    log_path: Path | None = None,
    constraints: SearchConstraints | None = None,
    load_constraints_from_vault: bool = True,
) -> GateResult:
    """The full gate for a tailored resume or cover letter: fit, duplicate and pay."""
    result = check_fit(jd_text, profile, confirm_gaps=confirm_gaps)
    result.notes += check_duplicate(jd_text, confirm_reapply=confirm_reapply, log_path=log_path)
    result.notes += check_pay(
        jd_text,
        confirm_below_minimum=confirm_below_minimum,
        constraints=constraints,
        load=load_constraints_from_vault,
    )
    return result


def check_letter(
    jd_text: str, *, confirm_reapply: bool = False, log_path: Path | None = None
) -> list[str]:
    """The gate for the job-site letter: location and duplicate, not skill fit (ADR 0003)."""
    check_location(jd_text)
    return check_duplicate(jd_text, confirm_reapply=confirm_reapply, log_path=log_path)
