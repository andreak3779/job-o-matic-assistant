# 0015 — One outputs hierarchy, built by one module

**Status:** Accepted

## Context

Generated files currently land in several places: `outputs/`,
`outputs/part-time/`, `outputs/outputs.bak/`, and per-project `outputs/`
folders. Names are free-form, nothing links a document to the application
it was made for, and each generator builds its own path.

## Decision

All generated files live under the vault's `outputs/` in one hierarchy:

```text
outputs/
  applications/<YYYY-MM-DD>_<company-slug>_<role-slug>/
  part-time/<YYYY-MM-DD>_<employer-slug>/
  outreach/<YYYY-MM-DD>_<recruiter-slug>/
  profiles/<platform>/<YYYY-MM-DD>.md
  learning-plans/<YYYY-MM-DD>_<slug>.pdf
  research/
  templates/
```

An application folder's name is that application's ID in
`applications.jsonl`, so the log and the documents point at each other.
One function, `paths.output_dir(kind, ...)`, builds every path, and no
generator builds its own. Generated documents are committed in the vault
repo. Files inside a folder have plain names (`resume.docx`,
`cover-letter.docx`, `gap-analysis.md`, `interview-prep.docx`,
`thank-you.docx`, `salary.md`, `top-choice.md`, `jd.md`).

Applications created from now on get a readable id
(`2026-10-31_acme-health_net-developer`, with `-2` on a clash). The 33
applications logged before this keep their random ids, because the log is
append-only; `applications.folder_name_for` builds their folder name from
the date they were created, their company and their title.

Which documents write to the log follows
[ADR 0010](0010-applications-log-event-sourced-explicit-applied.md): the
resume, cover letter and job-site letter log the posting as `drafted`. Gap
analysis, interview prep and thank-you letters reuse an existing entry and
never create one. A gap-analysis folder made before any entry exists is
adopted (its date is kept) when the entry is created, so a posting still has
one folder.

## Consequences

- A one-time migration (dry-run by default, nothing deleted, unclassified
  files go to `outputs/_unsorted/`) moves the existing files.
- Folder names contain company names, which is fine in the private vault
  and is one reason none of this lives in the code repo.
- Re-generating for the same application reuses its folder instead of
  creating a new, differently named file.
- The entry is logged before the document is built, so a build that fails
  leaves a `drafted` entry with no document. Before this change it was
  logged only after success.
- Attachments need a friendlier name than `resume.docx`; a later `export`
  step can copy them out under the candidate's name.
- `learning-plans/` keeps the file names given in each plan's config for now,
  not the dated names sketched above.
