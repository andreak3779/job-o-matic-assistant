# 0031 — One canonical location for the skills

**Status:** Proposed. A problem statement only; no decision yet, details to be added.

## Context

The skills live in `skills/`, which the README and `CLAUDE.md` call the source. Claude Code reads
`.claude/skills/<name>`, which are symlinks to `skills/<name>` (24 tracked entries). The MCP server
reads `.claude/skills` (`interfaces/mcp/skill_prompts.py`), and the Dockerfile copies both folders.

So the server depends on the symlink layer, not the canonical folder. Symlinks can be lost when a
repository is downloaded as an archive or copied on a file system that does not keep them, in which
case the prompts would disappear without an obvious error. This has not been checked.

## Options to weigh

- The MCP server reads `skills/` directly; the symlinks exist only for Claude Code.
- A test that fails when a symlink is missing or points somewhere else.
- Leave it, and document that the symlinks must survive.

## To decide

Whether the Dockerfile still needs `.claude/skills` once the server reads `skills/`.
