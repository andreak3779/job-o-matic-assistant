# 0013 — Code and personal data live in two repos

**Status:** Accepted

## Context

`claude-projects` holds both the application code and the data it runs on:
career facts, a resume snapshot, salary limits, an applications log, and
every generated document. Keeping the repo private was the only thing
standing between that data and the public. The plan is to share the code
as a portfolio piece, so the data can no longer travel with it, and git
history can't be scrubbed reliably after the fact.

## Decision

Split into two repos:

- **`job-o-matic-assistant`** holds code, templates, skills, ADRs and a
  fictional `demo-vault/`. It starts with a clean history and is made
  public once it is polished.
- **`job-o-matic-vault`** is a private GitHub repo holding profile facts,
  private limits, the applications log, imports, and generated outputs.

The code finds the vault through one module, `paths.py`, in this order:
`$JOBOMATIC_VAULT`, then `~/.config/job-o-matic/config.toml`, then a
sibling `../job-o-matic-vault`. A directory only counts as a vault if it
holds a `.jobomatic.toml` marker; otherwise everything fails loudly
(ADR [0007](0007-fail-loud-on-malformed-input.md)). Tests and `jobo demo`
use `demo-vault/`.

A tree-wide PII scan reads its values (name, contact details, salary
numbers, company names) from the vault at run time, so the scan itself
holds no personal data. It runs in the pre-commit hook and in CI.

## Consequences

- The code repo can go public without a history rewrite, because the new
  repo starts from one scrubbed commit. The earlier history stays in the
  archived `claude-projects` repo.
- Two repos to keep in sync and back up. The vault is a private GitHub repo
  and needs two-factor authentication and no CI or third-party apps.
- Docker/Podman images mount the vault instead of the code repo
  (supersedes the data path in ADR [0005](0005-container-data-via-bind-mount.md)).
- Skills and docs can't name the candidate; they say "the candidate" and
  read the name from the vault.
