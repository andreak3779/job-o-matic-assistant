"""scripts/check_pushed_commits.py against real git repositories (ADR 0032).

Each test builds a throwaway repository with a bare remote and a throwaway vault holding fictional
terms, then runs the script the way the pre-push hook does: with the lines git sends on stdin.
Nothing here touches this repository, its remote or a real vault.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from jobomatic import paths

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_pushed_commits.py"
NULL = "0" * 40

TERMS = {
    "names": ["Jordan Example"],
    "emails": ["jordan@example.com"],
    "phones": [],
    "employers": ["Acme Widgets"],
    "identifiers": [],
}


@dataclass
class World:
    work: Path
    env: dict[str, str]

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.work, env=self.env, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def commit(
        self, name: str, text: str, message: str = "change", author: str | None = None
    ) -> str:
        (self.work / name).write_text(text, encoding="utf-8")
        self.git("add", name)
        extra = ["--author", author] if author else []
        self.git("commit", "-q", "-m", message, *extra)
        return self.git("rev-parse", "HEAD")

    def run(
        self, stdin: str = "", *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.work,
            env=env or self.env,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )

    def push_line(self, local: str, remote: str | None, ref: str = "refs/heads/feat") -> str:
        return f"{ref} {local} {ref} {remote or NULL}\n"


@pytest.fixture
def world(tmp_path: Path) -> World:
    vault = tmp_path / "vault"
    (vault / "private").mkdir(parents=True)
    (vault / ".jobomatic.toml").write_text("vault_version = 1\n", encoding="utf-8")
    (vault / "private" / "pii-terms.json").write_text(json.dumps(TERMS), encoding="utf-8")

    # No variable of git's (GIT_DIR, GIT_INDEX_FILE...) may leak in when the suite runs from a hook,
    # and no JOBOMATIC_ variable may point at anything but this vault.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("GIT_", "JOBOMATIC_")) and k not in paths.RETIRED_VARIABLES
    }
    env |= {
        "JOBOMATIC_VAULT": str(vault),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], env=env, check=True)
    work.mkdir()
    w = World(work, env)
    w.git("init", "-q", "-b", "main")
    w.git("config", "user.name", "Test Author")
    w.git("config", "user.email", "noreply@example.com")
    w.git("remote", "add", "origin", str(remote))
    w.commit("README.md", "hello\n", "first")
    w.git("push", "-q", "origin", "main")
    w.git("checkout", "-q", "-b", "feat")
    return w


def test_a_clean_branch_new_to_the_remote_passes(world: World) -> None:
    tip = world.commit("notes.md", "nothing private\n")
    done = world.run(world.push_line(tip, None))
    assert done.returncode == 0, done.stderr
    assert "clean" in done.stdout


def test_a_private_value_added_in_a_new_branch_blocks_and_never_prints_the_value(
    world: World,
) -> None:
    tip = world.commit("notes.md", "line one\nI worked at acme widgets\n")
    done = world.run(world.push_line(tip, None))
    assert done.returncode == 1
    assert "notes.md:2 (employers)" in done.stderr
    assert "acme" not in (done.stdout + done.stderr).lower().replace("pii-terms", "")


def test_a_value_added_in_one_commit_and_removed_in_the_next_is_still_caught(world: World) -> None:
    world.commit("notes.md", "Jordan Example\n", "add")
    tip = world.commit("notes.md", "gone\n", "remove")
    done = world.run(world.push_line(tip, None))
    assert done.returncode == 1  # the first commit is published too, whatever the net change is
    assert "notes.md:1 (names)" in done.stderr


def test_a_value_only_in_a_removed_line_passes(world: World) -> None:
    world.git("checkout", "-q", "main")
    world.commit("old.md", "Acme Widgets\n", "was already public")
    world.git("push", "-q", "origin", "main")
    world.git("checkout", "-q", "-b", "cleanup")
    tip = world.commit("old.md", "scrubbed\n", "scrub it")
    done = world.run(world.push_line(tip, None, "refs/heads/cleanup"))
    assert done.returncode == 0, done.stderr


def test_an_update_is_compared_with_the_remote_commit(world: World) -> None:
    first = world.commit("a.md", "fine\n")
    world.git("push", "-q", "origin", "feat")
    tip = world.commit("b.md", "Jordan Example\n")
    done = world.run(world.push_line(tip, first))
    assert done.returncode == 1
    assert "b.md:1 (names)" in done.stderr
    assert "a.md" not in done.stderr


def test_a_private_value_in_a_commit_message_is_caught(world: World) -> None:
    tip = world.commit("a.md", "fine\n", "thanks to Jordan Example")
    done = world.run(world.push_line(tip, None))
    assert done.returncode == 1
    assert f"commit {tip[:10]}:3 (names)" in done.stderr


def test_a_private_author_email_is_caught(world: World) -> None:
    tip = world.commit("a.md", "fine\n", author="Someone <jordan@example.com>")
    done = world.run(world.push_line(tip, None))
    assert done.returncode == 1
    assert f"commit {tip[:10]}:1 (emails)" in done.stderr


def test_a_deletion_publishes_nothing_and_passes(world: World) -> None:
    done = world.run(f"(delete) {NULL} refs/heads/feat {'a' * 40}\n")
    assert done.returncode == 0
    assert "clean" in done.stdout


def test_an_empty_push_passes(world: World) -> None:
    assert world.run("").returncode == 0


def test_a_remote_commit_this_clone_does_not_have_falls_back_to_the_base_branch(
    world: World,
) -> None:
    tip = world.commit("notes.md", "Jordan Example\n")
    done = world.run(world.push_line(tip, "f" * 40))
    assert done.returncode == 1
    assert "notes.md:1 (names)" in done.stderr


def test_with_no_base_branch_the_whole_history_is_audited(world: World) -> None:
    world.git("update-ref", "-d", "refs/remotes/origin/main")
    world.git("checkout", "-q", "-b", "orphanish")
    world.git("branch", "-q", "-m", "main", "trunk")  # no branch is called main any more
    tip = world.commit("notes.md", "Jordan Example\n")
    done = world.run(world.push_line(tip, None, "refs/heads/orphanish"))
    assert done.returncode == 1
    assert "notes.md:1 (names)" in done.stderr


def test_a_range_given_by_hand_is_audited(world: World) -> None:
    world.commit("notes.md", "Jordan Example\n")
    done = world.run("", "--range", "main..HEAD")
    assert done.returncode == 1
    assert "notes.md:1 (names)" in done.stderr
    assert world.run("", "--range", "HEAD..HEAD").returncode == 0


def test_a_range_that_does_not_exist_is_an_error_not_a_pass(world: World) -> None:
    done = world.run("", "--range", "nope..HEAD")
    assert done.returncode == 1
    assert "failed" in done.stderr


def test_a_path_on_the_allowlist_would_be_skipped_only_by_the_repository_file(world: World) -> None:
    # The allowlist is the repository's scripts/pii-allowlist.txt (empty); a path in a scratch
    # repository is not on it.
    tip = world.commit("pii-allowlist.txt", "Jordan Example\n")
    assert world.run(world.push_line(tip, None)).returncode == 1


def test_without_a_vault_the_audit_is_skipped_with_a_clear_line(
    world: World, tmp_path: Path
) -> None:
    env = dict(world.env, JOBOMATIC_VAULT=str(tmp_path / "no-such-vault"))
    tip = world.commit("notes.md", "Jordan Example\n")
    done = world.run(world.push_line(tip, None), env=env)
    assert done.returncode == 0
    assert "skipped" in done.stdout


def test_without_a_terms_file_the_audit_is_skipped(world: World) -> None:
    (Path(world.env["JOBOMATIC_VAULT"]) / "private" / "pii-terms.json").unlink()
    tip = world.commit("notes.md", "Jordan Example\n")
    done = world.run(world.push_line(tip, None))
    assert done.returncode == 0
    assert "skipped" in done.stdout


def test_a_broken_terms_file_is_an_error(world: World) -> None:
    (Path(world.env["JOBOMATIC_VAULT"]) / "private" / "pii-terms.json").write_text(
        "[1]", encoding="utf-8"
    )
    tip = world.commit("notes.md", "fine\n")
    assert world.run(world.push_line(tip, None)).returncode == 1


def test_an_old_variable_name_is_an_error_not_a_silent_skip(world: World) -> None:
    # ADR 0030: a retired variable raises VaultError, which this script also uses for "no vault".
    # It must not be read as "no vault", or a stale variable would quietly switch the audit off.
    old = next(iter(paths.RETIRED_VARIABLES))
    tip = world.commit("notes.md", "Jordan Example\n")
    done = world.run(world.push_line(tip, None), env=dict(world.env, **{old: "/nowhere"}))
    assert done.returncode == 1
    assert "no longer read" in done.stderr and "skipped" not in done.stdout


# -- the hook files ----------------------------------------------------------------------------


@pytest.mark.parametrize("hook", ["pre-commit", "pre-push"])
def test_each_hook_is_executable_bash_that_parses(hook: str) -> None:
    path = ROOT / "scripts" / "hooks" / hook
    assert os.access(path, os.X_OK)
    assert subprocess.run(["bash", "-n", str(path)], check=False).returncode == 0


def test_the_commit_hook_no_longer_runs_the_tests_and_the_push_hook_does() -> None:
    commit = (ROOT / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    push = (ROOT / "scripts" / "hooks" / "pre-push").read_text(encoding="utf-8")
    assert "pytest tests" not in commit
    assert "pytest tests" in push and "check_pushed_commits.py" in push
    # What a leak needs before a commit exists stays on commit.
    for check in ("check_private_values.py", "staged-file guard", "lint-imports", "mypy src"):
        assert check in commit, check
