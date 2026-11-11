# 0026 — Setup is one guided path with scripts, and the project says it is pre-1.0

**Status:** Accepted. Written after a clean clone was set up by following the documents exactly,
which showed where a new user gets stuck.

## Context

The setup documents had grown by accretion, and a reader meeting the project for the first time
could not tell what to do. Following them in a clean clone in November 2026 showed:

- **The install steps were written in six places that disagreed.** The README had two overlapping
  sections (one with a diagram that still showed extras that no longer exist), the setup page
  claimed to be "the only place" yet the README repeated it, the MCP README had its own install
  with different extras and no lock file, `GETTING_STARTED.md` and the site page each had their
  own lines, and the header of `requirements-lock.txt` named a fifth variant.
- **`GETTING_STARTED.md` was a command reference**, not a first session. The README's "Try it"
  block ran `jobo` with no install step before it, so pasting it into a new terminal failed.
- **Required and optional steps were interleaved** in one list of eleven, with a one-off
  spreadsheet import (the author's migration) among them. The disk-encryption advice, `gh auth`
  and the git identity came before the demo, which needs none of them.
- **Failure modes a newcomer meets were not covered**: a distro whose Python is too old (Ubuntu
  22.04 ships 3.10 and the project needs 3.11), a missing `python3-venv`, `jobo: command not
  found` in every new terminal because the virtual environment was not activated, and `python -m
  jobomatic` failing outside it.
- **The commit hook blocked every commit when there was no vault**, because one check crashed
  instead of skipping, although the page said only two checks were skipped.
- **Nothing could check a setup.** The "Check that it works" list was seven commands to run by
  eye. Jargon (vault, MCP, extras, editable, hook, ADR) was never defined.
- **The project never said what stage it is at**, so a reader could not tell "finished" from "a
  working draft".

## Decision

1. **One page holds the install steps**: `docs/setup.md`. The README, `GETTING_STARTED.md`, the MCP
   README and the site carry a short quick start that is the same command and a link, never the
   steps. A test keeps the quick-start line identical and every relative link resolving.
2. **Scripts do the work and the page explains.** `scripts/setup.sh` creates the virtual
   environment, installs with the lock file (retrying without it if pip cannot resolve it),
   checks the install and runs a demo smoke test. `scripts/check-setup.sh` is a read-only health
   check that says OK, WARN or FAIL in words. Both are plain bash with no prompts, safe to run
   twice, and they **never run `sudo`, add a package source, create a GitHub repository or push**.
   Where something is missing they print the exact command for the user to run.
3. **Supported scope: the Debian and Ubuntu family**, recognised from `ID` and `ID_LIKE` in
   `/etc/os-release`. It is tested on Zorin OS 18 (Ubuntu 24.04 base); other distros in the family
   are expected to work, and anything else gets a warning, not a refusal. macOS and Windows are out
   of scope for now. The page carries a dated table of each distro's default Python.
4. **The page is ordered by what the reader has**: try it with the demo vault (no personal data),
   then your own vault, then optional extras, then contributors. Required steps never contain an
   optional one. Optional extras are independent and each says "skip for now" and what is lost.
5. **Visuals are text, not screenshots**: a flowchart for choosing a path (with a table that says
   the same, since mermaid does not render everywhere), a folder picture of the two repositories,
   a "what you should see" block after each command taken from real runs with paths generalised,
   and a visible `[n/N]` progress line in the scripts. Screenshots go stale and cannot be tested.
6. **The project says it is pre-1.0.** One standard notice appears in the README, the setup page,
   `GETTING_STARTED.md`, the MCP README and the site, and a short form in the script banner:
   works end to end and is used by its author, but command options, the profile layout and
   document formats can still change, with no migration guarantee, and the vault should be
   committed before updating. The prose says "pre-1.0" because it is precise and does not read as
   "broken"; "beta" would claim wider testing than a single-user tool has had. The package
   classifier says `Development Status :: 3 - Alpha` because that field is for tools and PyPI has
   no pre-1.0 value.
7. **The commit hook works without a vault.** The salary check skips, as the identifier check
   already did, so a contributor with only the code can commit.
8. **Page-count setup recommends one option**, `sudo apt install libreoffice-writer`. The Flatpak
   route in [ADR 0024](0024-resume-page-budget.md) still works through `JOBOMATIC_LIBREOFFICE`; the
   setup page just stops offering a choice a newcomer cannot make.

Problems found while writing this that are architecture, not documentation, are logged as proposed
records [0028](0028-structured-command-results-for-cli-and-mcp.md) to
[0033](0033-python-version-support-and-ci-matrix.md), so they are not lost.

## Consequences

- The scripts and the page are two things to keep in step. `check-setup.sh` is the test of the
  page: if a step is added, the script should check it.
- The Python-by-distro table ages with each release. It is dated, and the script prints advice
  from the detected version, not the table.
- The pre-1.0 notice must be changed when the status changes. One test finds every copy.
- The scripts cannot be run on other distros here. Detection is tested against sample
  `os-release` files; the rest is tested on one machine, and the page says so.
- Not doing a `jobo doctor` command for now: it would need Python code and tests, and a shell
  script runs before the package is installed, which is exactly when a new user needs it.
- Not scripting `sudo` or a Python upgrade: running a stranger's repository as root, or changing
  the system Python, is a bigger step than a setup script should take for the user.
