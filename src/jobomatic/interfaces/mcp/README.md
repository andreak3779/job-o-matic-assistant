# job-o-matic MCP server

Exposes the `jobo` commands (`src/jobomatic/commands/`) as MCP tools, and the
application-workflow skills as MCP prompts, so an MCP client — Claude Desktop,
or any other MCP-capable app — can run fit checks, search the evidence in your
own record, and generate application documents without a terminal. The server
is registered as `job-o-matic`.

> **Pre-1.0 and in active development.** job-o-matic works end to end and is used by its author for a live job search. It is not yet 1.0: command options, the profile file layout and generated-document formats can still change, and there is no migration guarantee. Commit and push your vault before you update.

Every tool is a thin wrapper: it checks the paths it was given, calls the command's `run()`
(see `src/jobomatic/commands/`, and `src/jobomatic/presence/` for the profile-update generators)
with plain values, and returns the text of the result and the content of the files the result
lists as written. It does not drive the command line, read printed text, or capture output
([ADR 0028](../../../../docs/adr/0028-structured-command-results-for-cli-and-mcp.md)). No
generation logic lives here, and no gate logic either: the fit, duplicate, pay and location gates
run inside the commands, before anything is written, so they hold for every caller (see "Fit gate"
below). The MCP server and the command line do not import each other; an import contract checks
it.

## Tools

| Tool | CLI equivalent |
| --- | --- |
| `validate_profile` | `profile validate` |
| `fit_check(jd)` | `fit-check <jd>` |
| `gap_analysis(jd, out=None)` | `gap-analysis <jd> [--out]` |
| `generate_linkedin(out=None)` | `generate-linkedin [--out]` |
| `generate_github(out=None)` | `generate-github [--out]` |
| `generate_jobgether(out=None)` | `generate-jobgether [--out]` |
| `generate_job_board(out=None)` | `generate-job-board [--out]` |
| `generate_pluralsight(out=None)` | `generate-pluralsight [--out]` |
| `generate_resume(jd, company=None, out=None, confirm_reapply=False, confirm_below_minimum=False)` | `generate-resume <jd> [--company] [--out]` — refuses a duplicate application or pay below the minimum unless confirmed |
| `generate_cover_letter(jd, company=None, out=None, confirm_reapply=False, confirm_below_minimum=False)` | `generate-cover-letter <jd> [--company] [--out]` — same gates as `generate_resume` |
| `generate_application_documents(jd, company=None, confirm_reapply=False, confirm_below_minimum=False)` | resume + cover-letter in one call, same gates |
| `generate_cold_call(jd, company=None, out=None)` | `generate-cold-call <jd> [--company] [--out]` |
| `generate_job_site_letter(jd, company=None, out=None, confirm_reapply=False)` | `generate-job-site <jd> [--company] [--out]` |
| `generate_thank_you(jd, company=None, out=None)` | `generate-thank-you <jd> [--company] [--out]` |
| `interview_prep(jd, out=None)` | `interview-prep <jd> [--out]` |
| `generate_learning_plan(role_json)` | `generate-learning-plan <role_json>` |
| `applications_check(jd)` | `applications check <jd>` — NEW / DRAFTED / RELATED / REPEAT / DUPLICATE |
| `applications_list(status=None, company=None)` | `applications list [--status] [--company]` |
| `applications_mark_applied(application_id=None, jd=None, date=None)` | `applications applied` — **only when the user says they submitted it** |
| `applications_set_status(application_id, status, next_step=None, note=None)` | `applications status <id> <status>` |
| `learning_import(file=None, content=None, apply=False)` | `learning import <export> --provider pluralsight [--apply]` — Pluralsight only. **A dry run unless `apply=True`; set it only after the user has seen the result and said yes.** `file` is a path to the import `.json` from `templates/pluralsight_import_template.html` or a saved history `.html`; `content` is the text of a small import file (for example its "new entries only" download). Summaries and `index build` stay CLI steps |
| `search_constraints()` | `constraints show` — the private salary minimums |
| `search_evidence(query, k=3)` | `search <query> --k` over courses, labs, Microsoft Learn items and projects only — advisory (ADR 0012); needs the local Ollama service, and says "Evidence search skipped" without it. Resume bullets and interview stories are `local_only` (ADR 0019) and never returned, because a tool result goes to the model Claude Desktop talks to |
| `profile_summary()` | `profile show --public facts` — headline, summary, certifications and skills; no contact details, nothing marked private |

`jd`, `out`, and `role_json` paths may be absolute or relative. A relative
path starts from the server process's current folder, exactly as on the
command line ([ADR 0027](../../../../docs/adr/0027-relative-paths-resolve-against-the-current-folder.md)).
Prefer absolute paths from MCP clients since they don't have a reliable notion
of "current directory."
For `generate_learning_plan`, this applies to the role config's own
`"output"` key too — it's resolved relative to this server's working
directory, so prefer an absolute path there as well.

Every `jd` parameter also accepts the job description's raw text instead of
a path — this is the normal case when a client like Claude Desktop has a
job description pasted or attached in the chat itself, since that content
never lands on disk anywhere the server's filesystem can see. A `jd` string
is treated as a path only if it's short, single-line, and contains no
spaces; anything else is the job description text itself and goes straight to the
command (nothing is written to disk for it). A path-shaped string that doesn't resolve to
a real file still raises a clear "job description file not found" error
(so a typo'd path never gets silently reinterpreted as literal JD text).

A command that does not succeed (an error or a refusal) raises an MCP tool error containing
what the command line would have printed, so the client sees it as a failure rather than a
silent success.

## Prompts

The skills in `skills/<name>/SKILL.md` are the single source for the
workflows. Nine of them are served to Claude Desktop as MCP prompts (each takes an
optional `jd` argument that is appended to the prompt):

| Prompt | Uses |
| --- | --- |
| `job-description-fit` | `fit_check`, `applications_check` |
| `gap-analysis-job-description` | `gap_analysis` |
| `create-a-cover-letter-and-tailored-resume-for-job-description` | `generate_application_documents`, `generate_resume`, `generate_cover_letter` |
| `interview-prep` | `interview_prep`, `profile_summary` |
| `interview-practice`, `interview-practice-job-description` | `profile_summary`, `fit_check` |
| `post-interview-thank-you-letter` | `generate_thank_you` |
| `cold-outreach-recruiter-letter` | `generate_cold_call` |
| `salary-research` | `search_constraints`, `profile_summary` |

Each prompt is the skill's text behind a short preamble that says which tool to call
in place of each command (`src/jobomatic/interfaces/mcp/skill_prompts.py`, `COMMAND_TO_TOOL`). A test
fails if a listed skill starts needing a command that has no tool.

These skills stay Claude Code only, because they need a shell or file import that Desktop
does not have: the Pluralsight and Microsoft Learn updaters and summary enricher (`learning ...`),
the part-time resume (`render`), the learning-plan skills (`learning lookup`), the platform
resume PDF, the routing skills and the profile-update skills that read `profile show` in full.
Giving Desktop a tool for an importer would be a small follow-up.

## Returned content

Every document-producing tool (everything above except `validate_profile`
and `fit_check`) returns the artifact's actual content,
not just the local path it was written to — that's what makes a generated
resume, cover letter, gap analysis, or learning-plan PDF retrievable through
a client with no filesystem access to this machine's `outputs/` folders. The
file is still written to its normal `outputs/` location as before — this is
additive, not a replacement.

How that content comes back depends on the tool:

- **Profile-update tools** (`generate_linkedin`, `generate_github`,
  `generate_jobgether`, `generate_job_board`, `generate_pluralsight`) — their
  markdown draft *is* the deliverable, so every artifact they write (the
  draft plus its provenance sidecars) comes back as a text `EmbeddedResource`
  (`text/markdown` or `application/json`). MCP clients like Claude Desktop
  render an `EmbeddedResource` as an attachment, so the draft shows up as a
  document rather than getting dumped into the chat transcript as a wall of
  text.
- **Everything else that produces markdown/text/JSON** (gap analyses,
  provenance `.meta.json` sidecars from other tools) comes back as inline
  text — that content is meant to be read and discussed directly in the
  conversation.
- **DOCX and PDF artifacts** (resumes, cover letters, thank-you notes,
  learning plans, etc.) come back as a base64-encoded `EmbeddedResource`
  with the correct MIME type, same as before.

## Fit gate

`generate_resume`, `generate_cover_letter`, and `generate_application_documents`
refuse to generate (raising a tool error with the rating and rationale) when
the JD's computed fit rating is below Good. This enforces, in code, the same
rule the `create-a-cover-letter-and-tailored-resume-for-job-description`
skill already states as prompt guidance — an MCP client calling these tools
directly bypasses that skill (and its judgment) entirely, so the rule is
checked here too. Call `fit_check` first to see the rating without
generating documents. No other tool is gated this way.

## Install

The install steps are in one place: [docs/setup.md](../../../../docs/setup.md). The short version is
`bash scripts/setup.sh` from the repository root, which installs the `mcp` package with everything
else. Check it with `bash scripts/check-setup.sh`: it reports whether the MCP package is installed
and whether `.mcp.json` can start the server.

**ModuleNotFoundError: No module named 'mcp'.** If Claude logs show this, the `mcp` package is
missing from `.venv`. Run `bash scripts/setup.sh` again from the repository root, then restart Claude
Desktop (it only reads its settings on startup).

If you edited `claude_desktop_config.json` by hand, point it at this repository's
`.venv/bin/python3`, typically `/path/to/job-o-matic-assistant/.venv/bin/python3`.

## Try it out (MCP Inspector)

```bash
mcp dev src/jobomatic/interfaces/mcp/server.py
```

Opens the MCP Inspector in a browser — call each tool interactively before
wiring up a client.

## Wire up Claude Desktop

**Important:** Complete the [install](#install) first — Claude Desktop
needs the dependencies to be installed in your venv before it can use the
server.

Easiest: let the `mcp` CLI write the config for you (run from the repo root,
using this project's venv):

```bash
.venv/bin/mcp install src/jobomatic/interfaces/mcp/server.py --name job-o-matic \
  --with-editable . --with python-docx --with beautifulsoup4 --with lxml \
  --with orjson --with pyyaml --with jsonschema --with reportlab
```

Or edit `claude_desktop_config.json` by hand:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "job-o-matic": {
      "command": "/path/to/job-o-matic-assistant/.venv/bin/python3",
      "args": ["-m", "jobomatic.interfaces.mcp.server"],
      "cwd": "/path/to/job-o-matic-assistant/"
    }
  }
}
```

The server finds your vault the way the CLI does: `$JOBOMATIC_VAULT`, then
`~/.config/job-o-matic/config.toml`, then a sibling `job-o-matic-vault/` directory. Add
`"env": {"JOBOMATIC_VAULT": "/path/to/job-o-matic-vault"}` to the entry to pin it.

If you registered the server under its old name (`claude-jobs`, pointing at the archived
`claude-projects` checkout), delete that entry so Desktop does not start the old code.
If your entry sets `CLAUDE_JOBS_ALLOWED_DIRS`, `CLAUDE_JOBS_PRIVATE_DIR` or
`CLAUDE_JOBS_APPLICATIONS_LOG`, rename them to `JOBOMATIC_ALLOWED_DIRS`, `JOBOMATIC_PRIVATE_DIR` and
`JOBOMATIC_APPLICATIONS_LOG` (ADR 0030). The old names are not read; the server refuses to run with
one set and says which new name to use.
Restart Claude Desktop after either method — it only reads this config on startup.
Then try, in order: a fit check on a pasted job description, one document generation, and a
`search_evidence` question.

## Running in a container (Podman)

The repo includes a `Dockerfile` at the repo root, built and run with
[Podman](https://podman.io/) (Podman Desktop works too — it's the same
engine under a GUI). This is a same-machine setup: Claude Desktop still
spawns the server as a local child process over stdio, just via `podman run`
instead of a bare `python3` command.

Build once, and again whenever the code or its dependencies change:

```bash
podman build -t job-o-matic-mcp .
```

Point Claude Desktop at it (same config locations as above). The **vault** is
what gets bind-mounted, not the code (ADR 0005, updated):

```json
{
  "mcpServers": {
    "job-o-matic": {
      "command": "podman",
      "args": ["run", "-i", "--rm", "-v", "/path/to/job-o-matic-vault:/vault", "job-o-matic-mcp"]
    }
  }
}
```

The image sets `JOBOMATIC_VAULT=/vault`. If you hit permission errors reading or writing
the mount (Fedora/RHEL-family hosts with SELinux, not Ubuntu/Debian), append `:Z`:
`-v /path/to/job-o-matic-vault:/vault:Z`. The mount can be read-only (`:ro`) for a server that
only reads, but then document generation, which writes to `outputs/`, will fail.

Tested for this change: the image builds, and over stdio it lists the tools and prompts and
answers `profile_summary` and `fit_check` against the fictional `demo-vault` mounted read-only.

### Path restrictions

Every path a client passes in is untrusted (a pasted job posting can carry prompt-injection text
that steers a tool call). The rules live in `src/jobomatic/interfaces/mcp/access.py` (written by the author, ADR 0020):

- **Readable:** the vault, the system temp directory, and any directory in `JOBOMATIC_ALLOWED_DIRS`.
  The code repository itself is not.
- **Writable:** the vault `outputs/` folder (and its learning-plans folder), the one file
  `profile/stories.yaml` (for `--update-star-bank`), the temp directory and the extra directories.
  The rest of the vault is read-only.
- **Never, in either direction:** the vault's `private/` folder (salary minimums), the applications
  log (changed only through the applications tools), and any `.git` directory.

Paths are resolved first (`..` and symlinks followed), so a link inside `outputs/` cannot lead out of it.
Anything else is refused with a `ToolError`. `JOBOMATIC_ALLOWED_DIRS` takes paths separated by `:`
on Linux and macOS.

### `learning_import`: access review

ADR 0020 asked for a review before any importer tool. What a client controls and what it cannot:

- **Controlled by the client:** `file`, checked like every other path (readable roots only, never
  `private/`, the applications log or `.git`) and limited to `.html`, `.htm` and `.json`, so the
  tool cannot be used to read other vault files; and `content`, up to 2 MB, held in a throwaway temp
  folder for the call and deleted afterwards. A full history import file is about 100 KB.
- **Fixed by the CLI, not the client:** what is written. Only the vault's
  `profile/learning/items.yaml` and a copy of the export in `imports/pluralsight/`. With a
  read-only mount (`:ro`) a dry run works and `apply=True` fails, which is the safe direction.
- **Not available:** Microsoft Learn (a transcript is refused) and anything that uses the network.
- **What comes back to the model:** course titles, dates and counts, nothing from the profile.
- **Where the file lives:** Desktop reaches only the vault and the directories in
  `JOBOMATIC_ALLOWED_DIRS`. Put the downloaded import file in the vault (for example
  `imports/`), add its folder to `JOBOMATIC_ALLOWED_DIRS`, or paste a small one as `content`.

### PII

Personal data lives in the separate private vault repo, never in this one. None of it is baked into
the image: the vault is outside the build context, and `.containerignore` also excludes `private/`,
`outputs/` and the applications log as a safety net. It reaches the running container only through
the bind mount. A tool result goes to the model Claude Desktop uses, which is why `search_evidence`
leaves out resume bullets and interview stories and `profile_summary` returns the public view only.
No at-rest encryption is applied — the bind mount plus your normal OS login and disk encryption was
judged sufficient.

### Later: a separate machine on the LAN

This design doesn't block adding a network-reachable mode later — switching
`src/jobomatic/interfaces/mcp/server.py`'s `mcp.run()` to the `streamable-http` transport and
exposing a port would let a container on a different Linux PC be reached
over the network, with Claude Desktop pointed at it as a remote connector
instead of a local stdio command. Not implemented now; noted here so the
same-machine setup above isn't mistaken for the only option.

## Tests

```bash
python3 -m pytest tests/test_mcp_server.py tests/test_mcp_prompts.py tests/test_mcp_access.py -q
```

Calls each tool function directly (no live MCP transport needed) against
`tests/fixtures/*.md`, mirroring `tests/test_cli_commands.py`.
