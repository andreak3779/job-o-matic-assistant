# 0032 — Tiered git hooks: a fast check on commit, the full suite on push and in CI

**Status:** Accepted. Built; see "As built".

## Context

`scripts/hooks/pre-commit` ran the staged-file guard, the private-value scan, ruff, the import
contracts, mypy and the whole test suite on every commit. The first draft of this ADR measured
about 85 seconds for a one-line documentation change and proposed moving the import contracts and
mypy to push. The setup documents tell people that `git commit --no-verify` exists, which is what a
slow hook teaches. CI repeats the code checks after the push.

What was found when each step was timed (on `main`, 2026-11-12, 1805 tests):

| Step | Time |
|---|---|
| staged-file guard, byte-compile, `ruff check`, `ruff format --check` | 0.3 s together |
| `check_skill_hardcoding.py`, `profile validate` | 1.5 s and 1.4 s |
| `lint-imports` and `mypy src` | 0.4 s and 0.5 s |
| `check_private_values.py` | **16.9 s** |
| `pytest tests` | **82 s** |

- **The contracts and mypy are not the problem.** Moving them to push would save about 1 second of
  about 103.
- **The private-value scan is.** It ran 377,692 regex searches (every line against every category).
  Each term carried its own lookbehind alternatives, which stops the regex engine skipping ahead.
  With the lookarounds written once around the whole alternation, the same scan took about 1.3
  seconds on the real tree.
- **The tests take 78 s of test time.** Two tests in `test_pagefit.py` drive the real LibreOffice
  and take 17 s; about 16 s is the autouse fixture that copies the demo vault for every test; the
  rest is a flat spread. `pytest-xdist` with four workers took the suite from 82 s to 61 s, which is
  not a fix and adds a pinned dependency.
- **CI has no vault.** It runs ruff, `lint-imports`, mypy and pytest (about a minute). It does not
  run the staged-file guard, the private-value scan, `check_skill_hardcoding.py` or `profile
  validate`, so those can only ever run on the author's machine.
- **A change to a document can fail a test.** `test_docs.py` checks every Markdown link,
  `test_old_names_are_gone.py` ([ADR 0030](0030-finish-the-claude-jobs-rename.md)) scans every tracked file,
  `test_skill_links.py` ([ADR 0031](0031-one-canonical-skills-location.md)) checks `.claude/skills`, and
  the skill-text tests read `skills/`. Running the tests only when `src/` or `tests/` changed would
  let those through.
- **The leak becomes irreversible at the push.** The repository is public. A leaked value can be
  taken back until it is pushed. The commit hook checks staged paths and tracked files, and the scan
  is case-sensitive for employers and identifiers. The audit that was run by hand before each push
  reads only the added lines of the branch and is case-insensitive for every term. That manual step
  was skipped once, and the branch was wrongly reported as clean.
- `scripts/install-hooks.sh` points `core.hooksPath` at the tracked `scripts/hooks/`, so a new
  `pre-push` file there is active on every machine that already has the commit hook.

## Decision

1. **Three tiers.** *Commit*: every check that is not the test suite, about 6 seconds. *Push*: the
   full test suite and a leak audit of the commits being pushed. *CI*: unchanged, and the authority
   for merging.
2. **The private-value scan is made fast without changing what it finds**, by writing the
   lookarounds once around the alternation. This is what lets every non-test check, the leak scan
   included, stay on commit, where the leak scan must run.
3. **The commit tier keeps the import contracts and mypy** (about 1 second together). Moving them to
   push would save almost nothing, and an import violation is cheapest to fix in the commit that
   caused it.
4. **A `pre-push` hook** runs the leak audit of the pushed range (the added lines, every term,
   case-insensitive) and then the full suite. It does nothing for a branch deletion, handles a new
   branch (no remote commit yet), skips the audit with a clear line when there is no vault, and warns
   when the working tree has uncommitted changes, because the tests run on the working tree and not
   on the commit being pushed.
5. **The documents say what runs where.** `--no-verify` is reworded: skipping the commit hook is
   cheap to undo, skipping the push hook is not, and CI cannot catch a leak.

## Considered and rejected

- **Leave it.** A commit of about 100 seconds teaches `--no-verify`.
- **The path filter** (run the tests only when `src/` or `tests/` changed). Unsafe, for the reason
  above.
- **Run the suite in parallel.** 82 s to 61 s, and a new pinned dependency.
- **Keep the suite on commit for commits that touch code.** It keeps every commit green but leaves
  code commits at about 85 seconds. Not chosen.
- **Move every check to CI.** CI has no vault, so the leak checks cannot run there
  ([ADR 0013](0013-code-and-vault-split-into-two-repos.md)).

## Consequences

- A commit can now contain a failing test. The push hook and CI catch it, but a rebase merge puts
  every commit of a branch on `main`, so a red commit that a later commit fixes stays in history. The
  suite is no longer run for each commit; it is run before the push and in CI.
- The push hook takes about as long as the suite (about 80 seconds), once per push instead of once
  per commit.
- The leak audit at push also covers commits made with `--no-verify`, on another machine, or before
  the hook existed. `--no-verify` on the push still skips it, and nothing else backstops it.

## Follow-ups

- Parallel tests, the per-test vault copy (about 16 seconds) and marking the two LibreOffice tests
  are measured above and left for later.

## As built

Measured on the same machine as the table in Context (1857 tests now):

| | Before | After |
|---|---|---|
| `check_private_values.py` | 16.9 s | 1.8 s |
| The commit hook alone (`bash scripts/hooks/pre-commit`) | about 103 s | 5.6 s (twice) |
| A real `git commit` of a code and test change | about 100 s | 6.3 s |
| The push hook | none | the audit (about 1 s) plus the suite, 82 to 89 s |

- **The scan.** `privacy/scan.py::_compile` writes the boundary tests once around the literal terms.
  `tests/test_pii_scan_equivalence.py` keeps the old pattern as the reference and compares both on a
  table of 42 awkward lines and a seeded fuzz of 4,000 lines per category; four mutations of the new
  pattern (a dropped trailing boundary, a dropped `\n` alternative, boundary-less phone terms, a
  dropped leading boundary) each fail it. On the real terms with 520 planted lines (376 findings)
  both forms report the same findings, 17.0 s against 1.1 s; the real tree has none.
- **The audit.** `jobomatic/privacy/diff_audit.py` holds the pure functions (added lines with their
  line numbers, matching, the pre-push input, a commit's author, committer and message);
  `scripts/check_pushed_commits.py` runs `git log -p` per commit, not the net change, so a value
  added in one commit and removed in the next is still caught, and it audits the author, committer
  and message as well. A range can be audited by hand with `--range`. Against the last 30 commits of
  `main` it names the commits that carry the author's personal email (two where GitHub's rebase
  merge set it as committer), as `commit <sha>:line`, with no value printed.
- **Tests.** The pure functions are tested directly; the script is tested against throwaway
  repositories with a bare remote and a fake vault (new branch, update, deletion, a remote commit the
  clone does not have, no base branch, no vault, no terms file, a broken terms file, a bad range).
  Three mutations (net diff instead of per-commit patches, ignoring author and message, treating a
  deletion as an update) each fail them. The hooks are checked to be executable bash that parses.
- **The push hook, end to end.** Run through `git push` from a scratch clone with a scratch bare remote
  and a throwaway vault: a clean new branch passes; an added line with a fake employer in different
  case is blocked and prints only `b.md:1 (employers)`, and the remote is unchanged; a branch
  deletion runs no checks; a failing test blocks; a dirty tree prints the note.
- **The first real run found two things.** The suite had passed on the commit that added the audit,
  because the guard test of ADR 0030 reads tracked files and the new test file was not tracked yet;
  the push hook failed on it, which is the cost this ADR accepts (a commit can be red until the
  push), and it was fixed before anything was pushed. And a renamed variable from ADR 0030 raises
  the error that `check_private_values.py` and the new script read as "no vault": a stale
  `CLAUDE_JOBS_PRIVATE_DIR` would have quietly switched the leak checks off. Both scripts now call
  `reject_retired_variables()` first and fail; each has a test, and removing the call fails it.
- Not done, as decided: parallel tests, the per-test vault copy, marking the two LibreOffice tests,
  adding the vault-dependent checks to CI.
