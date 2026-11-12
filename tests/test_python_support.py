"""The statements about which Python versions are supported agree (ADR 0033).

``requires-python`` gives the floor; the classifiers and the CI test matrix list the versions that
are claimed and tested. Adding a Python release means editing both lists, and this test fails when
only one of them is edited. The container image and the tools' target versions stay on the floor.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
CI = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def _version(text: str) -> tuple[int, int]:
    major, minor = text.split(".")[:2]
    return int(major), int(minor)


def _floor() -> tuple[int, int]:
    match = re.fullmatch(r">=\s*(\d+\.\d+)", PYPROJECT["project"]["requires-python"])
    assert match, "requires-python is expected to be a plain '>=X.Y' floor"
    return _version(match.group(1))


def _matrix() -> list[str]:
    return CI["jobs"]["tests"]["strategy"]["matrix"]["python-version"]


def test_the_matrix_versions_are_strings_so_that_3_10_is_not_read_as_3_1() -> None:
    assert all(isinstance(v, str) for v in _matrix()), _matrix()


def test_the_lowest_tested_version_is_the_floor_pyproject_declares() -> None:
    assert min(_version(v) for v in _matrix()) == _floor()


def test_the_classifiers_name_exactly_the_tested_versions() -> None:
    prefix = "Programming Language :: Python :: "
    claimed = {
        _version(c.removeprefix(prefix))
        for c in PYPROJECT["project"]["classifiers"]
        if c.startswith(prefix) and "." in c.removeprefix(prefix)
    }
    assert claimed == {_version(v) for v in _matrix()}


def test_the_matrix_has_no_gaps_between_the_floor_and_the_newest() -> None:
    minors = sorted(_version(v)[1] for v in _matrix())
    assert minors == list(range(minors[0], minors[-1] + 1))


def test_the_lint_job_runs_on_the_floor_and_tests_do_not_fail_fast() -> None:
    lint = CI["jobs"]["lint"]["steps"]
    versions = [s["with"]["python-version"] for s in lint if "setup-python" in s.get("uses", "")]
    assert [_version(v) for v in versions] == [_floor()]
    assert CI["jobs"]["tests"]["strategy"]["fail-fast"] is False


def test_the_container_and_the_tools_target_the_floor() -> None:
    floor = _floor()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    image = re.search(r"^FROM python:(\d+\.\d+)", dockerfile, re.MULTILINE)
    assert image and _version(image.group(1)) == floor
    assert _version(PYPROJECT["tool"]["mypy"]["python_version"]) == floor
    assert PYPROJECT["tool"]["ruff"]["target-version"] == f"py{floor[0]}{floor[1]}"


def test_every_ci_install_uses_the_lock() -> None:
    for job in ("lint", "tests"):
        installs = [s["run"] for s in CI["jobs"][job]["steps"] if s.get("name") == "Install"]
        assert installs and all("-c requirements-lock.txt" in run for run in installs), job
