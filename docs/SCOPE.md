# Scope and trade-offs

## What this is sized for

One person's job search, run on one or two laptops, with no users to support and no uptime to
keep. The structure is larger than that needs, on purpose: the project is also a place to practise
building software that stays understandable and checkable when an AI agent writes much of the
code. This page says which parts earn their place and which parts a team would drop.

## What a team setting would keep

- **The gate and its tests.** Rules that refuse an action and can be shown to refuse it.
- **The decision records.** Short, dated reasons for each non-obvious choice.
- **Typed models and validation at the edges.** Bad input fails loudly
  ([ADR 0007](adr/0007-fail-loud-on-malformed-input.md)).
- **Architecture rules checked by tool.** `lint-imports` fails a build that breaks the module
  layers, so the structure cannot erode quietly.
- **A fake-able boundary around files and services** (ports and adapters), so tests need no real
  data.

## What I would cut or simplify

- **The module count.** The number of modules and import contracts is more than a single-user
  tool needs. Two or three packages (profile and learning data, fit and gate, documents and
  interfaces) would do the same work with less ceremony.
- **The two interfaces.** The command line and the MCP server share all logic, so the cost is
  small, but a team with one real client would build only that one.
- **The separate vault repository.** It protects personal data cleanly. For a team product the
  data would live in a database or a managed store, not a second git repo.
- **The skills' volume.** Many skills overlap in intent. A shipped product would offer fewer, better
  documented workflows.

## Deliberately deferred

- Recalibrating the rating thresholds against recorded outcomes
  ([Fit-Calibration-Plan.md](Fit-Calibration-Plan.md)).
- Encryption at rest and a network-reachable server ([quality-attributes.md](quality-attributes.md)).
- Improving the plain wording of the generated letters; see [LIMITS.md](LIMITS.md).

## How this document should be used

It is my own assessment, written as the project was finished. [Edit this section in your own words
before relying on it in an interview; the cuts above are proposals drawn from the code, not
decisions already made.]
