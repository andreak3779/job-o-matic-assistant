# Getting started

A first session with `jobo`, the job-o-matic command line, followed by a reference for every
command. **Not installed yet?** Do [Part 1 of docs/setup.md](docs/setup.md) first; it takes about 15
minutes and uses no personal data.

> **Pre-1.0 and in active development.** job-o-matic works end to end and is used by its author for a live job search. It is not yet 1.0: command options, the profile file layout and generated-document formats can still change, and there is no migration guarantee. Commit and push your vault before you update.

## At the start of every session

Open a terminal and run these two lines. A new terminal forgets them.

```bash
cd ~/src/job-o-matic-assistant      # the code folder; the examples below start here
source .venv/bin/activate           # puts jobo on your PATH; your prompt starts with (.venv)
```

`jobo: command not found` means the second line was skipped. `python -m jobomatic` does the same
thing as `jobo`, but only with the virtual environment active, because it needs that environment's
Python.

A relative path such as `tests/fixtures/strong-fit-jd.md` starts from the folder you are in
([ADR 0027](docs/adr/0027-relative-paths-resolve-against-the-current-folder.md)). If a file is "not
found", the message shows where it looked. Run from the code folder, or give the full path.

## Your first session

Two tracks. Start with A: it uses an invented person, so every result is predictable. Move to B when
you have your own vault.

### Track A: the demo vault

**1. Use a copy of the demo vault.** Generating documents writes into the vault, and you do not want
that inside your code folder:

```bash
cp -r demo-vault ~/job-o-matic-demo
export JOBOMATIC_VAULT="$HOME/job-o-matic-demo"
```

To start over later, delete `~/job-o-matic-demo` and copy again.

**2. Rate a posting.** `fit-check` compares a posting with the profile by fixed rules, with no AI
guessing, so the same posting always gets the same rating:

```bash
jobo fit-check tests/fixtures/strong-fit-jd.md
```

```text
## Fit Check — Senior Full-Stack .NET Developer at Northgate Insurance Group
...
**Fit Rating: Strong**
All 9 required skills covered (...); 4 nice-to-have(s) present.
```

The ratings, best to worst, are **Strong**, **Good**, **Worth a try**, **Stretch** and **Pass**.

**3. Read the gap analysis.** It lists what matched, what is missing and how to frame the rest:

```bash
jobo gap-analysis tests/fixtures/strong-fit-jd.md
```

It prints a `Wrote <path>` line: the report is a markdown file in the vault's
`outputs/applications/<date>_<company>_<role>/` folder. Open it in any editor, or with
`less <path>`.

**4. Draft the documents.**

```bash
jobo generate-resume tests/fixtures/strong-fit-jd.md
jobo generate-cover-letter tests/fixtures/strong-fit-jd.md
```

```text
Fit Rating: Strong — ...
Logged as drafted (not applied): application <date>_northgate-insurance-group_...
Wrote <vault>/outputs/applications/<date>_northgate-insurance-group_.../resume.docx
```

Open the `.docx` files with LibreOffice or any word processor. They are drafts for you to read and
rewrite. The tool never sends anything.

**5. See the gate say no.** A posting that does not match is refused, and no document is written:

```bash
jobo generate-resume tests/fixtures/data-engineer-jd.md
```

```text
REFUSED: Fit rating is Pass — refusing to generate resume/cover letter.
...
```

It exits with status 2. The checks and which of them you can override are in [The gate](#the-gate).

**6. Keep track.** Generating documents only logs a posting as *drafted*. *Applied* is recorded only
when you say so:

```bash
jobo applications list
jobo applications applied --jd tests/fixtures/strong-fit-jd.md      # only after you really submitted
```

That is the whole loop: rate, read, draft, decide, record.

### Track B: your own vault and a real posting

You need a vault with your profile ([Part 2 of docs/setup.md](docs/setup.md#part-2-your-own-vault))
and `bash scripts/check-setup.sh` showing no FAIL. If you exported the demo vault above, run
`unset JOBOMATIC_VAULT` so your own is found.

**1. Save the posting as a markdown file.** Keep your postings in one folder, outside the code
folder:

```bash
mkdir -p ~/job-postings
nano ~/job-postings/acme-backend.md        # paste the posting, then Ctrl+O, Enter, Ctrl+X
```

The tool reads this shape best: a title, then the company, location and skills. It copes with other
layouts too (see `tests/fixtures/atypical-*`).

```markdown
# Backend Developer

**Company:** Acme Corp
**Location:** Remote (Canada)

## Required Skills
- C#
- SQL Server

## Nice to Have
- Docker
```

**2. Rate it.** `~` is expanded by your shell, so this works from any folder. Check that the first
line shows the right title and company; that tells you it understood the posting:

```bash
jobo fit-check ~/job-postings/acme-backend.md
```

**3. Decide from the rating.**

| Rating | What to do |
| --- | --- |
| **Strong**, **Good** | Go on to step 4. |
| **Worth a try**, **Stretch** | Run `gap-analysis` and read the gaps. Only if you still want to apply, add `--confirm-gaps` to the generate commands. That is your decision, not a default. |
| **Pass** | Stop. A Pass on skills, and a Pass on location, cannot be overridden. |

**4. Draft, read, then submit yourself.**

```bash
jobo generate-resume ~/job-postings/acme-backend.md
jobo generate-cover-letter ~/job-postings/acme-backend.md
```

Read every line of both. Fix anything that is not true or not in your voice. You submit the
application yourself, on the employer's site.

**5. Record it after you submit, then save your vault.**

```bash
jobo applications applied --jd ~/job-postings/acme-backend.md
cd ~/src/job-o-matic-vault && git add -A && git commit -m "Applied to Acme" && git push
```

Pushing the vault keeps the duplicate check right on your other laptop.

---

## Command reference

Run `jobo <command> --help` for every option of a command.

```bash
jobo <command> [options]          # with the virtual environment active
python -m jobomatic <command>     # the same thing, from any folder, with the virtual environment active
```

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
[docs/setup.md](docs/setup.md#page-counts---check-pages).

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
| `docs/setup.md` | Step-by-step setup |

Run `jobo <command> --help` for every option.

MIT licence.
