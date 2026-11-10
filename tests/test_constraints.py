import json
from pathlib import Path

import pytest

from jobomatic.fit.constraints import (
    SearchConstraints,
    constraints_path,
    load_constraints,
    private_dir,
)


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "search-constraints.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_missing_file_means_no_constraints(tmp_path: Path) -> None:
    assert load_constraints(tmp_path / "nope.json") is None


def test_loads_both_minimums(tmp_path: Path) -> None:
    got = load_constraints(
        _write(tmp_path, {"min_permanent_base_cad": 85000, "min_contract_hourly_cad": 60})
    )
    assert got == SearchConstraints(85000.0, 60.0)
    assert "$85,000" in got.describe() and "$60/hr" in got.describe()


def test_either_key_may_be_omitted(tmp_path: Path) -> None:
    got = load_constraints(_write(tmp_path, {"min_contract_hourly_cad": 60}))
    assert got == SearchConstraints(None, 60.0)


def test_underscore_keys_are_comments(tmp_path: Path) -> None:
    got = load_constraints(_write(tmp_path, {"_comment": "hi", "min_permanent_base_cad": 1}))
    assert got is not None and got.min_permanent_base_cad == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"min_permanent_base": 85000},  # typo'd key must not silently disable the screen
        {"min_permanent_base_cad": "85000"},
        {"min_permanent_base_cad": -5},
        {"min_permanent_base_cad": True},
        ["not", "an", "object"],
    ],
)
def test_malformed_file_fails_loudly(tmp_path: Path, payload: object) -> None:
    with pytest.raises(ValueError):
        load_constraints(_write(tmp_path, payload))


def test_invalid_json_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "search-constraints.json"
    path.write_text("{nope", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_constraints(path)


def test_env_override_is_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_JOBS_PRIVATE_DIR", str(tmp_path))
    assert private_dir() == tmp_path
    assert constraints_path() == tmp_path / "search-constraints.json"


def test_example_file_is_valid_and_real_file_is_gitignored() -> None:
    repo = Path(__file__).resolve().parents[1]
    example = repo / "private" / "search-constraints.example.json"
    assert load_constraints(example) is not None
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "private/*" in gitignore and "!private/*.example.*" in gitignore
