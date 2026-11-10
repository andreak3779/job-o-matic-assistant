# 0010 — Applications log: tracked, append-only, and "applied" is explicit

**Status:** Accepted

## Context

The skills told Claude to ask "have you already applied to this exact posting?"
from memory, because the application tracker was a spreadsheet outside the
repo. Companies re-post requisitions, and a cold re-application a few days
later reads as a duplicate. The repo is used on two laptops, so whatever
records applications has to agree on both — a per-machine file would miss
anything applied from the other one.

## Decision

`src/jobomatic/applications/` keeps an **append-only event log**,
`applications/applications.jsonl` in the private vault (originally `project-1-application-engine/data/applications.jsonl`), one JSON event per
line (`create` / `update`), tracked in git. Current state is a fold over the
events in timestamp order. Nothing is ever rewritten, so two machines that
each add lines merge cleanly: `.gitattributes` marks the file `merge=union`
(keep both sides' lines), and the fold gives the same answer everywhere
regardless of line order.

Statuses: `drafted`, `applied`, `phone_screen`, `technical`, `offer`,
`rejected`, `withdrawn`.

**Generating documents never marks a posting applied.** The generators for
`generate-resume`, `generate-cover-letter` and `generate-job-site` record only a
`drafted` entry (or add document kinds to the existing one); since
[ADR 0015](0015-single-outputs-hierarchy.md) they do so just before building the
document, because the entry's id names the folder it goes in.
`applied` is set only by an explicit call — `applications applied`, or the
`applications_mark_applied` tool, which is described as "only when the user
has said they submitted it". Thank-you letters, interview prep and cold
outreach never touch the log.

The duplicate check (`check_posting`) matches on company plus job ID, or
company plus title when IDs are missing. It returns `duplicate` (submitted
within 60 days — blocking), `repeat` (older), `drafted`, `related` (same
company, other role) or `new`, and flags a no-response pattern (2+ unanswered
applications to one company). The MCP gate refuses a `duplicate` on resume,
cover letter, application-documents and job-site letter unless
`confirm_reapply=true` is passed after the user says so. It deliberately does
**not** gate thank-you letters or interview prep: those only make sense after
an application exists.

## Consequences

- The log names companies applied to. That is tracked in the private repo on
  purpose (the user chose sync over secrecy); it is excluded from container
  images (`.containerignore`) and from client-supplied MCP paths.
- Malformed lines, unknown fields, unknown statuses and bad dates fail loudly
  with the line number (ADR [0007](0007-fail-loud-on-malformed-input.md));
  a corrupt log stops generation rather than being silently ignored.
- `parse_jd` returns "Unknown Company" for postings it cannot read; those
  never match anything (otherwise every unreadable posting would look like the
  same posting) and are not recorded.
- Matching is heuristic. A different title at the same company is `related`,
  not a duplicate, and two postings with the same title but different job IDs
  are different postings. A re-titled req with no job ID can slip through.
- `applications import-csv` brings in a spreadsheet tracker export. It is
  idempotent, refuses to guess ambiguous dates (`04/05/2026`) or unknown
  statuses, and reports each bad row instead of dropping it silently.
- Tests never touch the real log: an autouse fixture in `tests/conftest.py`
  points `CLAUDE_JOBS_APPLICATIONS_LOG` and `CLAUDE_JOBS_PRIVATE_DIR` at
  throwaway directories.
