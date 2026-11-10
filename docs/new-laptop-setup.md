# Installing job-o-matic

An ordered checklist for a first install, a second laptop, or a clean reinstall. Allow about 15
minutes. The steps were run from a fresh clone: the install takes under a minute, and the 1,300
tests pass on the fictional demo vault.

This page is the **only** place the install steps are written in full, so the other docs cannot
drift from it. For what each command does once you are set up, see
[GETTING_STARTED.md](../GETTING_STARTED.md).

## What you are installing

Two folders, side by side:

| Folder | What | Visibility |
| --- | --- | --- |
| `job-o-matic-assistant/` | The code: commands, the fit engine, the MCP server, the skills, a fictional `demo-vault/` | Can be public |
| `job-o-matic-vault/` | **Your** data: profile YAML, applications log, learning history, private limits such as salary minimums, generated documents | **Private. Never make it public** |

The code finds the vault by itself when it sits next to the checkout. Nothing about you is ever
stored in the code folder.

**Just want to look around?** Do steps 1 to 5 and stop. The demo vault is a fictional candidate, so
you need no personal data. Go on to step 6 when you want your own.

## Before you start: protect the machine

The vault holds your contact details, work history and education dates. Two-factor authentication
protects your GitHub account but not a clone that is already on disk:

1. **Disk encryption is on.** On Linux, run `lsblk -f` and look for `crypto_LUKS` on the main
   partition. Enable it before cloning; it is far easier on a fresh install.
2. **A screen lock and a login password.**
3. **Never move the vault through email, chat apps or shared cloud folders.** Use `git clone`.

## Steps

### 1. Install the system tools

Debian and Ubuntu:

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-pip gh poppler-utils
python3 --version   # must be 3.11 or newer
```

`poppler-utils` provides `pdfinfo`, used only by the optional page check (step 9). macOS and other
distros: install the same things with your package manager.

### 2. Sign in to GitHub and set your git identity

```bash
gh auth login        # choose GitHub.com, then HTTPS or SSH, and follow the prompts
git config --global user.name  "Your Name"
git config --global user.email "<id>+<username>@users.noreply.github.com"
```

Use your GitHub **noreply** address (Settings, Emails). Commit metadata is public once the code
repo is, and it keeps your real address out of it. Use the same identity on every machine.

### 3. Clone the code

```bash
mkdir -p ~/src && cd ~/src
git clone https://github.com/andreak3779/job-o-matic-assistant.git
cd job-o-matic-assistant
```

Keep it somewhere ordinary such as `~/src`, not under `/tmp`: the MCP server may write to the
temp directory, and three of its safety tests skip themselves when the checkout is inside it.

### 4. Create the virtual environment and install

```bash
python3 -m venv .venv
.venv/bin/pip install -c requirements-lock.txt -e ".[mcp,parser,pdf,dev,lint]"
.venv/bin/python -c "import docx, bs4, yaml, jsonschema, reportlab, mcp; print('deps OK')"
```

- `-e` (editable) is required. The package lives under `src/` and is found through the editable
  install; without it every command fails with `ModuleNotFoundError`.
- `-c requirements-lock.txt` pins the exact versions the repo is tested with (generated on Python
  3.12). If pip cannot resolve it on an older Python, drop that flag.
- The extras: `parser` reads the Pluralsight and Microsoft Learn pages you save, `pdf` makes
  learning-plan PDFs, `mcp` is the Claude Desktop server (skip it if you will not use that),
  `dev` and `lint` are pytest, ruff, mypy and import-linter for the checks and the commit hook.
- Put `jobo` on your PATH with `source .venv/bin/activate`, or run `.venv/bin/jobo`. The same
  commands work as `python -m jobomatic <command>`.

### 5. Try it on the demo vault

```bash
export JOBOMATIC_VAULT=$PWD/demo-vault
jobo profile validate                                      # [OK] Profile valid ...
jobo fit-check tests/fixtures/strong-fit-jd.md             # rating: Strong
jobo generate-resume tests/fixtures/data-engineer-jd.md    # refused, exit status 2
```

The refusal is the point: skills rated Pass cannot be confirmed past. A few `[WARNING]` lines from
`profile validate` about counts in the fictional text are expected. Without a vault the commands
stop with `ERROR: No vault found` and say how to set one; that is the next step.

### 6. Your own vault

The code looks for a vault in this order: `$JOBOMATIC_VAULT`, then `vault = "/path"` in
`~/.config/job-o-matic/config.toml`, then a folder named `job-o-matic-vault` next to the checkout.
A folder only counts as a vault if it holds a `.jobomatic.toml` file.

**On a second laptop** (you already have a vault repo):

```bash
cd ~/src
git clone https://github.com/<you>/job-o-matic-vault.git
unset JOBOMATIC_VAULT          # the sibling folder is found by itself
cd job-o-matic-assistant && jobo profile validate
```

**Starting from nothing:** copy the demo vault as a template, then replace its fictional content
with yours. Make it a **private** repo, never a public one:

```bash
cp -r demo-vault ../job-o-matic-vault
cd ../job-o-matic-vault
git init && git add -A && git commit -m "Start my vault"
gh repo create job-o-matic-vault --private --source=. --push
```

The profile is YAML in `profile/` (identity, roles, skills, projects, certifications, education,
stories). Edit it by hand, or with Claude and then check it; there is no build step. Run
`jobo profile validate` after every change: it reports what is wrong and warns when counts written
in the text no longer match the imported learning data.

**Private limits.** Salary minimums live in the vault's `private/search-constraints.json` (a
template is in `private/search-constraints.example.json` here). Amounts are CAD and either key may
be left out; without the file the salary screen is skipped.

```bash
jobo constraints show        # prints your minimums, or says none are set
```

Because it is the vault's private repo, the file travels with `git pull`. Do not copy it into the
code repo: a hook blocks that and blocks any minimum retyped in a tracked file.

### 7. Turn on the pre-commit hook

```bash
bash scripts/install-hooks.sh
```

This points `core.hooksPath` at the tracked `scripts/hooks` folder, so the hook is always the
current one. On every commit it blocks generated or private files, scans for your private values
(read from the vault's `private/pii-terms.json`), byte-compiles, runs ruff, the import contracts,
mypy, `profile validate` and the tests (about a minute). With no vault it skips the two checks that
need one.

### 8. Optional: connect Claude Code and Claude Desktop

**Claude Code.** `.mcp.json` uses a path relative to the repo (`.venv/bin/python3`), so it works
on any machine if the virtual environment is at `.venv/` and you open Claude Code **from the repo
root**. Approve the `claude-jobs` server the first time it asks.

**Claude Desktop.** Its config, `~/.config/Claude/claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/`), holds absolute paths for this machine and is never
synced. Follow
[Wire up Claude Desktop](../src/jobomatic/interfaces/mcp/README.md#wire-up-claude-desktop), then
restart Desktop: it only reads the file on startup. The server finds your vault the same way the
command line does; add `"env": {"JOBOMATIC_VAULT": "/path/to/job-o-matic-vault"}` to pin it.

### 9. Optional: page counts (`--check-pages`)

A resume must be at most 2 pages and a cover letter exactly 1. `generate-resume` trims itself to
two pages by an estimate; `--check-pages` measures the real count by converting the file with
LibreOffice. It works on `generate-resume`, `generate-cover-letter`, `generate-profile-resume` and
`render`, and exits 1 (keeping the file) when a limit is broken:

```bash
jobo generate-resume posting.md --check-pages        # Pages: 2
jobo render resume content.json --out r.docx --check-pages
```

It needs `pdfinfo` (step 1) and **one working LibreOffice**. Pick either:

- **Flatpak** (what the author uses):
  ```bash
  sudo apt install flatpak
  flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
  flatpak install flathub org.libreoffice.LibreOffice
  export JOBOMATIC_LIBREOFFICE=flatpak      # put this line in ~/.bashrc
  ```
- **The distro package:** `sudo apt install libreoffice-writer`. Installing only
  `libreoffice-common` or `libreoffice-core` gives you a `soffice` that exists but cannot open a
  DOCX ("source file could not be loaded"); Writer is the part that can.

`JOBOMATIC_LIBREOFFICE` chooses which one: `flatpak`, or a command or path to use. Unset, `jobo`
tries `soffice` and `libreoffice` on the PATH, then the Flatpak. A value that cannot be found is an
error, never a silent fallback. Details: [ADR 0024](adr/0024-resume-page-budget.md).

### 10. Optional: evidence search (Ollama)

`jobo evidence` and `jobo search` find the closest course, project and resume evidence for a skill.
They need a local [Ollama](https://ollama.com) server with an embedding model:

```bash
ollama pull nomic-embed-text
jobo index build          # embeds new or changed evidence; the index is rebuildable
jobo search "event-driven architecture"
```

Without Ollama, `jobo search --keyword-only` still works, and the evidence tools say "skipped"
instead of failing. Retrieval is advisory and never changes a fit rating.

### 11. Optional, once only: import a spreadsheet tracker

Do this on **one** machine, one time. The applications log lives in the vault and syncs through
git, so the other machine gets the entries when it pulls.

1. Export the tracker sheet as CSV.
2. Preview: `jobo applications import-csv tracker.csv --dry-run`
3. Fix any rows it reports (ambiguous dates such as `04/05/2026` and unknown statuses are
   rejected, never guessed), then run it again without `--dry-run`.
4. Commit and push the vault (`applications/applications.jsonl`).

## Check that it works

All of these should succeed (use your own vault, or `export JOBOMATIC_VAULT=$PWD/demo-vault`):

```bash
jobo profile validate
jobo fit-check tests/fixtures/strong-fit-jd.md
jobo applications list
jobo constraints show
.venv/bin/python -m pytest -q        # about a minute; uses a throwaway copy of the demo vault
git config core.hooksPath            # prints scripts/hooks
git status --short                   # prints nothing
```

The tests never touch your vault: each one gets its own copy of the demo vault.

## Working across two laptops

- **Pull before you start, push when you finish**, in **both** repos: code in one, your data in the
  other.
- **The applications log merges itself.** It is append-only, one event per line, and the vault's
  `.gitattributes` keeps both machines' lines (`merge=union`). Two laptops adding entries between
  pulls do not conflict.
- **The evidence index is not synced.** It is rebuildable and ignored by git: run `jobo index
  build` after pulling profile or learning changes.
- **Record "applied" on whichever laptop you used**, with `jobo applications applied --jd <file>`,
  then commit and push the vault so the other machine's duplicate check agrees.
- **Generated documents** go to the vault's `outputs/` and are committed there; they are never
  committed to the code repo (the hook blocks `*.docx`, `*.pdf` and `outputs/`).

## When something goes wrong

| Symptom | Likely cause and fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'jobomatic'` | The install was not editable, or you used a different Python. Re-run step 4 with `-e` and use `.venv/bin/...`. |
| `ERROR: No vault found` | No vault is configured. Set `JOBOMATIC_VAULT`, add the config file, or put `job-o-matic-vault` next to the checkout (step 6). |
| `... points at <path>, which has no .jobomatic.toml` | The folder is not a vault. Copy the marker from `demo-vault/`, or fix the path. |
| `No private/search-constraints.json found` | No salary minimums yet; the salary screen is skipped. Add the file to the vault's `private/` (step 6). |
| `unknown key(s)` from `constraints show` | A typo in the file. Only `min_permanent_base_cad` and `min_contract_hourly_cad` are allowed. |
| `cannot count pages: LibreOffice failed (soffice: Error: source file could not be loaded)` | A `soffice` without Writer is on the PATH. Install `libreoffice-writer`, or set `JOBOMATIC_LIBREOFFICE=flatpak` (step 9). |
| `cannot count pages: 'pdfinfo' ... was not found` | Install `poppler-utils` (step 1). |
| 3 MCP tests skipped | The checkout is under the temp directory (step 3). Move it. |
| Commit blocked: "refusing to commit private files" | You staged something under `private/` or `outputs/`. Unstage it; only `*.example.*` files belong in the code repo. |
| Commit blocked: "private value" | A name, employer, city or pay figure from your vault was typed into a tracked file. Remove it. |
| Commit blocked by ruff, mypy or tests | Fix what it reports. `git commit --no-verify` bypasses the hook; do it only on purpose. |
| The MCP server fails to start in Claude Code | Open Claude Code from the repo root and confirm `.venv/bin/python3` exists. |
| `applications check` reports an unreadable log | A bad merge left a broken line. The error names the line in `applications.jsonl`; fix or remove it. |
