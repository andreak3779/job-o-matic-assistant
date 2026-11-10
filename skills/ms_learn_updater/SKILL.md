---
name: ms-learn-updater
description: >
  Imports the candidate's completed Microsoft Learn modules, learning paths, certifications and
  applied skills into the learning data. Trigger when the user says things like "I finished a new
  Microsoft Learn module", "update my MS Learn data", "sync my MS Learn transcript", "I completed
  another Microsoft Learn learning path", or provides a new Microsoft Learn transcript file. Do
  NOT use this skill for Pluralsight updates; those go through pluralsight-updater.
---

# Microsoft Learn Transcript Updater

Completed Learn modules and learning paths live as items in `profile/learning/items.yaml` in the
vault. The source is the transcript share link's JSON. There is no hand-kept list and no
hand-kept count.

## The network rule (the user's own)

**Contact Microsoft only when the user explicitly asks for a transcript refresh.** Every other
command, skill and workflow reads the saved copy in the vault's `imports/mslearn/` and makes no
network call. Never refresh on your own, never schedule a refresh, and never suggest one
unprompted.

## Workflow A: the user asks for a refresh

1. **Dry run:** `python -m jobomatic learning import --mslearn`
   The share id is read from the vault's `private/sources.yaml` (key `mslearn_share_id`); if it is
   missing the command says so. The response is validated against a JSON Schema (if Microsoft
   changed it, the import stops with "Nothing was imported"), and the owner's name and email are
   dropped before anything is saved.
2. **Show the user the diff:** new items, changed fields, and the credentials the transcript
   reports. The command compares passed exams with the profile's certifications and prints a
   `note:` for any mismatch. It never edits the profile; offer to update `certifications.yaml`
   and wait for a yes.
3. **On the user's yes,** run the same command with `--apply`. The cleaned response is kept as
   `imports/mslearn/<date>.json`.

## Workflow B: the user gives a transcript file

`python -m jobomatic learning import <file.json>` (add `--apply` after the diff is
confirmed). No network is used. Owner fields are removed before the copy is kept.

## Workflow C: no refresh requested

Report from what is saved: `learning list --provider mslearn`, `learning stats`. If the user
mentions a module they just finished, say it will appear at their next refresh and ask whether
they want one now. Do not refresh without a yes.

## Filling the gaps

Paths come without a link, and a few modules have none. Public Learn pages fill most of them:

1. `python -m jobomatic learning enrich` confirms each path's page by its uid, saves its
   link, ties modules to their path, and caches the pages. It lists the paths it could not
   confirm. (It reads public pages, not the user's transcript.)
2. For an item still without a link (typically retired modules), look it up by **exact title**
   with the Microsoft Learn MCP server (`microsoft_docs_search`, then `microsoft_docs_fetch`),
   falling back to web search. **Propose** the link to the user and wait. Never save a guess.
3. On a yes: `python -m jobomatic learning set-url <item-id> <https-url>`. Each title is
   searched once; the saved link is reused.
4. Anything still unmatched stays listed in the import report. Nothing is estimated.

Microsoft's descriptions are stored as `summary_source: provider`. They are fine in the private
vault; paraphrase them in resume or LinkedIn text.

## Downstream notes

- A newly passed exam or certification: remind the user to update `certifications.yaml` and run
  `python -m jobomatic profile validate`.
- Pluralsight and Learn overlap on GitHub Copilot and C#; do not double-count.
