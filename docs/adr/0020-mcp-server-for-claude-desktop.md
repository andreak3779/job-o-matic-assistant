# 0020 — The MCP server for Claude Desktop: a written access policy, evidence without private prose, skills as prompts

**Status:** Accepted

## Context

The MCP server (now `src/jobomatic/interfaces/mcp/server.py`) wraps the CLI as tools so Claude Desktop can run the
toolkit without a terminal. Three things needed deciding:

1. Which files a client may reach. Every path a client passes in is untrusted: a pasted job
   posting can carry text that steers a tool call. The rules were four functions in `server.py`
   that read global state, so they could only be tested through the whole server, and they let a
   client read the entire code repository.
2. Whether the new `search_evidence` tool may return resume bullets and interview stories. ADR
   [0019](0019-retrieval-module-and-sqlite-index.md) marks them `local_only` so they never go in a
   prompt sent to a cloud model, and a tool result goes to the model Claude Desktop talks to.
3. How Desktop gets the workflows that Claude Code gets from `.claude/skills`.

Claude Desktop was also still registered against the archived pre-rearchitecture checkout.

## Decision

- **The access policy is a pure module**, `mcp_server/access.py`, written by the author and
  reviewed. `resolve(value, roots, denied)` decides one path and `build_policy(locations)` decides
  the three lists. The server builds a `Locations` from `jobomatic.paths` (the only place that knows
  where data lives) and passes it in. Paths are resolved first, so `..` and symlinks cannot escape.
- **Readable:** the vault, the temp directory and `CLAUDE_JOBS_ALLOWED_DIRS`. **Writable:** vault
  `outputs/`, the learning-plans folder, `profile/stories.yaml`, temp and the extra directories.
  **Never:** the vault `private/` folder, the applications log, and any `.git`. The code repository
  is no longer readable: a job description or an output never lives there.
- **`search_evidence` searches courses, labs, Microsoft Learn items and projects only.** Resume
  bullets and interview stories are not searched through MCP. `profile_summary` returns the public
  view only (no contact details, nothing marked private).
- **Skills become MCP prompts**, not copies. `.claude/skills/<name>/SKILL.md` stays the single
  source; `mcp_server/skill_prompts.py` serves a curated nine behind a preamble that maps each CLI
  command to the tool that replaces it. A test fails if a listed skill needs a command with no tool.
  Skills that need a shell or file import stay Claude Code only.
- **The server is named `job-o-matic`.** The CLI is `jobo`; the old `claude-jobs` name survives only as a deprecated alias.
- **The container mounts the vault** (ADR [0005](0005-container-data-via-bind-mount.md), amended).

## Consequences

- The privacy boundary for Desktop is about 60 lines that can be read and tested alone, with
  contract tests for traversal, symlinks, sibling-prefix names, `.git`, and unreadable user homes.
- Desktop cannot cite resume bullets or stories as evidence. That is deliberate, and it costs some
  recall: the best evidence for a skill is often a resume bullet. The same search is available
  locally in Claude Code through the CLI, which does include them.
- Generation still happens locally, but generated documents (and so resume text) come back to the
  client as attachments, as they did before. This ADR does not change that.
- Dropping the code repository from the readable roots could surprise anyone who kept job
  descriptions inside it. The error names `CLAUDE_JOBS_ALLOWED_DIRS`.
- Desktop prompts do not have the skills that need a shell. Adding a tool for an importer would
  be a small follow-up, with its own access review.
- The image must be rebuilt when code changes, since the code is no longer a live mount.
