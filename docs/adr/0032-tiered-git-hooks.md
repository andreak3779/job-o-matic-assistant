# 0032 — Tiered git hooks: a fast check on commit, the full suite on push and in CI

**Status:** Proposed. A problem statement only; no decision yet, details to be added.

## Context

`scripts/hooks/pre-commit` runs the staged-file guard, the private-value scan, ruff, the import
contracts, mypy and the whole test suite on every commit. In a measured run that was about 85
seconds for a one-line documentation change, of which the tests were about a minute. The setup
documents tell people that `git commit --no-verify` exists, which is what a slow hook teaches.
CI repeats the same checks after the push.

## Options to weigh

- On commit: the staged-file guard, the private-value scan, ruff and a syntax check. On push: the
  import contracts, mypy and the tests.
- Run the tests on commit only when a file under `src/` or `tests/` changed.
- Leave it; slow commits are the price of catching a problem before it is committed.

## To decide

Which checks must run before a commit exists (the private-value scan and the staged-file guard do:
a leak is hard to take back) and which can wait for the push.
