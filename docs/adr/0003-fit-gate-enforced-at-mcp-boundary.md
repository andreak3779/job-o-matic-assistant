# 0003 — Fit gate enforced in code at the MCP boundary

**Status:** Accepted. Amended in November 2026 (the gate moved into `gate.py`; see "Update" at the end) and [0021](0021-fit-rating-weights-core-requirements.md): the
gate now lives in `src/jobomatic/gate.py` and is run by the command line as well as the MCP server;
a Stretch or Worth a try rating can be confirmed past (`confirm_gaps`).

## Context

The `create-a-cover-letter-and-tailored-resume-for-job-description` skill
already states the rule "only generate if the fit rating is Strong or
Good" — but that's prompt-level guidance Claude follows when it's the one
deciding to invoke the skill. An MCP client (Claude Desktop, or any other
MCP-capable app) calling `generate_resume` or `generate_cover_letter`
directly skips the skill, and the rule, entirely. The rule needed to be
true regardless of who or what is calling the tool.

## Decision

The MCP server's `_require_good_fit()` (originally in `mcp_server/server.py`, now replaced by `src/jobomatic/gate.py`) re-runs the same
`parse_jd`/`rate_fit` computation the underlying scripts already do
internally, as a precondition inside `generate_resume`,
`generate_cover_letter`, and `generate_application_documents`. Below a
Good rating it raises a `ToolError` with the rating and rationale instead
of dispatching to the CLI — no document gets written, no MCP client can
work around it by calling the tool a different way.

## Consequences

- The rule is enforced identically whether Claude is following the skill's
  guidance or an MCP client is calling the tool cold — there's exactly one
  place this can be bypassed from (editing the server module itself),
  not two independent surfaces to keep in sync.
- The rating gets computed twice per gated call (once by
  `_require_good_fit()`, once more inside the generator script it then
  dispatches to) — accepted as cheap and deterministic (ADR
  [0001](0001-deterministic-fit-engine.md)) rather than worth threading a
  precomputed `FitResult` through the CLI's argv boundary.
- Test fixtures need at least one JD that genuinely rates Strong against
  the real profile bundle (`tests/fixtures/strong-fit-jd.md`) — none of the
  repo's original JD fixtures did, which was a real gap this decision
  surfaced and required fixing before the gated tests could be written.
- `generate_cold_call` and `generate_job_site_letter` are deliberately
  **not** gated this way — they're governed by different skills that don't
  carry this rule, and gating them would be inventing a constraint nobody
  asked for.

## Update (November 2026)

The gate moved out of the MCP server module into `src/jobomatic/gate.py`, and the command line
runs it before it writes anything, so the rule holds for every caller, not only MCP clients. The
MCP tools only pass the user's confirmations through.

- **Fit rating:** Strong and Good pass. Worth a try and Stretch are refused until the user says so
  (`confirm_gaps`; command line `--confirm-gaps`). A skills Pass and a location Pass can never be
  confirmed past ([0021](0021-fit-rating-weights-core-requirements.md), decision F4).
- **Also gated:** a duplicate application inside the window (`confirm_reapply`, ADR
  [0010](0010-applications-log-event-sourced-explicit-applied.md)) and stated pay below the
  minimum (`confirm_below_minimum`, ADR [0011](0011-salary-screen-flag-not-pass.md)).
- **Covers the same tools as before:** the tailored resume, cover letter and the combined tool.
  The job-site letter is gated on location and duplicates only, and cold outreach with a posting on
  location only, as before.
- A confirmation is a decision the user makes, never a default. The skill text says to set it only
  after the user says yes; as with the salary flag, a model could still set it alone, an accepted
  limit.
