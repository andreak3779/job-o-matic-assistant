"""What ``pyproject.toml`` promises about packaging matches what is in the repository (ADR 0033).

* The lock gives every dependency an exact pin that satisfies the declared range. It once lacked
  ``sqlite-vec``, a core dependency, so CI and the container installed whatever was newest.
* The hand-written list of packages equals the folders that are packages, and every data file sits
  under a ``package-data`` pattern. Only editable installs are supported, where an unlisted package
  still imports; a wheel would miss it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
SRC = ROOT / "src"


def _declared() -> list[Requirement]:
    project = PYPROJECT["project"]
    lines = list(project["dependencies"])
    for extra in project["optional-dependencies"].values():
        lines.extend(extra)
    return [Requirement(line) for line in lines]


def _lock() -> dict[str, list[str]]:
    pins: dict[str, list[str]] = {}
    for raw in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        name, _, version = line.partition("==")
        pins.setdefault(canonicalize_name(name), []).append(version)
    return pins


# -- the lock ----------------------------------------------------------------------------------


def test_every_declared_dependency_has_an_exact_pin_in_the_lock() -> None:
    pins = _lock()
    missing = sorted({canonicalize_name(r.name) for r in _declared()} - set(pins))
    assert not missing, f"in pyproject.toml but not pinned in requirements-lock.txt: {missing}"


def test_every_pin_satisfies_the_range_pyproject_declares() -> None:
    pins = _lock()
    wrong = []
    for requirement in _declared():
        for version in pins.get(canonicalize_name(requirement.name), []):
            if not requirement.specifier.contains(Version(version), prereleases=True):
                wrong.append(f"{requirement.name}=={version} is outside {requirement.specifier}")
    assert not wrong, "\n".join(wrong)


def test_the_lock_pins_each_package_once_and_exactly() -> None:
    for name, versions in _lock().items():
        assert len(versions) == 1 and versions[0], f"{name}: {versions}"


# -- the package list --------------------------------------------------------------------------


def _package_folders() -> set[str]:
    return {
        ".".join(init.parent.relative_to(SRC).parts)
        for init in SRC.rglob("__init__.py")
        if "__pycache__" not in init.parts
    }


def test_the_package_list_is_exactly_the_folders_that_are_packages() -> None:
    listed = set(PYPROJECT["tool"]["setuptools"]["packages"])
    folders = _package_folders()
    assert listed == folders, (
        f"folders not listed in pyproject.toml: {sorted(folders - listed)}; "
        f"listed but not a folder: {sorted(listed - folders)}"
    )


def test_every_data_file_is_covered_by_a_package_data_pattern() -> None:
    package_data = PYPROJECT["tool"]["setuptools"]["package-data"]
    covered: set[Path] = set()
    for package, patterns in package_data.items():
        folder = SRC.joinpath(*package.split("."))
        for pattern in patterns:
            covered.update(p for p in folder.glob(pattern) if p.is_file())
    data_files = {
        p
        for p in (SRC / "jobomatic").rglob("*")
        # A README documents a folder and is read from the checkout, never by the code.
        if p.is_file()
        and p.suffix not in {".py", ".pyc"}
        and p.name != "README.md"
        and "__pycache__" not in p.parts
    }
    uncovered = sorted(str(p.relative_to(SRC)) for p in data_files - covered)
    assert not uncovered, f"data files that a wheel would leave out: {uncovered}"


def test_only_editable_installs_are_declared_supported() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "only editable installs" in text


@pytest.mark.parametrize("extra", ["mcp", "parser", "pdf", "dev", "lint"])
def test_the_extras_the_setup_and_ci_install_exist(extra: str) -> None:
    assert extra in PYPROJECT["project"]["optional-dependencies"]
