#!/usr/bin/env python3
"""Print an inline fit table for a job description."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

from jobomatic.commands.support import load_profile_or_none, require_path
from jobomatic.fit.constraints import MISSING_MESSAGE, load_constraints
from jobomatic.fit.engine import rate_parsed_jd, render_fit_table
from jobomatic.fit.parser import parse_jd
from jobomatic.fit.salary import assess_salary, render_salary_screen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fit-check", description="Inline fit check for a job description"
    )
    parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    parser.add_argument(
        "--root",
        type=Path,
        help="Repository root to read the profile from (default: the vault)",
    )
    args = parser.parse_args(argv)

    try:
        require_path(args.jd, "JD file")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    profile = load_profile_or_none(args.root or ROOT)
    if profile is None:
        return 1
    jd_text = args.jd.read_text(encoding="utf-8")
    parsed = parse_jd(jd_text)
    result = rate_parsed_jd(parsed, profile)

    print(f"## Fit Check — {parsed.title} at {parsed.company}\n")
    print(render_fit_table(result).replace("## Fit Check\n\n", ""))

    try:
        constraints = load_constraints()
    except ValueError as exc:
        print(f"ERROR: private/search-constraints.json is invalid: {exc}", file=sys.stderr)
        return 1
    assessment = assess_salary(jd_text, constraints)
    screen = render_salary_screen(assessment, configured=constraints is not None)
    if screen:
        print(screen)
        if constraints is None:
            print(f"_{MISSING_MESSAGE}_")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
