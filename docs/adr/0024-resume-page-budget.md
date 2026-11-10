# 0024 — The deterministic resume is trimmed to a page budget, and real pages are measured on request

**Status:** Accepted. Built after `generate-resume` produced 7 to 8 pages for a real profile against
a limit of two.

## Context

A resume is at most two pages and a cover letter exactly one (CLAUDE.md). The tailored documents
Claude writes as JSON and lays out with `render` are checked by eye and by a page count. The
deterministic `generate-resume` is different: it builds the content from the profile by rule and
emitted every skill category and every bullet of every role, so a profile with six roles came out
at 7 to 8 pages. The Node templates this repo replaced had the same gap. Their page control was a
trim order in a comment that Claude followed by hand.

## Decision

1. **Trim by a budget, in a fixed order** (`jobomatic.documents.pagefit`, pure, no LibreOffice).
   At most seven skill lines; long skill lists shortened, never inside a parenthesis; then bullets,
   dropping the last (least relevant, since they are ordered by relevance) one of a role. A
   self-directed role (no employer) gives up bullets first, then the oldest employer. The three most
   recent roles are protected longest and never go below two bullets. A role is never dropped. If
   the content still does not fit, the command refuses with the reason instead of writing a long
   resume (fail loudly, [0007](0007-fail-loud-on-malformed-input.md)).
2. **Fit is an estimate.** The height is computed from the layout the DOCX renderer produces and
   multiplied by a calibration factor measured against LibreOffice (the raw estimate ran 1 to 5%
   low), with a 3% safety margin. The calibration is a fact about the current layout: change the
   fonts or margins and it must be measured again.
3. **Real pages are measured only when asked.** `--check-pages` on `generate-resume`,
   `generate-cover-letter`, the two platform documents and `render` converts the DOCX with
   LibreOffice and counts the pages of the PDF (`PageCounter` port, `LibreOfficePageCounter`
   adapter). Over the limit, or no working LibreOffice, exits 1 and keeps the file. It is not the
   default because it needs LibreOffice and takes a few seconds, and CI and a fresh clone have
   neither.

The adapter tries each converter it finds, in order (`soffice` or `libreoffice` on the PATH, then
the Flatpak), until one makes a PDF. `JOBOMATIC_LIBREOFFICE` overrides that: `flatpak` uses only the
Flatpak, any other value is the one command or path to use, and a value that cannot be found is an
error rather than a fallback. A tool on the PATH is not a working one: a distro's `libreoffice-common` alone installs
`soffice` without the Writer module.

## Consequences

- The deterministic resume is a usable first draft again, still not as tailored as the document
  written for the posting; the skill keeps that path as the deliverable.
- The estimate can be wrong for unusual content (very long headers or links). `--check-pages` is the
  authority; the estimate only decides what to trim.
- Trimming is by position and relevance order, not by reading the posting again: a role that matters
  a lot to one posting but sits low in the profile loses bullets like any other old role.
