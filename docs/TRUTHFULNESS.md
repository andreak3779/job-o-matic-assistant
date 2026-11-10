# How the tool keeps documents truthful

A résumé or cover letter that claims something untrue is worse than none. This page lists the
controls that keep generated documents tied to what is true, where each one lives, and the tests
that check it. It also says what the tool cannot guarantee, because those are the parts you must
check by hand before sending anything.

## 1. Every claim starts from one validated profile

Generators read a typed profile, not free text and not an old export. The profile is YAML in the
private vault, loaded into typed models (`src/jobomatic/profile/`), and `jobo profile validate`
runs its consistency checks, including a warning when a count written in the profile text no longer
matches the imported learning data. Counts, hours and certification status are computed from the
data, never typed ([ADR 0017](adr/0017-learning-import-pipeline.md)); skills that use such numbers
take them from computed placeholders, and `scripts/check_skill_hardcoding.py` flags literal numbers
that have crept back in.

Tests: `tests/test_profile_model.py`, `tests/test_profile_cli.py`, `tests/test_learning.py`,
`tests/test_skill_text.py`.

## 2. Evidence is tiered, and coursework is called coursework

For each skill a posting requires, the fit engine (`src/jobomatic/fit/engine.py`) records the
strongest evidence it can find, in one of five states:

| State | Meaning | Mark |
| --- | --- | --- |
| `match` | Used in paid work on the current résumé | ✅ |
| `portfolio` | Used in a portfolio project | ✅ |
| `course` | Coursework or self-study only | 🟡 |
| `legacy` | Older work deliberately kept off the résumé | 🕰️ |
| `gap` | No evidence | 🔴 |

The cover-letter generator builds its body only from `match` and `portfolio` evidence. Coursework
and gaps are left out of the letter unless the profile explicitly tracks them as planned learning,
and they are never written as experience (`src/jobomatic/commands/cover_letter.py`). In reports, a
`course` row says "coursework or self-study", and a `legacy` row caps the overall rating at Good.

Tests: `tests/test_fit_engine.py`, `tests/test_core_requirements.py`,
`tests/test_resume_cover_letter_generators.py`, `tests/test_gap_analysis.py`.

## 3. The rating is computed, not asked for

The rating follows from counts (coverage and core requirements), so the same posting always gets
the same rating ([ADR 0001](adr/0001-deterministic-fit-engine.md),
[ADR 0021](adr/0021-fit-rating-weights-core-requirements.md)). Lines the parser cannot turn into
skills are listed under "Required lines not scored" instead of being dropped, and a result where
more than half the required skills show no evidence is flagged as low confidence, because the
posting may have been misread. Retrieval of similar evidence is advisory and never changes the
rating ([ADR 0012](adr/0012-evidence-retrieval-advisory.md)).

## 4. A gate sits in front of document generation

`jobomatic.gate` runs before a résumé or cover letter is written, for the command line and the MCP
server alike ([ADR 0003](adr/0003-fit-gate-enforced-at-mcp-boundary.md)).

| Check | Refused when | Override |
| --- | --- | --- |
| Location | The role breaks a location rule | None |
| Skills | The rating is Pass | None |
| Fit | The rating is Stretch or Worth a try | `--confirm-gaps`, after the gaps are listed |
| Duplicate | Applied to this posting inside 60 days | `--confirm-reapply` |
| Pay | Stated pay is below the private minimum | `--confirm-below-minimum` |

Tests: `tests/test_gate.py`, `tests/test_gate_interfaces.py`, `tests/test_mcp_server.py`.

## 5. "Applied" is never set automatically

Generating documents records a posting as `drafted`. Only an explicit `applications applied`
command records an application as submitted
([ADR 0010](adr/0010-applications-log-event-sourced-explicit-applied.md)). The tool never sends
anything anywhere.

Tests: `tests/test_applications.py`, `tests/test_applications_service.py`,
`tests/test_applications_cli.py`.

## 6. Protected characteristics are never added by default

No document contains self-identification information unless a posting asks for it and the person
confirms for that posting. See [RESPONSIBLE_USE.md](RESPONSIBLE_USE.md).

## 7. Outputs carry a record of how they were made

Generated files can be written with a sidecar that records the generating script, a hash of the
profile and the inputs (`src/jobomatic/provenance.py`), so a document can be traced to the data it
came from.

## What the tool cannot guarantee

- **The profile itself.** If the profile is wrong or out of date, the documents are too. Validation
  catches inconsistencies, not untruths.
- **That the parser read the posting correctly.** Postings are free text. Read the "not scored"
  list and the low-confidence note, and read the posting.
- **That wording is persuasive.** The templates are plain on purpose. The tailoring picks and
  orders true evidence; it does not write like a person.
- **That a document is right for the employer.** Check names, dates, the company, the role and the
  page count before sending anything.

Every document is a draft for the person to read and own. Nothing here removes that step.
