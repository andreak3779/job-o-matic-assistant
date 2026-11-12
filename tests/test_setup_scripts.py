"""scripts/setup.sh and scripts/check-setup.sh: the parts that can be tested without installing.

Every test runs a *copy* of the scripts inside a temporary folder, so none of them can touch the
real checkout's .venv. The full install is checked by hand on a clean clone (ADR 0026); here we
cover option handling, distro detection and the messages for the failures a new user meets.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ("setup.sh", "check-setup.sh")
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is not available")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway folder with copies of the scripts and nothing else, so it has no .venv."""
    target = tmp_path / "repo"
    (target / "scripts").mkdir(parents=True)
    for name in SCRIPTS:
        shutil.copy(ROOT / "scripts" / name, target / "scripts" / name)
    shutil.copytree(ROOT / "scripts" / "lib", target / "scripts" / "lib")
    (target / "pyproject.toml").write_text("", encoding="utf-8")
    (target / "requirements-lock.txt").write_text("", encoding="utf-8")
    return target


def run(
    repo: Path, script: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ, "NO_COLOR": "1", **(env or {})}
    return subprocess.run(
        [str(BASH), str(repo / "scripts" / script), *args],
        cwd=repo,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


# ── The files themselves ─────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["setup.sh", "check-setup.sh", "lib/setup-common.sh"])
def test_every_script_is_valid_bash(name: str) -> None:
    result = subprocess.run(
        [str(BASH), "-n", str(ROOT / "scripts" / name)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_scripts_are_executable_and_start_with_a_shebang(name: str) -> None:
    path = ROOT / "scripts" / name
    assert os.access(path, os.X_OK)
    assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")


# ── Options ──────────────────────────────────────────────────────────────────


def test_setup_help_lists_every_option(repo: Path) -> None:
    result = run(repo, "setup.sh", "--help")
    assert result.returncode == 0
    for option in ("--no-dev", "--hooks", "--recreate", "--python", "--vault-url", "--new-vault"):
        assert option in result.stdout


@pytest.mark.parametrize(
    "args",
    [("--nope",), ("--python",), ("--vault-url",), ("--vault-url", "x", "--new-vault")],
)
def test_setup_rejects_bad_options_with_status_2_and_a_hint(
    repo: Path, args: tuple[str, ...]
) -> None:
    result = run(repo, "setup.sh", *args)
    assert result.returncode == 2
    assert "--help" in result.stderr


def test_check_setup_help_and_bad_option(repo: Path) -> None:
    assert run(repo, "check-setup.sh", "--help").returncode == 0
    assert run(repo, "check-setup.sh", "--nope").returncode == 2


# ── Which distro is this? ────────────────────────────────────────────────────

OS_RELEASES = {
    "zorin": ('PRETTY_NAME="Zorin OS 18"\nID=zorin\nID_LIKE="ubuntu debian"\n', "debian", "yes"),
    "mint": (
        'PRETTY_NAME="Linux Mint 22"\nID=linuxmint\nID_LIKE="ubuntu debian"\n',
        "debian",
        "yes",
    ),
    "ubuntu": ('PRETTY_NAME="Ubuntu 24.04"\nID=ubuntu\nID_LIKE=debian\n', "debian", "yes"),
    "debian": ('PRETTY_NAME="Debian GNU/Linux 12"\nID=debian\n', "debian", "no"),
    "raspbian": ('PRETTY_NAME="Raspbian"\nID=raspbian\nID_LIKE=debian\n', "debian", "no"),
    "fedora": ('PRETTY_NAME="Fedora Linux 41"\nID=fedora\n', "other", "no"),
    "arch": ('PRETTY_NAME="Arch Linux"\nID=arch\n', "other", "no"),
    # A name that merely contains "debian" or "ubuntu" must not count as the family.
    "lookalike": ('PRETTY_NAME="Notubuntu"\nID=notubuntu\nID_LIKE=notdebian\n', "other", "no"),
}


@pytest.mark.parametrize("name", OS_RELEASES)
def test_distro_family_comes_from_id_and_id_like(tmp_path: Path, name: str) -> None:
    content, family, ubuntu_based = OS_RELEASES[name]
    release = tmp_path / "os-release"
    release.write_text(content, encoding="utf-8")
    result = subprocess.run(
        [
            str(BASH),
            "-c",
            '. "$1"; detect_distro; echo "$DISTRO_FAMILY $DISTRO_UBUNTU_BASED"',
            "_",
            str(ROOT / "scripts" / "lib" / "setup-common.sh"),
        ],
        env={**os.environ, "JOBOMATIC_OS_RELEASE": str(release)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip() == f"{family} {ubuntu_based}", result.stderr


def test_a_missing_os_release_is_not_an_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            str(BASH),
            "-c",
            '. "$1"; detect_distro; echo "$DISTRO_FAMILY $DISTRO_NAME"',
            "_",
            str(ROOT / "scripts" / "lib" / "setup-common.sh"),
        ],
        env={**os.environ, "JOBOMATIC_OS_RELEASE": str(tmp_path / "nope")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip() == "other unknown"


# ── The failures a new user meets ────────────────────────────────────────────

TOOLS = (
    "bash env mktemp df awk id dirname cat tail sed rm basename git cp mkdir head tr grep"
).split()


def restricted_path(tmp_path: Path, fake_python3: str) -> str:
    """A PATH holding the basic tools and a fake python3, and no real Python at all."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    fake = bin_dir / "python3"
    fake.write_text(fake_python3, encoding="utf-8")
    fake.chmod(0o755)
    return str(bin_dir)


OLD_PYTHON = """#!/bin/sh
case "$*" in
  *"sys.version_info >= (3, 11)"*) exit 1;;
  *'print("%d.%d.%d"'*) echo 3.10.12; exit 0;;
esac
exit 0
"""

NO_VENV_MODULE = """#!/bin/sh
case "$*" in
  *"sys.version_info >= (3, 11)"*) exit 0;;
  *'print("%d.%d.%d"'*) echo 3.12.3; exit 0;;
  *"-m venv"*) echo "ensurepip is not available" >&2; exit 1;;
esac
exit 0
"""


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="setup.sh refuses root")
@pytest.mark.parametrize(
    ("os_release", "expected"),
    [
        ('ID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 22.04"\n', "deadsnakes"),
        ('ID=linuxmint\nID_LIKE="ubuntu debian"\nPRETTY_NAME="Linux Mint 21"\n', "deadsnakes"),
        ('ID=debian\nPRETTY_NAME="Debian GNU/Linux 11"\n', "Upgrade to Debian 12"),
        ('ID=fedora\nPRETTY_NAME="Fedora"\n', "package manager"),
    ],
)
def test_a_python_that_is_too_old_gets_advice_for_that_distro(
    repo: Path, tmp_path: Path, os_release: str, expected: str
) -> None:
    release = tmp_path / "os-release"
    release.write_text(os_release, encoding="utf-8")
    result = run(
        repo,
        "setup.sh",
        env={
            "PATH": restricted_path(tmp_path, OLD_PYTHON),
            "JOBOMATIC_OS_RELEASE": str(release),
        },
    )
    assert result.returncode == 1
    assert "Python 3.10.12 is too old" in result.stdout
    assert expected in result.stdout
    assert not (repo / ".venv").exists()


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="setup.sh refuses root")
def test_a_missing_venv_module_names_the_package_to_install(repo: Path, tmp_path: Path) -> None:
    release = tmp_path / "os-release"
    release.write_text('ID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 24.04"\n', encoding="utf-8")
    result = run(
        repo,
        "setup.sh",
        env={
            "PATH": restricted_path(tmp_path, NO_VENV_MODULE),
            "JOBOMATIC_OS_RELEASE": str(release),
        },
    )
    assert result.returncode == 1
    assert "sudo apt update && sudo apt install -y python3-venv" in result.stdout
    assert not (repo / ".venv").exists()


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="setup.sh refuses root")
def test_a_python_argument_that_does_not_run_is_reported(repo: Path) -> None:
    result = run(repo, "setup.sh", "--python", "/nonexistent/python")
    assert result.returncode == 1
    assert "is not Python 3.11 or newer, or does not run" in result.stdout


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="setup.sh refuses root")
def test_a_folder_called_dot_venv_that_is_not_a_venv_is_never_deleted(repo: Path) -> None:
    folder = repo / ".venv"
    folder.mkdir()
    (folder / "keep.txt").write_text("mine", encoding="utf-8")
    python = shutil.which("python3")
    assert python is not None
    result = run(repo, "setup.sh", "--python", python)
    assert result.returncode == 1
    assert "is not a virtual environment" in result.stdout
    assert (folder / "keep.txt").read_text(encoding="utf-8") == "mine"


def test_check_setup_without_an_install_fails_and_says_what_to_run(repo: Path) -> None:
    result = run(repo, "check-setup.sh")
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "There is no .venv here. Run:  bash scripts/setup.sh" in result.stdout
    assert "Pre-1.0, in active development." in result.stdout
