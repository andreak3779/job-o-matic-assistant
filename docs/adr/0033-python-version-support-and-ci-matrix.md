# 0033 — Which Python versions are supported, and what CI tests

**Status:** Accepted.

## Context

`pyproject.toml` says `requires-python >= 3.11`. CI ran only 3.11. `requirements-lock.txt` was
generated on 3.12, which is also what the author runs. Debian 13 ships 3.13, and some distros that
users meet still ship a version that is too old (Ubuntu 22.04 has 3.10). The first draft of this ADR
said nothing showed whether 3.13 or newer works, and feared that a pinned dependency with no wheel
for a new Python would fail at install. It also said a forgotten subpackage in `pyproject.toml`
would fail in a container.

What was found when this was investigated (2026-11-12):

- **Every check passes on 3.11, 3.12, 3.13 and 3.14.** The whole set (install with the lock as CI
  does, then `pytest`, `ruff`, `lint-imports`, `mypy`) was run in the official `python:X-slim`
  images with Podman, with git added as on a GitHub runner:

  | Python | Install | Tests | ruff, 34 contracts, mypy |
  |---|---|---|---|
  | 3.11 (the floor, with the lock) | ok | 1848 passed, 9 skipped, 2 failed (below) | pass |
  | 3.12 (the author's venv, with the lock) | ok | 1859 passed | pass |
  | 3.13, with the lock | ok | as 3.11 | pass |
  | 3.13, no lock (the newest of everything) | ok | as 3.11 | pass |
  | 3.14, with the lock | ok | as 3.11 | pass |
  | 3.14, no lock (mcp 2.3.0, pydantic 2.14.3, pillow 13.0.0, ...) | ok | as 3.11 | pass |

  Every pin in the lock has a wheel for 3.13 and 3.14, and the newest versions of every
  dependency also work. The same two tests fail on every version, including 3.11.
- **The two failures were a test bug, not a Python one.** `_normalize` in
  `tests/test_command_snapshots.py` replaced the repository path by plain substring, so with the
  checkout at `/app` it also rewrote the `/app` inside `outputs/applications/`. The `Dockerfile` has
  `WORKDIR /app`, and `--build-arg INSTALL_DEV=true` installs pytest there, so the suite failed
  inside the project's own image.
- **The lock was incomplete.** `sqlite-vec` is a core dependency and is installed in the author's
  venv, but `requirements-lock.txt` had no line for it, so CI, the container and `setup.sh`
  installed whatever was newest (0.1.9 at the time). The lock's header says "exact versions", and
  nothing checked that it covers `pyproject.toml`.
- **A forgotten subpackage does not fail in the container.** An unlisted `jobomatic/zz_unlisted/`
  imports fine in an editable install, and the `Dockerfile` uses `pip install -e`. A wheel built from
  `main` has exactly the 18 listed packages. `pyproject.toml` already says only editable installs
  are supported, because the code finds `skills/`, `reference/`, `templates/` and `demo-vault/` next
  to the checkout ([ADR 0031](0031-one-canonical-skills-location.md)). The list and the folders agreed
  at the time; only a wheel would be exposed.
- **`setup.sh` already falls back** to an install without the lock, with a warning, and tries
  `python3, 3.12, 3.13, 3.11, 3.14` in that order.
- **The `main` ruleset requires no status checks** (it blocks deletion, non-fast-forward, creation
  and update), so CI job names are free to change, and a red CI does not block a merge by itself.
  [ADR 0032](0032-tiered-git-hooks.md) calls CI the authority for merging; that is convention, not
  enforcement.

## Decision

1. **Supported: Python 3.11, 3.12, 3.13 and 3.14**, each tested in CI. `requires-python` stays
   `>=3.11` with no upper bound, since a bound would make `pip install` refuse a newer Python with no
   evidence that it fails. The rule for later: support every CPython that is not end-of-life and
   whose full check set is green; add a version when it is released and the dependencies have
   wheels; drop the oldest when it reaches end of life (3.11 in October 2027).
2. **CI is two jobs.** *Lint, contracts and types* run on 3.11 only (ruff and mypy have a fixed
   target version, and the contracts read the source, so none can differ by interpreter). *Tests*
   run in a matrix of the four versions with `fail-fast: false`, so one red version does not hide
   the others.
3. **One lock for all versions.** It installs on all four, and so do the newest versions without
   it, so a lock per version would add files for nothing. `setup.sh` keeps its fallback.
4. **The lock is made complete and kept complete.** `sqlite-vec` is added, and a test checks that
   every dependency and extra in `pyproject.toml` has an exact `==` pin in the lock that satisfies
   the declared range.
5. **The package list stays by hand, and a test compares it with the folders under `src/`**, and
   checks that every data file sits under a `package-data` pattern. Package discovery would change
   how the editable install finds the package, to protect an install type the project does not
   support. The README says plainly that only editable installs are supported.
6. **A test ties the statements together:** the `requires-python` floor, the classifiers and the
   versions in `ci.yml` must agree.
7. **The `Dockerfile` stays on 3.11**, the floor, so the image tests the oldest supported version.
8. **The snapshot test replaces the repository path only as whole path segments**, with a
   regression test that puts the repository at `/app`.

## Considered and rejected

- **Test only 3.11 and say newer versions probably work.** They do, but nothing would say when that
  stops being true.
- **A lock per Python version.** Not needed (see the table).
- **Package discovery** instead of the list. See Decision 5.
- **An upper bound on `requires-python`.** See Decision 1.
- **Run mypy and the contracts on every version.** They cannot differ, so it costs time and finds
  nothing.
- **Allow a version's job to fail** so that a red one never shows. A job that is red for a reason
  outside the repository is reported, not hidden.

## Consequences

- CI runs five jobs of about a minute each, in parallel (free on a public repository).
- A new Python release is a one-line change to the matrix and to the classifiers, and the drift test
  fails if only one of them is edited.
- The evidence for 3.13 and 3.14 is the official Python image, not Debian's own `python3`, which was
  not run; the documents say so. GitHub's runners are the second proof, and the pull request that
  introduced the matrix is where it ran.
- Nine tests are skipped in the container (LibreOffice and similar), as in CI; "tested on X" excludes
  them.

## Follow-ups

- Making CI a required check on `main` is a GitHub setting and is left to the repository owner.
- Migrating `(str, Enum)` to `StrEnum`, which the ruff comment mentions, is separate.
