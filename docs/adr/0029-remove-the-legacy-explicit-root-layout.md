# 0029 — Remove the legacy explicit-root layout from the path module and the commands

**Status:** Accepted.

## Context

[ADR 0013](0013-code-and-vault-split-into-two-repos.md) says one module, `paths.py`, decides where
personal data lives. It still carries a second mode from before the split: a caller may pass an
explicit `root`, and any root that is not this checkout is "used as given, in the old project-2
layout". Two ways to locate data means two paths to test, and a reader cannot tell which one is
live.

What was found when this was investigated (counts are of the tracked code at the time of writing):

- **`paths.py`**: `outputs_dir`, `profile_dir`, `star_bank_path` and `output_dir` take a `root`;
  `_is_default_root` decides which layout applies; `_LEGACY_PROFILE_DIR` names a
  `project-2-profile-learning-hub` folder. `star_bank_path` has **no caller in the code**: the
  story bank is `stories.yaml`, reached through the profile repository.
- **Plumbing**: `root` is passed through `bootstrap.profile_repository`, `load_profile`,
  `load_presence_view` and `retrieval_chunks`; through `locate_application` and
  `_unlogged_folder` in `applications/outputs.py`; through `resume_freshness_lines` and the
  `_build_draft` helpers of four presence generators; and through eight generator functions in six
  command modules. Seven commands (`fit-check`, `generate-resume`, `generate-cover-letter`,
  `generate-cold-call`, `generate-thank-you`, `generate-job-site`, `interview-prep`) have a
  `--root` option and an `args.root or ROOT` default; eight command modules define their own
  `ROOT` constant.
- **Every production caller already means "the vault".** The commands pass the code root, which
  `_is_default_root` treats as "use the vault", and the presence generators pass the code root for
  the same reason. No real run reaches the old layout. A user who passed some other directory to
  `--root` would be pointed at a layout that no longer exists, and `--root` is not mentioned in the
  README, the setup pages, the skills or the scripts.
- **The tests already do not need it.** An autouse fixture in `tests/conftest.py` gives every
  test a throwaway copy of the demo vault, and `tmp_vault` makes an empty one. What still uses a
  root: 41 `root=tmp_path` call sites (31 in `test_interview_prep.py`, 6 in
  `test_thank_you_letter.py`, 4 in `test_cold_call_letter.py`), `test_resume_freshness.py`
  (builds the old folder names by hand), one test in `test_paths.py`, and one `monkeypatch` of a
  command's `ROOT` in `test_gap_analysis.py`.

The per-file overrides `CLAUDE_JOBS_PRIVATE_DIR` and `CLAUDE_JOBS_APPLICATIONS_LOG` are a
different thing. They do not select a layout; they move one file or folder. They are used by the
autouse test fixture, by `scripts/setup.sh` and `scripts/check-setup.sh` (which unset them), by
`scripts/golden_outputs.py` and by the container.

## Decision

**Delete the explicit-root mode.** There is one way to locate data: the vault.

- `paths.py` loses the `root` argument from `outputs_dir`, `profile_dir` and `output_dir`, and
  loses `_is_default_root`, `_LEGACY_PROFILE_DIR` and `star_bank_path`. The module docstring drops
  the paragraph about explicit roots.
- `root` is removed from the plumbing listed above, and `--root` and the per-module
  `ROOT` constants are removed from the seven commands. The presence modules keep
  `ROOT = paths.code_root()`, which is where the skill templates are (code, not data), but no
  longer hand it to functions as a data root.
- Tests use the vault fixtures they already have:
  - the `root=tmp_path` call sites drop the argument; the generators write to the test's demo
    vault, or to the `out_path` the test already passes;
  - `test_resume_freshness.py` builds its files in `tmp_vault` (`profile/` and `outputs/templates/`);
  - the gap-analysis test for a missing profile points the vault at one with no profile;
  - the explicit-root test in `test_paths.py` and the `star_bank_path` assertion are deleted.
- A test fails if `paths.py` gains a `root` parameter again, or if a command defines `--root`
  (the second is covered by the commands' own parser tests).

**The per-file overrides stay**, unchanged, and are not part of this record. They are the
container's and the test fixture's way to place one file, they work with a vault, and renaming
them was done in [ADR 0030](0030-finish-the-claude-jobs-rename.md). The `paths.py` docstring says
that they are overrides, not a second layout.

## Considered and rejected

- **Keep the explicit root behind one clearly named test-only function.** It would keep the old
  folder names alive for a mode no test needs, and the autouse vault fixture already gives each
  test the isolation the root provided.
- **Leave it.** Both layouts keep being tested and a reader still cannot tell which one is live.

## Consequences

- **`--root` disappears from seven commands.** `argparse` will now reject it. Nothing documents
  it, and for any directory other than the vault it could not have worked, so the visible change
  is small; the project is pre-1.0 ([ADR 0026](0026-guided-setup-and-pre-1-0-status.md)).
- **No change for a real run.** Every production path already resolved to the vault.
- **Some tests now write into their demo-vault copy** instead of `tmp_path/outputs`. That copy is
  per test and thrown away; a test that asserted on a path under `tmp_path` is changed to read the
  returned path.
- **Smaller, simpler command signatures** for [ADR 0028](0028-structured-command-results-for-cli-and-mcp.md),
  which changes the same seven modules next, and no dead `root` parameter to carry over.

## Follow-ups

- `--star-bank-path` on `interview-prep` and `star_bank_path()` in `paths.py` were removed in the
  same change, and the `interview_prep` skill no longer mentions the option. That skill still names
  `profile/star-bank.md` in several places although the story bank is `stories.yaml`; correcting
  the skill text is separate work.
- [ADR 0030](0030-finish-the-claude-jobs-rename.md) renamed the per-file override variables to
  `JOBOMATIC_PRIVATE_DIR` and `JOBOMATIC_APPLICATIONS_LOG`. It also records a correction to this
  record: the container does not use the overrides (the image sets only `JOBOMATIC_VAULT`).
