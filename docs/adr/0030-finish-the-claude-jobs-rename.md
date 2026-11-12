# 0030 — Finish the rename from claude-jobs to job-o-matic

**Status:** Accepted.

## Context

The project is `job-o-matic-assistant`, the package is `jobomatic` and the command is `jobo`, but
the earlier names were still in the tracked code and documents (outside the ADRs, which are not
rewritten):

- `claude-jobs`, the old command, kept as an alias that prints a notice.
- `CLAUDE_JOBS_PRIVATE_DIR`, `CLAUDE_JOBS_APPLICATIONS_LOG` and `CLAUDE_JOBS_ALLOWED_DIRS`, next to
  the `JOBOMATIC_*` variables.
- Docstrings that say "project-1 generator scripts" and a reference to the old `claude-projects`
  checkout in the MCP README.

A reader meets four names for one thing, and the environment variables are part of the public
interface.

What was found when this was investigated (on `main`, 2026-11-12):

- **The variables are read in two source files.** `paths.py` reads the private folder and the
  applications log; `interfaces/mcp/server.py` reads the extra readable directories. The rest of
  the mentions are tests, three setup scripts and the MCP README.
- **The container does not use them.** The `Dockerfile` sets only `JOBOMATIC_VAULT`.
  [ADR 0029](0029-remove-the-legacy-explicit-root-layout.md) says the per-file overrides are used
  "by the container"; that is not so. They are used by the test fixture and by
  `scripts/golden_outputs.py`.
- **No Claude Desktop or Claude Code configuration of the author's uses an old name**
  (checked by name only). That is evidence about one machine and this repository, not proof that
  nobody else sets them.
- **There has never been a release.** The version is `0.1.0`, there are no tags, and the repository
  has been public since 2026-11-10. "Keep the old names for one release" has no starting point.
- **A silently ignored variable moves data.** If `CLAUDE_JOBS_APPLICATIONS_LOG` were simply no
  longer read, the applications log would be written to the vault instead of where the user pointed
  it, with no error. The MCP server's access rules would likewise be built around the wrong
  private folder.
- **The MCP server swallows `VaultError` in one place.** `_locations()` wraps the private-folder and
  applications-log lookups in `_or_none`, so a check placed only inside `paths.private_dir()` would
  be hidden there when no vault is configured.
- **A test checks nothing.** `test_curated_skills_only_need_commands_that_have_a_tool` matches only
  `claude-jobs <command>`, which no skill uses any more, so it matched zero commands. Matching
  `jobo` and `python -m jobomatic` finds 33 uses, all mapped to a tool.

## Decision

1. **Rename the three variables** to `JOBOMATIC_PRIVATE_DIR`, `JOBOMATIC_APPLICATIONS_LOG` and
   `JOBOMATIC_ALLOWED_DIRS`, matching `JOBOMATIC_VAULT`, `JOBOMATIC_CONFIG` and
   `JOBOMATIC_LIBREOFFICE`.
2. **A clean break with a loud failure, not a fallback.** The old names are not read. If one is
   set, the code that would have used it raises a `VaultError` that names the new variable. The
   command line prints it as a one-line `ERROR:` and exits 1; a command returns an `error` result;
   the MCP server raises it on the tool call, including when no vault is configured. There is no
   deprecation period, because there was never a release to deprecate from. The check is one map in
   one function in `paths.py` and is **deleted before 1.0**.
3. **Remove the `claude-jobs` command now**: the `pyproject.toml` entry and `main.deprecated`. An
   existing editable install keeps a `claude-jobs` script that fails with an `ImportError` until the
   project is reinstalled (`bash scripts/setup.sh --recreate`, or `pip install -e .`).
4. **Fix the docstrings and wording** that name the old command or the old checkout. The MCP
   README keeps one note about the old Desktop entry, because it is the only place that tells a
   user with that entry what to delete.
5. **A guard test** fails when an old name appears in a tracked file outside a short allowlist, so
   the rename cannot drift back.

The per-file overrides are renamed, not removed. Removing them would leave two fewer public names,
but the test fixture and `scripts/golden_outputs.py` use them, and that is a separate decision.

## Considered and rejected

- **Accept the old names for one release with a warning.** There is no release, and it adds code
  that has to be removed later.
- **Only fix the docstrings and leave the variables.** Leaves two names for the public variables.
- **Keep a stub `claude-jobs` that says the command was removed.** It avoids the `ImportError` on a
  stale install but leaves permanent residue; the reinstall command is one line.
- **Remove the two per-file overrides.** A different change; see above.
- **A new exception type for the check.** The command line's top-level handler and `guarded()`
  already handle `VaultError`, and the message names the variable.

## Consequences

- Anyone who set an old variable gets an immediate, named error instead of a silent change.
- Old names remain only in the ADRs, in the history documents, in the tripwire and its tests, in
  the MCP README note and in the guard itself.
- The tripwire is a small amount of code with a stated end: it goes before 1.0.

## Follow-ups

- Skill text that says "Project 1" (`primary_learning_plan_generator`) is model-facing prompt text
  and is not changed here.
