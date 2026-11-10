"""Private job-search constraints (salary minimums), kept out of git.

The values live in the vault's ``private/search-constraints.json`` (see
``private/search-constraints.example.json`` for the shape). They are deliberately
*not* in any tracked file: a walk-away number is a negotiating position, and the
repo is cloned to more than one machine.

A missing file is normal (CI, a fresh clone, the second laptop before the file is
copied over) and means "no salary screen". A *malformed* file raises ``ValueError``
rather than being ignored (ADR 0007): a typo'd key that silently disabled the
screen would be worse than a loud failure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jobomatic import paths

CONSTRAINTS_FILENAME = "search-constraints.json"
_KNOWN_KEYS = ("min_permanent_base_cad", "min_contract_hourly_cad")


@dataclass(frozen=True)
class SearchConstraints:
    """Walk-away minimums, in CAD. ``None`` means "no minimum set"."""

    min_permanent_base_cad: float | None = None
    min_contract_hourly_cad: float | None = None

    def describe(self) -> str:
        parts = []
        if self.min_permanent_base_cad is not None:
            parts.append(f"permanent base ${self.min_permanent_base_cad:,.0f}")
        if self.min_contract_hourly_cad is not None:
            parts.append(f"contract ${self.min_contract_hourly_cad:,.0f}/hr")
        return ", ".join(parts) or "no minimums set"


def private_dir() -> Path:
    """Directory holding gitignored personal files (override: CLAUDE_JOBS_PRIVATE_DIR)."""
    return paths.private_dir()


def constraints_path() -> Path:
    return private_dir() / CONSTRAINTS_FILENAME


def _positive_number(data: dict[str, object], key: str, source: str) -> float | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{source}: {key} must be a positive number, got {value!r}")
    return float(value)


def load_constraints(path: Path | None = None) -> SearchConstraints | None:
    """Load the constraints file; ``None`` when it does not exist."""
    path = path or constraints_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    unknown = sorted(k for k in data if k not in _KNOWN_KEYS and not k.startswith("_"))
    if unknown:
        raise ValueError(
            f"{path.name} has unknown key(s) {unknown}; expected {list(_KNOWN_KEYS)} "
            "(keys starting with '_' are treated as comments)"
        )
    return SearchConstraints(
        min_permanent_base_cad=_positive_number(data, "min_permanent_base_cad", path.name),
        min_contract_hourly_cad=_positive_number(data, "min_contract_hourly_cad", path.name),
    )


MISSING_MESSAGE = (
    "No private/search-constraints.json found — the salary screen is skipped. "
    "Copy it from your other machine, or create it from "
    "private/search-constraints.example.json."
)
