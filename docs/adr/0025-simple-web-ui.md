# 0025 — Simple web UI: standalone pages and a local web UI for the MCP tools, in the job-o-matic look

**Status:** Proposed. Part of this exists: the Pluralsight import page
([`templates/pluralsight_import_template.html`](../../templates/pluralsight_import_template.html))
works today, but does not yet use the brand. The local web UI for the MCP tools and the shared
look are decisions, not built.

**Build order:** [ADR 0028](0028-structured-command-results-for-cli-and-mcp.md) is built: every
command the MCP server offers returns a `CommandResult` (`jobomatic.results`), and the command
line and the MCP server both render it. The local web UI is built on `jobomatic.commands.*.run()`
and those results, so it never reads printed text.

## Context

There are three ways in today: the `jobo` command line, the MCP server for Claude Desktop
([ADR 0020](0020-mcp-server-for-claude-desktop.md)) and the skills for Claude Code. All three are
text. Two kinds of task fit text badly:

- **Moving a large paste of HTML.** A Pluralsight history table is too big to paste into a chat,
  and the `pluralsight-updater` skill says never to read an export into context. The page
  `templates/pluralsight_import_template.html` solved this: one self-contained file, no server,
  that parses the pasted table in the browser, previews it, and downloads an import file for
  `learning import`. Nothing is uploaded. It mirrors the Python reader's column layout and
  structure checks, and the `FORMAT` and `VERSION` of the import file, **by a comment asking the
  next editor to change both places together**; nothing tests that.
- **Reading a result and then deciding.** A fit rating with its reasons, a duplicate check, or the
  diff from a learning import (what is new, what changed, which ids moved) is easier to read as a
  page with a button than as captured console text, and `--apply` should be a deliberate click
  after the diff has been seen.

There is a brand, and the web pages do not use it consistently:

- The assets are in `src/jobomatic/branding/` (`job-o-matic-icon.svg`, `job-o-matic-logo.svg` and
  `.png`, `icon-512.png`, `favicon.ico`), with `docs/assets/social-preview.png`. `site/assets/`
  holds copies, and `tests/test_site_assets.py` fails if a copy drifts from its original.
  The MCP server already sends the icon to clients as `data:` URIs (`server_icons()`), and uses
  the gauge icon, not the full logo, because the logo's lettering cannot be read at icon sizes.
- The landing page (`site/index.html`) defines the look: cream background (`#fdf6e3`), navy text
  and rules (`#1b1f4b`), teal accent, pink and sun-yellow accents taken from the logo, thick navy
  outlines, rounded corners, and a dark mode built on the same navy.
- The Pluralsight page has its own blue-and-grey palette and a text-only header. It looks like
  a different product.

[ADR 0004](0004-stdio-only-transport.md) keeps the MCP server on stdio so that nothing binds a
port, and says any network setup "needs its own decision (and likely its own ADR) covering
authentication". A web UI for the MCP tools has to open a port, so this is that decision.

## Decision

### 1. Two kinds of page, kept apart

- **Standalone pages**: one HTML file in `templates/`, opened from disk, no server and no
  network. It does a job in the browser and hands a file to the CLI or the MCP tools. The
  Pluralsight import page is the first and the model for the rest. It needs no dependency and no
  port, which is why it stays the way to move a large paste.
- **A local web UI for the tools**: an opt-in command, `jobo web`, that
  serves the same tools the MCP server offers, in a browser, for someone who wants a screen
  instead of Claude Desktop. It is **another thin adapter** next to the CLI and the MCP server
  ([ADR 0002](0002-mcp-thin-adapter-over-cli.md),
  [0016](0016-modular-monolith-ports-and-adapters.md)). It holds no rules: the fit rating, the
  gate ([ADR 0003](0003-fit-gate-enforced-at-mcp-boundary.md)) and the file access policy
  (ADR 0020) apply to it exactly as they do to the MCP server. **It is built on the structured
  results of [ADR 0028](0028-structured-command-results-for-cli-and-mcp.md)**, not on the MCP
  tool functions: those return finished text, and a web page needs the rating, the status and the
  list of written files as data. It must not copy the output-capture code in
  `interfaces/mcp/server.py` or read printed text. So 0028 is decided and built first, and this
  command is started after it.

### 2. The local web UI is local, opt-in and small

- **Listens on `127.0.0.1` only**, on a port chosen at launch, in the foreground; Ctrl+C stops it.
  The MCP server stays stdio-only, so ADR 0004 still holds for it.
- **Guards against other pages in the same browser**, because any open web page can send requests
  to `localhost`. They are one `before_request` hook, so no route can skip them:
  - a check of the `Host` header against `127.0.0.1` and `localhost` on the launch port (the
    DNS-rebinding allowlist ADR 0004 mentioned);
  - a **single-use launch token**: the command opens `/?token=…`, the server accepts it once,
    sets a session cookie (`HttpOnly`, `SameSite=Strict`, no `Domain`), and redirects to the same
    address without the token, so it does not stay in the history or in a `Referer`. Every other
    route needs the cookie; a second use of the token is refused;
  - every `POST` also needs a matching `Origin` and a per-session form token, and the server
    sends no CORS headers;
  - the Werkzeug debugger and reloader are never enabled, because the debugger runs code.
- **One new Python dependency, as an optional extra.** Flask (with Jinja) goes in a `web` extra
  in `pyproject.toml`, so the core install stays as it is and `jobo web` says what to install if
  Flask is missing. It serves pages rendered on the server from the results of ADR 0028. Flask's
  built-in server is meant for development; one person on loopback is the case it handles
  well enough, and the ADR does not claim more. No request to any other origin: no CDN, no web
  fonts, no analytics. The pages show a real profile and real job descriptions.
- **Pasted text is escaped, always.** Pages show job postings, course titles and notes that came
  from outside. Templates are `.html` files with Jinja's automatic escaping on, and no template
  uses `|safe` or switches escaping off for data that did not come from the project itself.
- **HTMX for partial updates, vendored.** One small pinned file, served from the package with its
  licence file, no CDN, used for things like showing the dry-run result or saving a status
  change without a reload. It is configured to refuse cross-origin requests and `eval`
  (`selfRequestsOnly`, `allowEval` off). Every page still works as an ordinary form post; HTMX
  only makes it smoother. There is no build step, and there is no other JavaScript beyond a few
  inline lines.
- **The first version covers what a screen improves**: fit check (paste a posting), duplicate
  check, `validate_profile`, the two pages below, and **document downloads** (resume, cover
  letter and the other generators), offered only after the gate passes and served through the
  same write rules as the MCP server. Not in the first version: editing the vault, the private
  salary minimums, and anything under the vault's `private/` folder.
- **Overrides are never pre-selected.** `confirm_reapply`, `confirm_below_minimum` and the like
  are unticked boxes that name what is being overridden. `--apply` is a separate button shown
  only after the dry-run result is on screen. "Mark as applied" is its own explicit action
  ([ADR 0010](0010-applications-log-event-sourced-explicit-applied.md)).
- **Pluralsight import takes the import file or a saved history page**, the same inputs as
  `learning_import`. It does not carry a third copy of the HTML parser: the browser page and the
  Python reader are already two copies, and the standalone page stays the only place that parses
  a paste.

### 2a. The web UI is Flask, Jinja and HTMX

The web UI is **server-rendered**: a Flask app in `src/jobomatic/interfaces/web/` with Jinja
templates, one stylesheet built on the colour tokens in section 3, and HTMX for partial updates.

- **Python all the way.** No Node, no TypeScript, no build step and no generated or committed
  bundle. A person who clones the repository, installs the `web` extra and runs `jobo web` has
  everything, and the setup path in [ADR 0026](0026-guided-setup-and-pre-1-0-status.md) gains one
  line in its optional extras. The pages are tested with pytest and Flask's test client.
- **The look is our own CSS.** No component library or CSS framework, because a ready-made set
  has its own look and the brand is the point of section 3.
- **Routes are thin.** A route parses the form, calls the command layer from ADR 0028, and
  renders the result. It holds no rules and reads no printed text.
- **Standalone pages are separate.** They must open from disk with no server, so they stay
  hand-written HTML and do not use Flask or HTMX (section 1).

### 2b. Pages the local web UI needs

Each is a route of the Flask app. Every page uses the shared look in section 3 and a header with
the icon and a link to each of the other pages. Without HTMX each page still works as a form.

1. **Pluralsight import page, `/pluralsight`: a page of its own.** Three steps on one page:
   choose the import file (or a saved history page), see the dry-run result (what is new, what
   changed, which ids moved, items with no topic), then press **Apply**, which is only enabled
   once the result is on screen. It links to the standalone page for the step that needs a
   paste. This is the screen form of `learning_import` and the `pluralsight-updater` skill.
2. **Applications page, `/applications`: the list, and the way to change a status.** A table of
   the applications in the log (company, role, status, next step, last change) with filters for
   status and company, the same as `applications_list`. Each row has a control to move it to a
   new status (`drafted`, `applied`, `phone_screen`, `technical`, `offer`, `rejected`,
   `withdrawn`), with optional next step and note, which calls the same operation as
   `applications_set_status`. Moving a row to `applied` uses the explicit mark-applied action,
   with a confirmation that names the posting, because "applied" is only ever set on purpose
   (ADR 0010). The log is append-only, so the page shows the new state and never edits an old
   entry.

The other screens (fit check with duplicate check, validation and document downloads) hang off a
home page that links to these two.

### 3. Every web page follows the job-o-matic assets

- **The source of truth is `src/jobomatic/branding/`.** Pages use the **gauge icon**
  (`job-o-matic-icon.svg`) as the header mark and favicon, and `favicon.ico` as the fallback.
  The full logo is for a hero-size placement only, never a header, for the reason the MCP server
  already gives. Social preview art is not used. The pages show the job-o-matic mark and name, not
  the logo of any third-party service they handle.
- **A standalone page embeds the icon inline** (the SVG is about 1.2 KB, as a `data:` URI or an
  inline `<svg>`) so it still works when saved, emailed or moved. The local web UI serves the
  files straight from `branding/` in the package, with no second copy. A page never links to `site/assets/` or to a path outside itself.
- **One set of colour tokens**, defined once on `:root` and redefined for dark mode, taken from
  the landing page:

  | Role | Light | Dark |
  | --- | --- | --- |
  | Background | `#fdf6e3` cream | `#11143a` |
  | Surface | `#ffffff` | `#1b1f4b` |
  | Text and rules | `#1b1f4b` navy | `#fdf6e3` |
  | Muted text | `#4a4f7a` | `#b4b9e6` |
  | Accent fill (buttons, rules) | `#0e8f96` teal | `#38c9d0` |
  | Accent text (links, small labels) | `#0a6e74` darker teal | `#38c9d0` |
  | Secondary | `#c4207f` pink | `#ff7cc0` |
  | Header band | `#ffd23f` sun yellow with a navy rule | same |

  Fit and status colours come from the gauge on the icon (red, orange, yellow, light green,
  green). **Colour is never the only signal:** a rating always carries its word, and a status its
  text.
- **Contrast is part of the decision.** The landing page's teal (`#0e8f96`) is only 3.6:1 on the
  cream background, below the 4.5:1 that body-size text needs, and white on that teal is 3.9:1. So
  teal is for fills, borders and large text, and small text and links use the darker teal
  (`#0a6e74`, about 5.6:1 on cream, 6.0:1 with white on it) or navy (14.5:1). This is also a fix
  for the landing page, which uses the lighter teal for links.
- **Behaviour the pages share**: `prefers-color-scheme` dark mode, with the explicit
  `data-theme` override the landing page already has; usable at narrow widths; visible keyboard
  focus; every control labelled; no animation beyond `prefers-reduced-motion`.

### 4. Tests keep the pages honest

- The embedded icon in each standalone page is byte-identical to the original (the same idea as
  `tests/test_site_assets.py`).
- Every page, and the web UI's stylesheet, declares the same colour tokens.
- No template, stylesheet or vendored script references an external origin, except the links a
  person clicks (a course link opens Pluralsight; nothing is fetched). The SVG namespace string
  is the one allowed exception, and it is not requested.
- No template uses `|safe` or turns escaping off, and a posting containing `<script>` is shown as
  text.
- The vendored HTMX file is the pinned version.
- Rendered pages are checked with Flask's test client: **Apply** is absent until a dry run is
  shown, an override box starts unticked, a status change to `applied` asks for confirmation,
  and every form control has a label.
- The Pluralsight page's `FORMAT` and `VERSION` equal those in
  `learning/adapters/pluralsight_json.py`, which replaces the comment as the safeguard.
- The local web UI's tool list is checked against the MCP server's, so the two cannot drift
  apart on what the gate covers.
- A request without the session cookie, with a foreign `Host`, or a `POST` with a foreign
  `Origin` or no form token, is refused; the launch token works once; the debugger is off.

## Considered and rejected

- **A hosted web app.** The pages handle a personal profile and job postings; they stay on the
  machine ([ADR 0013](0013-code-and-vault-split-into-two-repos.md)).
- **MCP over streamable HTTP with a browser as the client.** It would put every tool on the
  network with the authentication gap ADR 0004 declined, for a result the adapter above gets
  without changing the MCP server.
- **React (with TypeScript and Vite).** It was chosen in an earlier draft of this record. It
  gives a component model, but needs Node, a second language, a JSON API between the two,
  committed build output and a CI rebuild check, and a large npm tree, for two pages and one
  user. Dropped for Flask.
- **The standard library alone, rendering HTML by hand.** No dependency, but no routing or
  templating, and every pasted posting would have to be escaped by hand.
- **NiceGUI.** Closest of the Python UI frameworks, but it has its own Material look and a
  WebSocket layer, and its default requests to other origins and its `Origin` handling were not
  checked. Not chosen; it can be revisited if Flask and HTMX prove too much code.
- **Streamlit, Reflex and Flet.** Streamlit's rerun model and own server do not fit a gated
  "dry run, then Apply" flow or our guards. Reflex needs Node anyway, and Flet brings a Flutter
  runtime.
- **FastAPI.** No need for async or generated API documents (the Swagger page was dropped), and
  it adds an ASGI server.
- **Only standalone pages.** They cannot run the gated tools or read the vault.
- **A desktop shell (Electron or similar).** A large dependency for a browser tab.

## Consequences

- **This is the project's first network listener.** It is loopback-only, opt-in and short-lived,
  but the claim "zero network attack surface" in ADR 0004 now applies to the MCP server only, and
  this command carries the guards above.
- **A third way in to keep level with the other two.** The tool list, the gate and the access
  policy must match; the test above is the guard, and a new MCP tool does not appear in the web UI
  until someone adds it.
- **Brand files stay in two places** (`branding/` and `site/assets/`), now with a third consumer
  that embeds one. The tests above are what keep the copies equal.
- **No Node, so `CLAUDE.md` stays true.** There is still no Node.js dependency. The cost is the
  other way: the screens are less interactive than a single-page app, and anything that needs
  rich client-side behaviour (drag and drop, live charts) would be awkward. Neither is needed for
  the pages in 2b. If that changes, this record is revisited rather than worked around.
- **One more Python dependency, and one vendored script.** Flask brings Werkzeug, Jinja2,
  MarkupSafe, itsdangerous, click and blinker. They are an optional extra, pinned in the lock
  file and in the lock check the setup page already has, and HTMX is a single file in the
  package. That is a small surface for a tool that handles personal data, and far smaller than an
  npm tree.
- **The setup documents must mention the extra.** ADR 0026's tests keep the setup page in step,
  so `docs/setup.md` (Part 3, optional extras), `requirements-lock.txt` and the MCP and README
  quick starts are updated with it, not left to drift.
- **Document downloads make the web UI a way to produce a resume**, so the gate, the page budget
  and the rule on protected-characteristic information in `CLAUDE.md` apply to it as to every
  other generator, and a self-identification question still has to be asked per posting. The page
  asks it; it does not assume an answer.

## Follow-ups

In this order:

1. **ADR 0028**: done. The commands return structured results; the web UI calls `run()` and
   renders the result (the console renderer in `jobomatic.results` is the model for a page).
2. **Restyle the Pluralsight import page** to the shared tokens, the inline gauge icon and the
   tests in section 4. It is blue today and has no mark, so it contradicts this record until it
   is changed. The change is cosmetic: layout, parsing and the import file are untouched.
3. **Fix the teal on the landing page** (`site/index.html`). It uses `#0e8f96` (3.6:1 on cream)
   for links and small text, which is below the 4.5:1 this record requires; links move to the
   darker teal and the lighter one stays on fills and borders. Until then the landing page and the
   web pages disagree.
4. **Add the `web` extra**: Flask in `pyproject.toml`, the lock file, `docs/setup.md` and the
   quick starts, and the extra in the CI install of
   [ADR 0033](0033-python-version-support-and-ci-matrix.md)'s matrix.
5. **Build `jobo web`**: the app, its guards and their tests first, then the two pages in 2b,
   then the rest.

## Decided with this record

- The command is `jobo web`.
- The first version includes document downloads.
- The web UI is built on the structured results of ADR 0028, not on the MCP tool functions.
- The web UI is **Flask with Jinja templates and HTMX**, a Python-only stack in an optional `web`
  extra. React and the Python UI frameworks were weighed and are listed under "Considered and
  rejected".
