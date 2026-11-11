# 0033 — Which Python versions are supported, and what CI tests

**Status:** Proposed. A problem statement only; no decision yet, details to be added.

## Context

`pyproject.toml` says `requires-python >= 3.11`. CI runs only 3.11. `requirements-lock.txt` was
generated on 3.12, which is also what the author runs. Debian 13 ships 3.13, and some distros that
users meet still ship a version that is too old (Ubuntu 22.04 has 3.10). Nothing says whether 3.13
or newer works, and a pinned dependency with no wheel for a new Python would fail at install.

Separately, `pyproject.toml` lists the packages by hand, and a comment warns that new subpackages
must be added there. A forgotten one works in an editable install and fails in a container or any
other install.

## Options to weigh

- Test 3.11, 3.12 and 3.13 in CI, and say which are supported.
- Keep the lock for one version and install without it elsewhere.
- Use package discovery so a new subpackage cannot be forgotten.

## To decide

The supported range, whether the lock is per-version, and whether a test should compare the package
list against the folders under `src/`.
