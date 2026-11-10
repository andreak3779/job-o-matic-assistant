# Getting started

How to run `jobo`, the job-o-matic command line. This page is a command reference. It assumes
the package is installed; for first-time setup (virtual environment, extras, vault, MCP server,
pre-commit hook) follow [docs/new-laptop-setup.md](docs/new-laptop-setup.md) or the
[README](README.md#setup). Install steps are kept there only, so the two cannot drift apart.

```bash
jobo <command> [options]          # with the virtual environment on your PATH
python -m jobomatic <command>     # the same thing, from anywhere the package is installed
```

`claude-jobs` still works as an alias and prints a notice; it will be removed.

## Before the first command

- Python 3.11 or later, installed with `pip install -c requirements-lock.txt -e ".[mcp,parser,pdf,dev,lint]"`
  (drop `mcp` if you will not use Claude Desktop, and `dev,lint` if you will not run the checks).
- A **vault**: the private repo with your profile and outputs. The code finds it through
  `JOBOMATIC_VAULT`, then `~/.config/job-o-matic/config.toml`, then a sibling `../job-o-matic-vault`.
  For a trial run use the fictional one: `export JOBOMATIC_VAULT=$PWD/demo-vault`. Without a vault
  every command stops with `ERROR: No vault found` and says how to set one.
- `jobo profile validate` should print no errors.
- Optional, for `--check-pages`: `pdfinfo` and a working LibreOffice (see below).

## Rate a posting

| Command | What it does |
| --- | --- |
| `fit-check <jd>` | Inline fit rating and skills table |
| `gap-analysis <jd> [--out PATH]` | Markdown gap analysis for the posting |
| `evidence <jd-or-skill>` | Closest course, project and résumé evidence for a skill or posting (advisory) |
| `constraints show` | Your private salary minimums, or a note that none are set |

`<jd>` is the path to a markdown file containing the posting.

## Make application documents

| Command | What it makes |
| --- | --- |
| `generate-resume <jd>` | Tailored résumé (DOCX) |
| `generate-cover-letter <jd>` | Tailored cover letter (DOCX) |
| `generate-job-site <jd>` | Short job-site letter (text; `.docx` if `--out` ends in it) |
| `generate-cold-call [<jd>] [--recruiter-name N] [--role-type T]` | Short cold-outreach letter (DOCX); the posting is optional |
| `generate-thank-you [<jd>] --discussion-point "..." --interviewer "..."` | Post-interview thank-you (DOCX); repeat the options for more than one |
| `interview-prep <jd>` | Role-specific interview prep (DOCX) |
| `generate-profile-resume` / `generate-profile-cover-letter` | Platform résumé and cover-letter template, no posting needed |
| `application-dir <jd>` | Print (and create) the folder that holds this posting's documents |

Options common to these: `--company NAME` overrides the company, and `--out PATH` overrides the
default location (a dated folder under the vault's `outputs/applications/`).

### Page limits

A résumé is at most 2 pages and a cover letter exactly 1. `generate-resume` and
`generate-profile-resume` trim themselves to two pages (self-directed work loses bullets first, then
the oldest role; your three newest roles keep at least two) and refuse if they cannot fit. That is
an estimate. To measure the real count, add `--check-pages` to `generate-resume`,
`generate-cover-letter`, `generate-profile-resume` or `render`: it converts the file with LibreOffice
and exits 1 (keeping the file) when a limit is broken.

```bash
jobo generate-resume posting.md --check-pages          # prints "Pages: 2"
export JOBOMATIC_LIBREOFFICE=flatpak                    # use the Flatpak build (or a command or path)
```

It needs `pdfinfo` and one working LibreOffice: the Flatpak, or `sudo apt install libreoffice-writer`
(the `libreoffice-common` package alone cannot open a DOCX). Setup and troubleshooting are in
[docs/new-laptop-setup.md](docs/new-laptop-setup.md#9-optional-page-counts---check-pages).

### The gate

Résumé and cover-letter generation checks the posting first and **refuses** (exit status 2, message
starting `REFUSED:`) when:

| Check | Refused when | You can override with |
| --- | --- | --- |
| Location | The role is outside your location rules | Nothing |
| Fit | Skills rate **Pass** | Nothing |
| Fit | Rating is **Stretch** or **Worth a try** | `--confirm-gaps` |
| Duplicate | You already applied to this posting recently | `--confirm-reapply` |
| Pay | Stated pay is below your minimum | `--confirm-below-minimum` |

An override is your decision, so use it only after reading the refusal. The job-site letter checks location and duplicates only (`--confirm-reapply`); the cold-outreach
letter checks location when you give it a posting.

## Track applications

```bash
jobo applications check <jd>      # have I seen this posting before?
jobo applications add <jd>        # log it as drafted
jobo applications applied --id <id>   # or --jd <jd>: you submitted it (always explicit, never automatic)
jobo applications status <id> <status>   # drafted, applied, phone_screen, technical, offer, rejected, withdrawn
jobo applications list
jobo applications import-csv tracker.csv
```

## Profile and learning

| Command | What it does |
| --- | --- |
| `profile validate` | Load the profile and run its consistency checks, including that no list item has unbalanced brackets (a sign a list was cut at a comma) |
| `profile show full\|facts\|contact\|section "<name>" [--public]` | Print the profile or a slice of it |
| `profile schema` | Print the JSON Schema generated from the profile models |
| `learning import <export>` | Preview an import; add `--apply` to write it |
| `learning list` / `lookup <title>` / `stats` | Browse imported items; totals and hours are computed, never typed |
| `learning summarize` / `enrich` / `set-url` | Fill in summaries and links |
| `index build` | Embed new or changed evidence (needs a local Ollama server) |
| `search "<phrase>"` | Find evidence for a phrase; `--keyword-only` needs no server |

## Online presence

`generate-linkedin`, `generate-github`, `generate-jobgether`, `generate-job-board` and
`generate-pluralsight` each write paste-ready copy from the public view of the profile, by default
to the vault's `outputs/profiles/<platform>/<date>.md`. Pass `--out PATH` to choose.

## Learning plans and other renderers

```bash
jobo generate-learning-plan profile/roles/<role>.json   # run from the vault, or give the full path
jobo render schema resume                                # print the JSON shape for a content file
jobo render resume content.json [--out PATH] [--check-pages]   # render a content file to DOCX
```

Copy `templates/roles/_example.json` to start a role config.

## Exit status

| Code | Meaning |
| --- | --- |
| `0` | Done |
| `1` | A validation or runtime error, no vault found, or a `--check-pages` limit broken |
| `2` | The gate refused (see the message for the override, if there is one) |

## Where things are

| Path | What |
| --- | --- |
| `src/jobomatic/interfaces/cli/main.py` | The command dispatcher |
| `skills/` | The Claude Code workflows that run these commands ([skills/README.md](skills/README.md)) |
| `docs/architecture.md` | How the modules fit together |
| `docs/adr/` | Why each decision was made |
| `docs/new-laptop-setup.md` | Step-by-step setup |

Run `jobo <command> --help` for every option.

MIT licence.
