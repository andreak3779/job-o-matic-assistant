# 0028 — Commands return structured results that the CLI and the MCP server render

**Status:** Accepted. Built; see "As built" for where the implementation differs from the draft.

## Context

[ADR 0002](0002-mcp-thin-adapter-over-cli.md) made the MCP server a thin adapter over the command
line, and [ADR 0016](0016-modular-monolith-ports-and-adapters.md) describes the code as ports and
adapters. In practice the adapter is coupled to the CLI's printed text:

- `interfaces/mcp/server.py` builds an argv list for each of its 24 tools and runs the CLI
  in-process under a global lock (`_CLI_LOCK`) with `redirect_stdout`, then finds the files a
  command wrote with a regular expression over `Wrote <path>` lines (`_WROTE_RE`).
- `interfaces/cli/main.py` rebuilds an argv list and calls each command's own `main(argv)`, so every
  command parses its arguments twice.
- Success and failure reach the MCP side as an exit code plus captured text. A path-shaped
  posting is told apart from pasted text by a heuristic (`_looks_like_path`), and pasted text is
  written to a temporary file because every command wants a path.

A change to a printed message can break an MCP tool without a type error or a failing import
contract. [ADR 0025](0025-simple-web-ui.md) adds a third interface, a local web UI, which needs the
fit rating, the status and the list of written files as data, so it cannot be built on printed
text.

What was found when this was investigated:

- **The gate is not in the commands.** `gate.check_documents`, `check_letter` and the cold-call
  location check are called from `interfaces/cli/main.py` (`_run_gates` and inline code), not from
  the command modules. The MCP server gets the gate only because it goes through the CLI
  ([ADR 0003](0003-fit-gate-enforced-at-mcp-boundary.md) records it as holding for both
  interfaces; that is true by route, not by construction). A caller that invoked a command
  directly would skip it. This must be fixed before any adapter stops going through the CLI.
- **The refusal already carries its override.** `GateRefusal` has an `override` field naming the
  confirmation that would let it through (`confirm_gaps`, `confirm_reapply`,
  `confirm_below_minimum`). It is lost only when the CLI prints it to stderr as a sentence.
- **The lock also serializes writes.** It was added to protect `sys.stdout`, but it also means
  two tool calls never touch the vault at the same time. The applications log is appended with a
  single `O_APPEND` write and does not need it. The YAML files (`items.yaml`, `stories.yaml`, the
  profile) are saved with a plain `write_text` after a read, and a record-a-draft step follows a
  duplicate check, so concurrent calls could lose an update or record a draft twice. Nothing
  protects against two *processes* (the CLI while the MCP server runs, or two MCP servers); that
  was never the case.
- **Expected failures come in several shapes**: exit codes, text on stderr, and exceptions
  (`ValueError`, `DocumentError`, `ProfileError`, `VaultError`, `FileNotFoundError`, `GateRefusal`,
  `SystemExit` from `argparse`). Helpers such as `run_and_report` and `load_profile_or_none` print.
- **Printed `Wrote` lines can be influenced by a posting**, since some of what a command prints
  comes from the posting. The server already checks every path against its write roots before
  attaching a file, for that reason.

## Decision

**Commands return a result object. The CLI and the MCP server (and later the web UI) render it.**
Nothing reads printed text. Each command has a function `run(params) -> CommandResult`, and
`main(argv)` becomes parse, `run`, render.

### 1. The result

```python
@dataclass(frozen=True)
class Message:
    level: Literal["info", "note", "warning", "error"]
    text: str


@dataclass(frozen=True)
class CommandResult(Generic[T]):
    status: Literal["ok", "error", "refused"]  # exit codes 0, 1, 2
    data: T | None = None  # the command's typed payload
    messages: tuple[Message, ...] = ()
    written: tuple[Path, ...] = ()  # every file this run created or changed
    override: str | None = None  # refused only: the confirmation that clears it
```

- **`ok`** is exit 0, **`error`** is exit 1 and **`refused`** is exit 2, as the CLI behaves today.
  A refusal is a gate saying no, and carries `override` (or `None` when it cannot be overridden: a
  location Pass or a skills Pass).
- **There is no free-text field for the output.** The payload is typed per command (a fit rating
  and its table rows, a learning-import diff, an application list). Markdown and console text are
  produced by renderers, one per payload, shared by the CLI and the MCP server, so the two cannot
  say different things. The fit module already has `render_fit_table`. A payload may be a plain
  `str` only when the command's product *is* text (the profile view, the application folder).
- **`written` replaces `Wrote <path>` lines.** The CLI renderer still prints them, in the same
  place, so the printed output is unchanged. The MCP server attaches exactly these files, still
  checked against its write roots as defence in depth.
- A message is `info` (plain output such as "Logged as drafted"), `note` (advice to show with the
  result), `warning` (something the run worked around) or `error` (why it did not succeed). An
  `error` or `refused` result must carry at least one `error` message, and only a `refused` result
  can carry an `override`.
- The type lives in `jobomatic/results.py`, a top-level module in the same layer as `bootstrap`.
  It cannot live in `jobomatic.commands` as first drafted: the five presence generators are among
  the 24 tools, `presence` and `commands` are independent siblings in the import contracts, and no
  module may use the `commands` package. A top-level module is already in the package list, so
  nothing is added to `pyproject.toml` except its place in the layers contract.

### 2. One boundary for expected failures

A single helper, `guarded` in `jobomatic/results.py`, turns the expected failures (`ProfileError`,
`VaultError`, `DocumentError`, `LearningError`, `RetrievalError`, `ValueError` from validation, and
`OSError`, which includes `FileNotFoundError`) into `error`, and a refusal into `refused` with its
`override`. The refusal is a base exception, `Refusal`, defined in `results.py`; the gate's
`GateRefusal` extends it, so the helper does not import the gate (the gate sits in a layer above
it). `Refusal` also owns the sentence that tells a caller how to confirm, so both interfaces say
it the same way. The helper replaces the printing in
`run_and_report` and `load_profile_or_none`. An exception that is not on that list is a bug and
propagates, as it does today; the MCP framework reports it as a tool error.

### 3. The gates run inside the command

The gate moves from `interfaces/cli/main.py` into `run()` of every command that is gated, before
anything is written: `generate-resume` and `generate-cover-letter` (fit, duplicate, pay),
`generate-job-site` (location, duplicate) and `generate-cold-call` with a posting (location).
This is ADR 0016 rule 4 (policy lives in the use case) and makes [ADR 0003](0003-fit-gate-enforced-at-mcp-boundary.md)
true by construction. It is done **before** any MCP tool is switched to call a command directly.
The import contracts need a change for this: `commands`, `gate` and `presence` are independent
siblings today, so a command cannot import the gate. The gate moves to the layer below the
commands and presence (it uses only the fit, applications and profile modules).
A test fails for any gated command that can complete without the gate: given a posting the gate
must refuse, `run()` returns `refused` and writes nothing, for the CLI and the MCP server alike.

### 4. The posting is passed as text

`run()` takes the posting as text, not a path. Reading the file, and the ADR 0027 "file not found"
message, stay in the CLI adapter; the MCP server passes the text it was given, or reads a path it
has checked. This removes `_looks_like_path`, `_jd_path` and the temporary file. Other optional
inputs (company research, recruiter briefing, Q&A cards, a role JSON) stay paths for now; they are
read by the adapter that checked them, and whether they should also become text is not decided
here.

Argument validation moves with it: the MCP server builds typed parameters (a stage is an enum, not
a string for `argparse` to reject), so an invalid value becomes an `error` result and the
`SystemExit` branch is not needed. The CLI keeps `argparse` for its own parsing.

### 5. The lock

`redirect_stdout` and the output lock go. **Writes to shared vault state stay serialized** by one
in-process lock, taken inside `run()` by the commands that read-modify-write the vault
(`learning import --apply` and the other `learning` writes, `interview-prep --update-star-bank`,
the generators that record a draft, and the `applications` writes), not by the adapter. Because it
is in the command layer, the CLI (uncontended), the MCP server and the web UI (threaded) all get it
without each adding its own. Not decided here, and not changed: protection between processes (file
locking) and atomic replacement of the YAML files. Both are worth doing, but neither was true
before, and they are separate from this record.

### 6. Scope: what moves

Every command the MCP server exposes moves: the 24 tools are `validate_profile`, `fit_check`,
`gap_analysis`, the five presence generators, `generate_resume`, `generate_cover_letter`,
`generate_application_documents`, `generate_cold_call`, `generate_job_site_letter`,
`generate_thank_you`, `interview_prep`, the four `applications_*` tools, `learning_import`,
`search_constraints`, `search_evidence`, `profile_summary` and `generate_learning_plan`. Commands
that only the CLI offers (`render`, `index`, the other `learning` subcommands) keep printing until a
second interface needs them. The guards in the build order apply to the commands that moved.

### 7. Build order

Strangler style: both paths exist while commands move, and each step leaves the suite green.

1. Tests that record each command's stdout, stderr and exit code, what each MCP tool returns, and
   that the CLI and the MCP server produce the same files and status.
2. The result type, the boundary helper and the renderers.
3. Move the gates into `run()` (section 3).
4. Move commands one at a time, switching the matching MCP tool as each moves: `fit-check`, then
   `applications` and `constraints`, then `profile` and `search`, then the generators, then the
   rest.
5. Section 5: the write lock in the command layer. Then delete `_run_cli`, `_CLI_LOCK`,
   `redirect_stdout`, `_WROTE_RE`, `_looks_like_path` and `_jd_path`.
6. Guards: an import-linter contract that the MCP server does not import the CLI (it does today)
   and that `commands` does not import `interfaces`; a test that fails on `print(` or
   `redirect_stdout` in a moved command; a test that the MCP tool list is unchanged.
7. Documents: ADR 0002 gets a status line saying it is amended by this record, and ADR 0025's
   build-order note is updated.

## Considered and rejected

- **Keep output capture and give the `Wrote` line a documented, tested format.** Smaller, and it
  would close the failure of a reworded message. It leaves the double parsing, the lock and the
  exit-code-plus-text interface, and ADR 0025's web UI would have to read printed text or wait for
  this work anyway.
- **Leave it and record the coupling as accepted.** The web UI is the reason not to.
- **A result that carries the finished text.** It is the smallest change, but the web UI would read
  that text, which is the coupling this record removes.
- **Each adapter calls the gate itself.** It would put the same rule in three places. The gate
  belongs to the use case.
- **A command registry in this change** (name, parameter type, `run`, gated or not, shared by the
  three adapters). It is the right answer to adapter drift, and ADR 0025 already needs a test that
  the tool lists match. It is left to that record; `run()` is written so a registry can be added
  without changing it.
- **A `--json` flag on the CLI.** The result type makes it cheap, but nobody asked for it.

## Consequences

- **A printed message can no longer break a tool.** The MCP tools read `status`, `data` and
  `written`, which are typed and tested.
- **A posting cannot influence which file is attached**, because `written` is the paths the
  command itself wrote, not text matched in output.
- **The gate holds by construction** for every adapter, including the web UI.
- **The CLI's output does not change.** The snapshot tests in step 1 are what prove it.
- **A new parameter type for each command moved** (about two dozen), and a renderer for each
  payload. That is the cost, and it is the surface a registry would later build on.
- **Behaviour changes at the seam that are intended**: the posting reaches a command as text, and
  an invalid enum value is an `error` result instead of an `argparse` exit.
- **Open risk, unchanged**: two processes writing the vault at once. Named here so it is a choice,
  not a surprise.
- **ADR 0002's text is not rewritten**, per the ADR README; it gets a status line when this is
  built.

## As built

The decision above held. What the implementation changed or added:

- **Where the code is.** `jobomatic/results.py` has `CommandResult`, `Message`, `ok`, `failure`,
  `refusal`, `Refusal`, `guarded`, and `console()`/`emit()`, which turn a result into the text the
  command line prints. The MCP server calls `console()` too, which is why the two cannot differ.
  There is no `interfaces/cli/output.py`: `commands` may not import `interfaces`.
- **Message levels** are `info`, `note`, `log`, `warning` and `error`. `log` is a plain line on stderr
  (how the run went, for example the index being synced). A failed result must carry a message of any
  level, not only `error`, so the profile and learning commands keep printing `[ERROR] ...` and
  `Profile has N error(s).` on stdout exactly as before. `failure()` can carry the data produced
  before the failure.
- **Every command is `run()` plus a thin `main()`.** `generate_*()` functions keep their path-taking
  signatures and tuple returns (many tests and scripts use them) and delegate to `*_from_text()`
  cores; an optional `notes` list collects what they would print (see `commands.support.say`), and a
  caller that passes none still sees it printed.
- **One skeleton for documents.** `commands.support.produce_document()` runs the gate, makes the
  document, and holds the vault write lock for the run. `presence/draft.py` does the same for the five
  profile-update generators.
- **The write lock** is `commands.support.vault_write_lock()`, a re-entrant in-process lock. The
  document commands, `applications applied` and `status`, and an applying `learning import` hold it. A
  test shows two threads marking one new posting applied make one entry, and fails without the lock.
  Protection between processes and atomic YAML writes are still not done.
- **The gates** run inside the commands. The import contracts changed to allow it: the gate moved to
  the layer below `commands` and `presence`.
- **The posting is text**, with a `source` path for the sidecar. A pasted posting records no input in
  the sidecar; before, it recorded a temporary file that no longer existed.
- **Guards.** The MCP server and the command line import neither the other. A test fails if a command
  or presence module prints outside its own `main()`, if anything in `src` uses `redirect_stdout`, or if
  the MCP server mentions the old machinery. The snapshot tests also fail if an MCP tool writes to
  stdout, the protocol channel.
- **Behaviour changes**, all on paths nothing was recording before: a missing posting on a gated
  command gets the ADR 0027 message; an unknown status or stage is an error result; a broken profile or
  vault is a clean error in the profile-update generators (it was a traceback); `search`'s stopped
  embedding service is the same two-line message.

**Left as it was.** `main.py` in the command line still rebuilds an argv list and calls each command's
`main(argv)`, so a command parses its arguments twice there. Removing that needs the dispatcher to call
`run()` with the parsed values, which no interface needs yet. The commands only the command line offers
(`render`, `index build`, `evidence`, the other `learning` subcommands, `applications add` and
`import-csv`, `profile schema`, the platform resume and cover letter) still print directly.
