# 0027 — Relative paths resolve against the current folder

**Status:** Accepted. This records a behaviour that was already there and tested, after it was
questioned and after a stale sentence in the MCP README said otherwise.

## Context

`jobo fit-check tests/fixtures/strong-fit-jd.md` works from the repository root and fails from
`docs/` with `JD file not found`. A new user hits this as soon as they leave the folder the
examples assume, and the message says neither which file it looked for nor from where. The MCP
README claimed paths are "anchored to this file's location, not the process's working directory,
same as the CLI". Neither is true: every path argument is an `argparse` `type=Path`, and the MCP
access check resolves with `Path.resolve()`. A test already states the rule,
`test_a_relative_path_is_resolved_against_the_current_directory`.

Anchoring relative paths to the repository root was considered, since it would make the examples
work from anywhere.

## Decision

Both the command line and the MCP server resolve a relative path against the **current folder**,
the way every other command-line tool does. The fix is the message and the documents, not the rule:

- `require_path` and the other missing-file errors name the path they looked for, the absolute
  path it resolved to and the current folder, and say what to do: run from the folder that holds
  the file, or give the full path.
- The documents tell new users to run the examples from the repository root, and to keep their own
  postings in a folder such as `~/job-postings/` and give the full path.
- The MCP README is corrected, and still recommends absolute paths for MCP clients, which have no
  reliable current folder.

## Consequences

- **Rejected: anchor to the repository root.** `--out report.md` would write inside the code
  checkout. The design keeps personal documents out of it ([ADR 0013](0013-code-and-vault-split-into-two-repos.md),
  [0015](0015-single-outputs-hierarchy.md)), and `.gitignore` covers `*.docx`, `*.pdf` and
  `outputs/` but not the `.md` and `.txt` files that `gap-analysis` and `generate-job-site` write.
  It also breaks tab-completion (`./acme.md` would silently look in the repository, and a
  same-named file there would be used), needs a custom path type at about twenty call sites, and
  depends on finding the repository root, which only works for an editable install.
- **Rejected: fall back to the repository root when the file is not found.** It makes the examples
  work from anywhere, but it is a second rule to explain and test, and it can pick the wrong file
  without saying so.
- The examples in the documents assume the repository root, and say so.
- A typo still fails loudly ([ADR 0007](0007-fail-loud-on-malformed-input.md)); the message is now
  enough to fix it without reading the source.
