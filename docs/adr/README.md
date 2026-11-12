# Architecture Decision Records

Short records of the decisions that shape job-o-matic-assistant, in the order they
were made. Each follows the same shape: Context (the problem, as it was
actually encountered), Decision, Consequences (including the ones we
accepted rather than solved).

**Older paths.** Records written before the November 2026 restructure name files by their earlier
locations. Today `mcp_server/` is `src/jobomatic/interfaces/mcp/`, `shared/` and the three
`project-*` folders are modules under `src/jobomatic/`, the skills are in `skills/`, and the
command `claude-jobs` is `jobo`. ADR [0016](0016-modular-monolith-ports-and-adapters.md) describes
the current layout. A record is not rewritten after the fact; where a decision was replaced, its
status below says so.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-deterministic-fit-engine.md) | Deterministic fit-rating engine instead of an LLM call | Accepted |
| [0002](0002-mcp-thin-adapter-over-cli.md) | MCP server is a thin adapter over the CLI, not independent logic | Accepted |
| [0003](0003-fit-gate-enforced-at-mcp-boundary.md) | Fit gate enforced in code at the MCP boundary | Accepted; now enforced in `gate.py` for both interfaces |
| [0004](0004-stdio-only-transport.md) | stdio transport only — no network-facing MCP server | Accepted (revisit if a LAN setup is built) |
| [0005](0005-container-data-via-bind-mount.md) | Container built from code only; personal data reaches it via bind mount | Accepted |
| [0006](0006-separate-project-domains.md) | Three separate project domains instead of one flat structure | Superseded by [0016](0016-modular-monolith-ports-and-adapters.md) |
| [0007](0007-fail-loud-on-malformed-input.md) | Fail loud on malformed input; never silent fallback | Accepted |
| [0008](0008-location-eligibility-in-fit-rating.md) | Location and work-arrangement rules are part of the fit rating | Accepted |
| [0009](0009-skill-terms-from-sentence-bullets.md) | Sentence-style JD bullets are scored by extracting skill terms | Accepted |
| [0010](0010-applications-log-event-sourced-explicit-applied.md) | Applications log is tracked and append-only; "applied" is only ever set explicitly | Accepted |
| [0011](0011-salary-screen-flag-not-pass.md) | Salary screen is a flag the user confirms past, not a Pass; minimums stay private | Accepted |
| [0012](0012-evidence-retrieval-advisory.md) | Evidence retrieval (embeddings + keywords) is advisory and never changes the fit rating | Accepted; implementation replaced by [0019](0019-retrieval-module-and-sqlite-index.md) |
| [0013](0013-code-and-vault-split-into-two-repos.md) | Code and personal data live in two repos (private vault + code repo) | Accepted |
| [0014](0014-typed-profile-store-and-rag-index-replace-bundles.md) | A typed profile store plus a retrieval index replace bundles | Accepted |
| [0015](0015-single-outputs-hierarchy.md) | One outputs hierarchy, built by one module | Accepted |
| [0016](0016-modular-monolith-ports-and-adapters.md) | Modular monolith built as ports and adapters | Accepted |
| [0017](0017-learning-import-pipeline.md) | Learning history comes from imports, not hand-kept markdown | Accepted |
| [0018](0018-visibility-declared-in-the-model.md) | Visibility is declared in the model, not repeated in the data | Accepted |
| [0019](0019-retrieval-module-and-sqlite-index.md) | Retrieval is its own module, with a SQLite index (FTS5 + sqlite-vec) and a pure scoring function | Accepted |
| [0020](0020-mcp-server-for-claude-desktop.md) | The MCP server for Claude Desktop: a written access policy, evidence without private prose, skills as prompts | Accepted |
| [0021](0021-fit-rating-weights-core-requirements.md) | The fit rating weights core requirements over tail ones, adds a "Worth a try" tier, and lets the user confirm past the gate | Proposed |
| [0022](0022-umbrella-skills-scored-by-their-parts.md) | Umbrella skills such as AI are scored by evidence in their parts | Accepted |
| [0023](0023-soft-skills-are-a-separate-unscored-block.md) | Soft skills are a separate block that is listed but not scored | Accepted |
| [0024](0024-resume-page-budget.md) | The deterministic resume is trimmed to a page budget, and real pages are measured on request | Accepted |
| [0025](0025-simple-web-ui.md) | Simple web UI: standalone pages plus a local, loopback-only web UI for the MCP tools, all in the job-o-matic look | Proposed (the Pluralsight import page exists; the brand pass and the local UI are not built; waits for [0028](0028-structured-command-results-for-cli-and-mcp.md)) |
| [0026](0026-guided-setup-and-pre-1-0-status.md) | Setup is one guided path with scripts, and the project says it is pre-1.0 | Accepted |
| [0027](0027-relative-paths-resolve-against-the-current-folder.md) | Relative paths resolve against the current folder, and the error says where it looked | Accepted |
| [0028](0028-structured-command-results-for-cli-and-mcp.md) | Commands return structured results that the CLI and the MCP server render, instead of the MCP server reading printed output | Proposed (problem statement only) |
| [0029](0029-remove-the-legacy-explicit-root-layout.md) | Remove the legacy explicit-root layout from the path module and the commands | Proposed (decision drafted; not built) |
| [0030](0030-finish-the-claude-jobs-rename.md) | Finish the rename from claude-jobs to job-o-matic: command alias, environment variables, docstrings | Proposed (problem statement only) |
| [0031](0031-one-canonical-skills-location.md) | One canonical location for the skills, so the MCP server does not depend on symlinks | Proposed (problem statement only) |
| [0032](0032-tiered-git-hooks.md) | Tiered git hooks: a fast check on commit, the full suite on push and in CI | Proposed (problem statement only) |
| [0033](0033-python-version-support-and-ci-matrix.md) | Which Python versions are supported, and what CI tests | Proposed (problem statement only) |
