# 0036 — The resume has a Selected Projects section, with pinned projects

**Status:** Accepted. Built.

## Context

The resume had no place for projects. The profile filed portfolio work as bullets under a
self-directed role, "Professional Development & Portfolio Building", and `generate-resume` kept the
four most relevant bullets of every role. So a project appeared only if its bullet happened to
outrank that role's course bullets for the posting. In practice the candidate's most recent AI-assisted
work (this toolkit, with its MCP server and Claude Code skills) was on none of the last four resumes
that were checked, and CookingTime on two. A posting that does not mention AI pushed the AI work out.

The candidate wants the AI skills and experience on the resume whatever the posting says, and a
real, visible place for it.

## Decision

1. **A Selected Projects section** between Technical Skills and Professional Experience. It is
   optional: an empty list draws no heading. `TailoredResume.projects` defaults to empty, so a
   resume written before this still parses and renders as it did.
2. **Two profile fields on a project**, both public: `resume_bullets` (short bullets, at most
   `PROJECT_BULLETS` = 2 used, each cut to `BULLET_WORDS`) and `resume_pin`. A project with no
   `resume_bullets` is never shown.
3. **Selection** (`commands.resume._project_content`): the pinned projects first, in profile order,
   then the best match for the posting by the same alias-aware relevance score the bullets use,
   at most `PROJECTS` = 3 in all. A private repository shows no link. The subtitle is the first
   stack items that fit `PROJECT_SUBTITLE_CHARS`, so the link stays on the heading's line.
4. **No repeats.** A bullet of the self-directed role that names a shown project is left out of
   that role. Employers' bullets are never touched. This is done when the resume is built, not by
   editing the profile, because the same role bullets also feed the cover letter and the
   presence drafts.
5. **Page budget** (`pagefit`, extends ADR 0024). The section is part of the height estimate. In the
   trim order the projects beyond the second (the unpinned ones) go after the roles are down to
   three bullets, and before an older role is cut to two. Pinned projects are cut only after every
   other step: one bullet each, then one project. The roles give up bullets first, but never below
   their floors.

## Consequences

- Measured on six real postings (LibreOffice, two pages each): with both pinned projects the three
  most recent roles keep two or three bullets and older roles two, against up to four before. That
  is the price of the section, and the candidate accepted it. Pinning a third project would cost
  more.
- The public profile hash changes when a project gains these fields, so earlier presence drafts
  read as stale and are regenerated. LinkedIn's raw inputs list the new fields.
- The calibration in `pagefit` (ADR 0024) is a fact about the layout. The new heading and lines use
  the same constants, and the estimate was within 0.1 page of the real count on every posting
  measured; recalibrate if the section's spacing changes.
- `resume_bullets` hold prose the candidate maintains by hand. Write them without counts that go
  stale (tests, coverage): the profile check only warns about learning counts.
