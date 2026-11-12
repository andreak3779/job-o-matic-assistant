"""Show the user's private job-search constraints (salary minimums) (ADR 0028).

The values live in the vault's ``private/`` folder and never in a tracked file (ADR 0011).
"""

from __future__ import annotations

from dataclasses import dataclass

from jobomatic.fit.constraints import (
    MISSING_MESSAGE,
    SearchConstraints,
    constraints_path,
    load_constraints,
)
from jobomatic.results import CommandResult, guarded, ok


@dataclass(frozen=True)
class ConstraintsData:
    """The minimums, or ``None`` when the file is not there (a normal state, not an error)."""

    constraints: SearchConstraints | None
    filename: str


def show() -> CommandResult[ConstraintsData]:
    return guarded(_show)


def _show() -> CommandResult[ConstraintsData]:
    return ok(ConstraintsData(load_constraints(), constraints_path().name))


def render(data: ConstraintsData) -> str:
    if data.constraints is None:
        return MISSING_MESSAGE
    return f"Minimums ({data.filename}): {data.constraints.describe()}"
