# 0005 — Container built from code only; personal data reaches it via bind mount

**Status:** Accepted; amended by [0020](0020-mcp-server-for-claude-desktop.md) (the vault, not the repo, is mounted)

## Context

Containerizing with Podman raised a concrete question: personal data
(`Resume_Snapshot.md`, `pluralsight_learning_history.json`, and the built
`outputs/profile-bundle.json` — names, email, phone, career history) needs
to reach the running container, but nothing should risk baking that data
into an image layer that could later be inspected, exported, or (even
accidentally) pushed somewhere. Research into current practice for this
exact shape of problem (single-user, local-only container needing
sensitive files) consistently pointed at bind mounts over dedicated
secret-management tooling — the latter (HashiCorp Vault, cloud secret
managers) is built for multi-host/production/team deployments with
rotation and audit needs, pure overhead for a tool that never leaves one
machine.

## Decision

`.containerignore` excludes the PII-bearing source files (plus `outputs/`,
which covers the built bundle) from the build context entirely — they
never enter an image layer, full stop. The
entire repository is then bind-mounted over `/app` at `podman run` time
(`-v <repo>:/app`), so the running container reads the candidate's real, live
host files directly. The image itself contains only a snapshot of the code
plus installed dependencies (`pip install -e .`, editable — imports
redirect back to the mounted `/app` rather than a frozen copy).

## Consequences

- The image is safe to build, inspect, or hand to someone else without
  exposing any personal data — confirmed empirically (`find` over the bare
  image for these filenames returns nothing).
- Generalizing the same mechanism to *all* data, not just the PII subset,
  answered a second question for free: how do you keep
  `pluralsight_learning_history.json`, `outputs/presence-bundle.json`, and
  `roles/*.json` current without rebuilding? You don't — they're live
  through the same mount. The image only needs rebuilding when
  `pyproject.toml`'s dependencies change.
- No at-rest encryption layer sits on top of this today — deliberately.
  `age` and the 1Password/Bitwarden CLIs were researched and documented as
  options, but judged unnecessary given the file already never enters git
  tracking changes or the image; revisit if that changes.
- `Resume_Snapshot.md` — the one PII file here that's currently
  *tracked in git* rather than gitignored — was found during this same
  piece of work and deliberately left as-is: a separate decision from the
  container's build-time exclusion, not blocked by or blocking it.

## Update (November 2026): the vault is mounted, not the repo

Personal data now lives in the separate private vault repo, so the bind mount carries the vault
and the image carries all of the code. `podman run -i --rm -v <vault>:/vault job-o-matic-mcp`,
with `JOBOMATIC_VAULT=/vault` set in the image. The reasoning above still holds: nothing
personal is in the build context, and the image is safe to inspect. Two things change:

- Code edits are no longer live. The image is rebuilt when the code or its dependencies change.
- `.containerignore` no longer needs to name individual personal files; it keeps `private/`,
  `outputs/` and the applications log as a safety net.
