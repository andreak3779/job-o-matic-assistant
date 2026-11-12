# 0032 — Tiered git hooks: a fast check on commit, the full suite on push and in CI

**Status:** Accepted.

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
