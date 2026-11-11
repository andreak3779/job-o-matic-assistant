# 0030 — Finish the rename from claude-jobs to job-o-matic

**Status:** Proposed. A problem statement only; no decision yet, details to be added.

## Context

The project is `job-o-matic-assistant`, the package is `jobomatic` and the command is `jobo`, but
the earlier names are still in the tracked code and documents (outside the ADRs, which are not
rewritten):

- `claude-jobs`, the old command, kept as an alias that prints a notice (about eleven files).
- `CLAUDE_JOBS_PRIVATE_DIR`, `CLAUDE_JOBS_APPLICATIONS_LOG` and `CLAUDE_JOBS_ALLOWED_DIRS` (about
  twelve files), next to the `JOBOMATIC_*` variables.
- Docstrings that say "project-1 generator scripts" and a reference to the old `claude-projects`
  checkout in the MCP README.

A reader meets four names for one thing, and the environment variables are part of the public
interface.

## Options to weigh

- Rename the variables, accept the old names for one release with a warning, then remove them.
- Remove the `claude-jobs` alias on a stated date.
- Only fix the docstrings and leave the variables.

## To decide

Whether anyone besides the author depends on the old names (the container and Claude Desktop
config do), and the removal date. Pre-1.0, so a clean break is allowed.
