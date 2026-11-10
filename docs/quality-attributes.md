# Quality attributes

What this system optimizes for, stated plainly rather than left to be reverse-engineered from code
and CI config. The decisions behind each one are in [adr/](adr/). What the tool does and does not
guarantee about its documents is in [TRUTHFULNESS.md](TRUTHFULNESS.md) and [LIMITS.md](LIMITS.md);
how personal data is handled is in [PRIVACY.md](PRIVACY.md).

## Determinism and reproducibility

The core commands make no language-model calls: parsing a posting, rating the fit, the gate, and
building DOCX and PDF files are plain Python ([ADR 0001](adr/0001-deterministic-fit-engine.md)). The
same posting against the same profile gives the same rating, the same rationale text and the same
document content. That is what makes the test suite meaningful: tests check real behaviour, not
mocked model answers. The optional exceptions (local embeddings, and the `--explain` option) are
listed in [LIMITS.md](LIMITS.md).

## Security and data privacy

- **No network exposure.** The MCP server speaks only stdio ([ADR 0004](adr/0004-stdio-only-transport.md)).
  No port is bound, so there is no authentication surface to build or forget.
- **Personal data stays out of this repo.** It lives in a separate private repo (the vault), and
  the container image holds code only ([ADR 0005](adr/0005-container-data-via-bind-mount.md),
  [ADR 0013](adr/0013-code-and-vault-split-into-two-repos.md)). [PRIVACY.md](PRIVACY.md) lists what
  is checked on every commit.
- **Visibility is declared in the model.** The public view of the profile can contain only fields
  marked public ([ADR 0018](adr/0018-visibility-declared-in-the-model.md)), and a guard scans that
  text for personal data before it is printed.
- **No encryption at rest** beyond the vault being a private repo. Tools such
  as `age` were considered and deliberately deferred.

## Testing and CI gates

- `pytest` runs the whole suite against fictional fixtures and the real profile-loading and
  fit-rating code, not mocks of it. Test counts are not written here because they go stale; run
  `pytest --collect-only -q` for the current number.
- `ruff check` and `ruff format --check`, `mypy src` and `lint-imports` (the architecture rules in
  [architecture.md](architecture.md#rules-that-are-checked)) run in CI and in the local pre-commit
  hook, so they are enforced on every commit and every pull request.
- CI has no access to the private vault, so it uses a throwaway vault built from fictional data.
  The checks that need the real vault (`profile validate`, the hardcoded-facts scan) run in the hook.

## Operational model

- **Single user, single machine, no SLA.** This is a personal tool, not a service. "Availability"
  means the machine the candidate is using is on, which is why the same-machine container design was
  chosen over an always-on host ([ADR 0004](adr/0004-stdio-only-transport.md)).
- **No horizontal scaling and none needed.** Every operation is a local computation over a profile
  measured in tens of kilobytes.
- **Rebuild versus live edit is explicit.** The container image is rebuilt only when dependencies
  change. The vault is mounted, so data edits reach the running container at once
  ([ADR 0005](adr/0005-container-data-via-bind-mount.md)).

## Known deferred work

Recorded here so that revisiting any of these is a decision, not a rediscovery.

- A network-reachable MCP server needs an authentication story first
  ([ADR 0004](adr/0004-stdio-only-transport.md)).
- Encryption at rest for the vault was researched and not implemented.
- The fit-rating thresholds are starting values until enough application outcomes are recorded
  ([ADR 0021](adr/0021-fit-rating-weights-core-requirements.md),
  [Fit-Calibration-Plan.md](Fit-Calibration-Plan.md)).
