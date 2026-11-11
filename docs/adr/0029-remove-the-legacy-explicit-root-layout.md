# 0029 — Remove the legacy explicit-root layout from the path module and the commands

**Status:** Proposed. A problem statement only; no decision yet, details to be added.

## Context

[ADR 0013](0013-code-and-vault-split-into-two-repos.md) says one module, `paths.py`, decides where
personal data lives. It still carries a second mode from before the split: a caller may pass an
explicit `root`, and any root that is not this checkout is "used as given, in the old project-2
layout". Related leftovers:

- `_LEGACY_PROFILE_DIR` names a `project-2-profile-learning-hub` folder.
- The star-bank path points at `project-1-application-engine/reference/star-bank.md`.
- `--root` options and `args.root or ROOT` defaults in the commands (about seventeen references).

Two ways to locate data means two paths to test, and a reader cannot tell which one is live.

## Options to weigh

- Delete the explicit-root mode; tests use a throwaway vault, which they already do.
- Keep it behind one clearly named function and mark it test-only.

## To decide

Which tests still depend on a root argument, and whether the container's per-file overrides
(`CLAUDE_JOBS_PRIVATE_DIR` and the applications log variable) stay.
