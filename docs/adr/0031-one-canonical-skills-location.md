# 0031 — One canonical location for the skills

**Status:** Accepted. Built; see "As built".

## Context

The skills live in `skills/`, which the README and `CLAUDE.md` call the source. Claude Code reads
`.claude/skills/<name>`, which are symlinks to `skills/<name>` (24 tracked entries, all mode
120000). Three presence skills (`update_job_board_profiles`, `update_jobgether_profile`,
`update_pluralsight_profile`) are deliberately not linked, so Claude Code does not offer them; a
fourth link, `part_time_retail_resume_and_cover_letter`, is gitignored and local to one machine.

What was found when this was investigated (on `main`, 2026-11-12):

- **The MCP server is the only reader of the link layer.** `skill_prompts.skills_dir()` returned
  `code_root()/.claude/skills`. The five presence generators already read
  `skills/<name>/SKILL.md`, and `scripts/check_skill_hardcoding.py` scans `skills/`.
- **A lost link stops the whole server, not only the prompts.** `server.py` registers the prompts
  when the module is imported. With a link turned into a text file, `load_skill` raises
  `NotADirectoryError` during that import, so none of the 24 tools start, and the traceback names
  no skill and no symlink. The first draft of this ADR said the prompts "would disappear without an
  obvious error"; that was not checked then, and it understated the failure.
- **Whether links are lost depends on the tool that extracts an archive.** `git archive
  --format=zip` keeps them and `unzip` restores them; Python's `zipfile.extractall` writes each
  one as a text file holding `../../skills/<name>`. The supported route, `git clone` on
  Debian/Ubuntu ([ADR 0026](0026-guided-setup-and-pre-1-0-status.md)), is not affected.
- **The Dockerfile copied both folders.** It already had `COPY skills ./skills`, so
  `COPY .claude/skills` existed only for the server.
- Nothing checked the links, and the setup check did not mention them.

## Decision

1. **The MCP server reads `skills/`.** `skills/` is the one source. `.claude/skills` exists only so
   Claude Code finds the skills.
2. **A test pins the link layer from both sides.** Every tracked entry in `.claude/skills` is a
   symlink to `../../skills/<same name>` whose `SKILL.md` exists, and every skill folder is linked
   unless it is on a short named list of exemptions (the three presence skills). A new skill with
   no link and no exemption fails the test, and so does an exemption that has gained a link.
3. **The Dockerfile no longer copies `.claude/skills`.**
4. **`scripts/check-setup.sh` reports broken skill links** and how to fix them, so a Claude Code
   user on a copy that lost its links is told, instead of finding no skills.
5. **The documents say what is canonical:** `skills/README.md`, the MCP README and the
   `skill_prompts` docstring. ADR 0020's statement that `.claude/skills` is the single source is
   amended here, with a status line there.

## Considered and rejected

- **Leave it and document that the symlinks must survive.** The failure is total and cryptic, and
  the fix is one line.
- **A loader that falls back when a link is a text file.** Reading `skills/` already removes the
  problem for the server; the fallback would be code for a case that no longer exists.
- **Copy the skills into `.claude/skills`, or make `.claude/skills` the source.** Claude Code reads
  only that folder, but copies drift, ADR 0020 says nothing is copied, and `skills/` is the path the
  presence generators and the hardcoding check already use.
- **Ship the skills as package data.** `reference/`, `templates/` and `demo-vault/` are found from
  the checkout through `code_root()`, so a wheel install does not work anyway. A different change.
- **Link the three presence skills now.** Not part of this decision; the exemption list records
  that they are left out on purpose.

## Consequences

- The server no longer depends on symlinks, so a copy without them still runs the tools and the
  prompts; only Claude Code loses the skills, and the setup check says so.
- Adding a skill without a link now fails a test unless it is added to the exemption list, which is
  where the author says "this one is deliberately not offered to Claude Code".
- Making a broken prompt skip itself instead of stopping the server is not done: [ADR 0007](0007-fail-loud-on-malformed-input.md)
  says to fail loudly, and CI loads all nine curated skills, so a malformed one cannot merge.

## Follow-ups

- None required. Linking the presence skills, if wanted, is a one-line change plus removing the
  name from the exemption list.

## As built

- `skill_prompts.skills_dir()` is `code_root()/skills`. `test_the_prompts_come_from_skills_not_from_the_claude_code_links`
  builds the nine prompts from a tree that has no `.claude` folder, and fails against the old path.
- The `Dockerfile` has no `COPY .claude/skills`. The image was built without it and, over stdio
  against the demo vault mounted read-only, listed 9 prompts and 24 tools.
- `tests/test_skill_links.py` checks the 24 tracked links and the three exemptions. Four mutations
  each fail it: a link to another skill, a link turned into a text file, a new skill with no link,
  and an exempt skill that gains a link.
- `scripts/check-setup.sh` counts the tracked links in a clone, and every entry in a copy with no
  `.git`. In a copy extracted with Python's `zipfile` it reports "24 of 24 skill links for Claude
  Code are broken" with the way out, and the server in that copy starts and serves 9 prompts and 24
  tools (before this change it failed at import).
- Not done, as decided: linking the three presence skills; making a broken prompt skip itself.
