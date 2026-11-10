# Privacy

This tool works with one person's career history, contact details and application history. This
page says what exists, where it lives, and what keeps it out of this repository.

This repository is public. It holds code, documentation and a fictional demo vault, and no
personal data. It was published from a fresh, single-commit history so that nothing from the
earlier private working repository's history is exposed. The checks below keep personal data out of
it.

## What personal data exists

| Data | Where it lives |
| --- | --- |
| The profile: identity, contact details, work history, skills, stories | The private vault repo (`profile/`) |
| Learning history (courses, labs, modules) | The vault (`profile/learning/`, `imports/`) |
| The applications log | The vault (`applications/applications.jsonl`) |
| Generated résumés, letters and reports | The vault (`outputs/`) |
| Salary minimums, search constraints, a list of personal terms to keep out of code | The vault (`private/`) |

The code repository holds code, skills, templates, tests and a **fictional** demo vault
(`demo-vault/`). The demo person, employers, email address and phone number are invented, and the
phone number uses the reserved 555-01xx range.

## How it is kept out of this repo

- **Separate repos.** The vault is a different, private repository. The code finds it next to the
  checkout or through the `JOBOMATIC_VAULT` environment variable
  ([ADR 0013](adr/0013-code-and-vault-split-into-two-repos.md)). Tests never use a real vault.
- **Ignore rules.** `.gitignore` excludes `outputs/`, generated `.docx` and `.pdf` files,
  provenance sidecars, and everything in `private/` except `*.example.*` templates.
- **A hook on every commit** (`scripts/hooks/pre-commit`, installed by `scripts/install-hooks.sh`):
  - refuses generated output, `.docx`, caches and non-template `private/` files;
  - runs `scripts/check_private_values.py`, which fails if a private salary minimum or any term from
    the vault's personal-terms list (names, emails, phone numbers, employers, share-link IDs) is
    written in any tracked file;
  - runs the other checks listed in the [README](../README.md#local-pre-commit-hook).
- **Public views.** The text for LinkedIn, GitHub and similar sites comes from a public view of the
  profile that contains only fields marked public in the model
  ([ADR 0018](adr/0018-visibility-declared-in-the-model.md)). A guard scans that text for emails, phone
  numbers, postal codes, social insurance numbers and street addresses before it is printed.
- **Containers.** The container image holds code only. The vault is mounted at run time
  ([ADR 0005](adr/0005-container-data-via-bind-mount.md)), so personal data never enters an image
  layer.
- **Network.** The MCP server speaks stdio only ([ADR 0004](adr/0004-stdio-only-transport.md)).
  The only optional network use is described in [LIMITS.md](LIMITS.md#model-use). Résumé bullets
  and interview stories are marked local-only and are never sent to a cloud model.

CI runs without the vault, so it checks code and architecture rules against the fictional data only.

## What this does not protect against

- Someone with access to the author's machine or the private vault.
- A mistake that bypasses the hook (`git commit --no-verify`, or a machine without the hook
  installed). The hook is a safety net, not access control.
- A private term that is not in the vault's personal-terms list.
- Data at rest is not encrypted beyond what the machine and the private repo provide.

## If you find a problem

If you find personal data in this repository, or a way for it to leak, open a GitHub issue that
describes where it is **without repeating the data**, or use GitHub's private vulnerability
reporting for the repository if it is enabled.
