#!/usr/bin/env python3
"""Rate a job description against the profile: an inline fit table (ADR 0028).

``run`` takes the posting as text and returns a ``CommandResult`` holding a ``FitCheckData``;
``render`` turns that into the markdown the command line prints and the MCP tool returns; ``main``
is the command line: read the file, ``run``, print.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from jobomatic import bootstrap
from jobomatic.commands.support import require_path
from jobomatic.fit.constraints import MISSING_MESSAGE, load_constraints
from jobomatic.fit.engine import FitResult, rate_parsed_jd, render_fit_table
from jobomatic.fit.parser import parse_jd
from jobomatic.fit.salary import SalaryAssessment, assess_salary, render_salary_screen
from jobomatic.results import CommandResult, emit, failure, guarded, ok


@dataclass(frozen=True)
class FitCheckData:
    title: str
    company: str
    fit: FitResult
    # None when the salary screen could not be run (the constraints file is invalid).
    salary: SalaryAssessment | None
    constraints_configured: bool


def run(jd_text: str) -> CommandResult[FitCheckData]:
    """Rate ``jd_text`` and screen its pay. The rating is computed in ``jobomatic.fit`` and is
    never re-derived here."""
    return guarded(lambda: _run(jd_text))


def _run(jd_text: str) -> CommandResult[FitCheckData]:
    profile = bootstrap.load_profile()
    parsed = parse_jd(jd_text)
    fit = rate_parsed_jd(parsed, profile)
    try:
        constraints = load_constraints()
    except ValueError as exc:
        # The table is still worth showing; the screen is what could not be run.
        data = FitCheckData(parsed.title, parsed.company, fit, None, False)
        return failure(f"private/search-constraints.json is invalid: {exc}", data=data)
    assessment = assess_salary(jd_text, constraints)
    return ok(FitCheckData(parsed.title, parsed.company, fit, assessment, constraints is not None))


def render(data: FitCheckData) -> str:
    """The fit table, then the salary screen when the posting states pay."""
    text = f"## Fit Check — {data.title} at {data.company}\n\n" + render_fit_table(
        data.fit
    ).replace("## Fit Check\n\n", "")
    if data.salary is not None:
        screen = render_salary_screen(data.salary, configured=data.constraints_configured)
        if screen:
            text += f"\n{screen}"
            if not data.constraints_configured:
                text += f"\n_{MISSING_MESSAGE}_"
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fit-check", description="Inline fit check for a job description"
    )
    parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    args = parser.parse_args(argv)

    try:
        require_path(args.jd, "JD file")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return emit(run(args.jd.read_text(encoding="utf-8")), render)


if __name__ == "__main__":
    raise SystemExit(main())
