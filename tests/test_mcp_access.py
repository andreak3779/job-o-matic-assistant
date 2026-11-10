"""Contract for ``mcp_server.access``: the rules that keep Claude Desktop inside its lane."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobomatic.interfaces.mcp import access
from jobomatic.interfaces.mcp.access import Locations, Policy

# ── resolve ──────────────────────────────────────────────────────────────────


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    allowed = tmp_path / "allowed"
    denied = allowed / "secret"
    denied.mkdir(parents=True)
    return allowed, denied


def test_a_path_inside_a_root_is_allowed_and_returned_resolved(roots, tmp_path):
    allowed, denied = roots
    target = allowed / "a" / ".." / "note.md"
    assert access.resolve(target, [allowed], [denied]) == (allowed / "note.md").resolve()


def test_a_str_works_like_a_path(roots):
    allowed, denied = roots
    assert access.resolve(str(allowed / "x.md"), [allowed], [denied]) is not None


def test_the_root_itself_is_allowed(roots):
    allowed, denied = roots
    assert access.resolve(allowed, [allowed], [denied]) == allowed.resolve()


def test_a_file_that_does_not_exist_yet_is_allowed(roots):
    allowed, denied = roots
    assert access.resolve(allowed / "new" / "later.docx", [allowed], [denied]) is not None


def test_a_path_outside_every_root_is_refused(roots, tmp_path):
    allowed, denied = roots
    assert access.resolve(tmp_path / "elsewhere.md", [allowed], [denied]) is None
    assert access.resolve(allowed / "x.md", [], [denied]) is None


def test_dot_dot_cannot_climb_out_of_a_root(roots, tmp_path):
    allowed, denied = roots
    assert access.resolve(allowed / ".." / "elsewhere.md", [allowed], [denied]) is None


def test_a_sibling_with_the_same_prefix_is_not_inside_the_root(tmp_path):
    root = tmp_path / "outputs"
    evil = tmp_path / "outputs-evil"
    root.mkdir()
    evil.mkdir()
    assert access.resolve(evil / "x.md", [root], []) is None


def test_denied_wins_over_a_root_that_contains_it(roots):
    allowed, denied = roots
    assert access.resolve(denied / "salary.json", [allowed], [denied]) is None
    assert access.resolve(denied, [allowed], [denied]) is None


def test_dot_dot_into_a_denied_path_is_refused(roots):
    allowed, denied = roots
    sneaky = allowed / "public" / ".." / "secret" / "salary.json"
    assert access.resolve(sneaky, [allowed], [denied]) is None


def test_a_symlink_inside_a_root_cannot_lead_out_of_it(roots, tmp_path):
    allowed, denied = roots
    outside = tmp_path / "outside"
    outside.mkdir()
    (allowed / "link").symlink_to(outside, target_is_directory=True)
    assert access.resolve(allowed / "link" / "x.md", [allowed], [denied]) is None


def test_a_symlink_into_a_denied_path_is_refused(roots):
    allowed, denied = roots
    (allowed / "shortcut").symlink_to(denied, target_is_directory=True)
    assert access.resolve(allowed / "shortcut" / "salary.json", [allowed], [denied]) is None


def test_a_root_that_is_itself_a_symlink_still_matches(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert access.resolve(real / "x.md", [alias], []) is not None
    assert access.resolve(alias / "x.md", [real], []) is not None


def test_a_denied_path_that_is_a_symlink_still_matches(tmp_path):
    root = tmp_path / "root"
    real = root / "private"
    real.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert access.resolve(real / "x.json", [root], [alias]) is None


def test_any_git_directory_is_denied_wherever_it_is(roots):
    allowed, denied = roots
    assert access.resolve(allowed / "project" / ".git" / "config", [allowed], [denied]) is None
    assert access.resolve(allowed / ".git", [allowed], [denied]) is None


def test_a_name_that_only_contains_git_is_fine(roots):
    allowed, denied = roots
    assert access.resolve(allowed / ".github" / "ci.yml", [allowed], [denied]) is not None
    assert access.resolve(allowed / "notes.git.md", [allowed], [denied]) is not None


def test_tilde_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert access.resolve("~/x.md", [tmp_path], []) == (tmp_path / "x.md").resolve()


def test_an_unknown_user_is_refused_not_a_crash():
    assert access.resolve("~no_such_user_here/x.md", [Path("/")], []) is None


def test_a_null_byte_is_refused_not_a_crash(roots):
    allowed, denied = roots
    assert access.resolve(f"{allowed}/a\0b", [allowed], [denied]) is None


def test_a_symlink_that_points_at_git_is_refused_whatever_it_is_called(roots, tmp_path):
    allowed, denied = roots
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "config").write_text("[core]\n")
    (allowed / "notes").symlink_to(repo / ".git", target_is_directory=True)
    assert access.resolve(allowed / "notes" / "config", [allowed, repo], [denied]) is None


def test_a_sibling_with_the_same_prefix_as_a_denied_path_is_not_denied(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    private = root / "private"
    log = root / "applications.jsonl"
    assert access.resolve(root / "private-notes" / "x.md", [root], [private]) is not None
    assert access.resolve(root / "applications.jsonl.bak", [root], [log]) is not None
    assert access.resolve(log, [root], [log]) is None


def test_a_relative_path_is_resolved_against_the_current_directory(roots, monkeypatch, tmp_path):
    allowed, denied = roots
    monkeypatch.chdir(allowed)
    assert access.resolve("jd.md", [allowed], [denied]) == (allowed / "jd.md").resolve()
    assert access.resolve("secret/salary.json", [allowed], [denied]) is None
    assert access.resolve("../elsewhere.md", [allowed], [denied]) is None


def test_the_empty_string_means_the_current_directory_and_follows_the_same_rules(
    roots, monkeypatch, tmp_path
):
    allowed, denied = roots
    monkeypatch.chdir(tmp_path)
    assert access.resolve("", [allowed], [denied]) is None
    monkeypatch.chdir(allowed)
    assert access.resolve("", [allowed], [denied]) == allowed.resolve()


# ── build_policy ─────────────────────────────────────────────────────────────


@pytest.fixture
def where(tmp_path: Path) -> Locations:
    vault = tmp_path / "vault"
    code = tmp_path / "code"
    for folder in (
        vault / "outputs" / "learning-plans",
        vault / "profile",
        vault / "imports",
        vault / "private",
        vault / "applications",
        vault / ".git",
        code / ".git",
        code / "private",
        code / "mcp_server",
        tmp_path / "tmp",
        tmp_path / "extra",
    ):
        folder.mkdir(parents=True)
    return Locations(
        code_root=code,
        temp=tmp_path / "tmp",
        extra=(tmp_path / "extra",),
        vault=vault,
        outputs=vault / "outputs",
        learning_plans=vault / "outputs" / "learning-plans",
        stories_file=vault / "profile" / "stories.yaml",
        private=vault / "private",
        applications_log=vault / "applications" / "applications.jsonl",
    )


def allowed(policy: Policy, path: Path, *, write: bool) -> bool:
    return access.resolve(path, policy.roots(write=write), policy.denied) is not None


def test_outputs_are_readable_and_writable(where):
    policy = access.build_policy(where)
    target = where.outputs / "2026-11-02_acme_dev" / "resume.docx"
    assert allowed(policy, target, write=False)
    assert allowed(policy, target, write=True)
    assert allowed(policy, where.learning_plans / "plan.pdf", write=True)


def test_the_rest_of_the_vault_is_read_only(where):
    policy = access.build_policy(where)
    for path in (where.vault / "profile" / "skills.yaml", where.vault / "imports" / "x.html"):
        assert allowed(policy, path, write=False)
        assert not allowed(policy, path, write=True)


def test_the_stories_file_alone_is_writable_in_the_profile(where):
    policy = access.build_policy(where)
    assert allowed(policy, where.stories_file, write=True)
    assert not allowed(policy, where.stories_file.parent / "other.yaml", write=True)


def test_private_and_the_applications_log_are_closed_both_ways(where):
    policy = access.build_policy(where)
    for path in (where.private / "constraints.json", where.applications_log):
        assert not allowed(policy, path, write=False)
        assert not allowed(policy, path, write=True)


def test_git_and_in_repo_private_are_closed_both_ways(where):
    policy = access.build_policy(where)
    for path in (
        where.vault / ".git" / "config",
        where.code_root / ".git" / "config",
        where.code_root / "private" / "x.json",
    ):
        assert not allowed(policy, path, write=False)
        assert not allowed(policy, path, write=True)


def test_the_code_repository_is_neither_readable_nor_writable(where):
    policy = access.build_policy(where)
    path = where.code_root / "mcp_server" / "server.py"
    assert not allowed(policy, path, write=False)
    assert not allowed(policy, path, write=True)


def test_temp_and_extra_directories_are_readable_and_writable(where):
    policy = access.build_policy(where)
    for folder in (where.temp, *where.extra):
        assert allowed(policy, folder / "jd.md", write=False)
        assert allowed(policy, folder / "out.docx", write=True)


def test_without_a_vault_only_temp_and_extra_are_open(where):
    policy = access.build_policy(Locations(code_root=where.code_root, temp=where.temp))
    assert allowed(policy, where.temp / "jd.md", write=True)
    assert not allowed(policy, where.vault / "profile" / "skills.yaml", write=False)
    assert not allowed(policy, where.code_root / "mcp_server" / "server.py", write=False)


def test_a_broad_extra_directory_does_not_open_private_or_the_applications_log(where, tmp_path):
    broad = Locations(
        code_root=where.code_root,
        temp=where.temp,
        extra=(tmp_path,),  # the parent of the vault and the code repo
        vault=where.vault,
        outputs=where.outputs,
        learning_plans=where.learning_plans,
        stories_file=where.stories_file,
        private=where.private,
        applications_log=where.applications_log,
    )
    policy = access.build_policy(broad)
    for path in (
        where.private / "constraints.json",
        where.applications_log,
        where.vault / ".git" / "config",
        where.code_root / ".git" / "config",
        where.code_root / "private" / "x.json",
    ):
        assert not allowed(policy, path, write=False)
        assert not allowed(policy, path, write=True)
    assert allowed(policy, where.vault / "profile" / "skills.yaml", write=True)  # the extra dir


def test_the_code_repository_opens_only_when_it_is_named_as_an_extra_directory(where):
    opted_in = Locations(code_root=where.code_root, temp=where.temp, extra=(where.code_root,))
    policy = access.build_policy(opted_in)
    assert allowed(policy, where.code_root / "mcp_server" / "server.py", write=False)
    assert not allowed(policy, where.code_root / ".git" / "config", write=False)
    assert not allowed(policy, where.code_root / "private" / "x.json", write=False)


def test_learning_plans_outside_outputs_are_writable_but_not_their_neighbours(where, tmp_path):
    plans = tmp_path / "plans"
    (plans / "2026").mkdir(parents=True)
    elsewhere = Locations(
        code_root=where.code_root,
        temp=where.temp,
        vault=where.vault,
        outputs=where.outputs,
        learning_plans=plans / "2026",
    )
    policy = access.build_policy(elsewhere)
    assert allowed(policy, plans / "2026" / "plan.pdf", write=True)
    assert not allowed(policy, plans / "other" / "plan.pdf", write=True)
