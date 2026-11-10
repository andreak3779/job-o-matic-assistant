---
name: update-jobgether-profile
description: >
  Updates the candidate's Jobgether candidate profile fields (title, about/bio,
  skills, job preferences) with accurate, ready-to-paste content. Use when the
  user asks to update, refresh, or improve their Jobgether profile. Also
  trigger after AZ-900 or AI-200 exam results to update cert-related fields.
  Jobgether publishes no fixed field character limits — content targets are
  practical, not enforced. Also flags whether the uploaded resume file is
  stale relative to the current profile, since Jobgether's matching algorithm
  leans on the uploaded resume alongside the typed profile fields.
---

# Jobgether Profile Update Skill

> **Source**: run `python -m jobomatic profile show
> --public section "Copy Fragments"
> "Cert Status + Badge URLs" "Technical Skills (flat list, ATS-formatted)"`
> before regenerating any field content, and check its cert table before
> filling any cert-related field. Any `{fragment_name}` placeholder below must
> be filled from that output's **Copy Fragments** section before presenting the
> final paste-ready text — never leave a literal `{fragment_name}` in delivered
> output. If that section is missing (older profile data, pre-fragments), fall
> back to computing the value the same way the Copy Fragments rules in `src/jobomatic/profile/copy_fragments.py`
> Step 2.5 does, from `profile-facts.md` / `skills-summary.md` directly.

Jobgether is an AI-matching job board: it scores candidates against postings
using the profile fields below plus the uploaded resume, rather than surfacing
a browsable public profile the way LinkedIn does. There is no field-limit
documentation to check against here (unlike LinkedIn/GitHub) — the content
below follows the same practical, non-enforced targets used for the
Indeed/ZipRecruiter skill, since Jobgether's profile shape is close to theirs.

> ⚠️ This skill was built without a confirmed live Jobgether account to check
> field names/limits against — verify the field labels below still match
> Jobgether's current profile UI the first time you use this skill, and note
> any mismatch back into this file so future runs stay accurate.

## Character Limits
| Field | Limit | Notes |
|---|---|---|
| Title / Headline | ~100 chars (practical target) | No published hard limit — keep it scannable in a match-results card. |
| About / Bio | ~1,000–1,500 chars (practical target) | No published cap; matches the Indeed/ZipRecruiter summary target. |
| Skills | ~20 tags (practical target) | No published cap; keep to the most ATS/match-relevant subset. |

---

## Resume File Dependency Check — run this first

Jobgether's matching algorithm scores against the uploaded resume alongside
the typed fields below. Before writing any field content:

1. Check the modification date of `outputs/templates/resume.docx` in the vault
   against the public profile's `generated` date (and the `last_modified` dates of
   `profile-facts.md` / `Resume_Snapshot.md` / `skills-summary.md` in Project 2).
2. If the resume file predates any of those sources, tell the user it's stale and
   offer to run the `fullstack_net_profile_resume` skill to regenerate it before
   they upload — a stale resume weakens Jobgether's match scoring even if the
   typed fields below are current.

---

## Current State vs Target (diff)

This table describes Jobgether's *live* profile state as last confirmed by the
user — this skill has no visibility into what's actually posted there.
Re-confirm with the user before trusting a "Current" value more than a couple
of sessions old; update this table by hand once a field has been applied.

| Field | Current (last confirmed) | Action |
|---|---|---|
| Title / Headline | Unknown — first run of this skill | Set — see Step 1 |
| About / Bio | Unknown | Set — see Step 2 |
| Skills | Unknown | Set — see Step 3 |
| Job preferences (roles, locations, employment type, salary, remote) | Unknown | Set — see Step 4 |
| Resume file | See freshness check above | Regenerate if stale |

---

## Step 1 — Title / Headline
*(Profile → Title / Current role)*

```
Full-Stack .NET Developer | C# · ASP.NET Core · Angular · Azure | {cert_status_short}
```

---

## Step 2 — About / Bio
*(Profile → About you)*

```
Full-stack developer with 10+ years of enterprise experience in C#, ASP.NET Core Web API, Entity Framework Core and Microsoft SQL Server, with Angular and TypeScript on the front end. Built ASP.NET Core APIs and Angular 12 to 14 features at Acme Software, and integrated HubSpot, Microsoft Dynamics 365 and SharePoint through a real-time C# API at Globex Industrial. CI/CD on GitLab, Azure DevOps and GitHub Actions, deployed with Docker.

{cert_status_short}. Completed training in Azure Functions, App Services, Azure Monitor, Entra ID and serverless architecture. Uses GitHub Copilot and Claude Code, and has completed {github_copilot_course_count} GitHub Copilot courses covering secure coding, CI/CD integration and AI-assisted testing.

Led legacy modernization at three employers (ASP.NET Web Forms to Angular, MS Access to ASP.NET Web Forms on SQL Server, Clipper to SQL Server), and practices TDD with xUnit and Moq.

Open to software developer and full-stack .NET roles. Remote in Canada preferred, based in <home city, province>.
```

---

## Step 3 — Skills

Curated list of about 20 tags, prioritizing the load-bearing stack and the most
recognizable single-concept terms. The full Technical Skills section runs to
several hundred terms and includes course-level skills that these platforms
would read as production experience, so it is curated rather than derived. The
generator reads this block. Revisit it when the Technical Skills section changes
materially, using the same rules as the LinkedIn skill's Step 4:

```
C#, ASP.NET Core, Angular, Microsoft Azure, CI/CD, Entity Framework Core, TypeScript,
Microsoft SQL Server, T-SQL, Azure Functions, Azure DevOps, Docker, GitHub Actions,
Git, xUnit, JWT, Microservices, GitHub Copilot, Microsoft Dynamics 365, SharePoint Online
```

---

## Step 4 — Job Preferences

| Setting | Value |
|---|---|
| Desired job titles | Full-Stack Developer · .NET Developer · Software Developer · Azure Developer |
| Employment type | Full-time · Contract |
| Location | <home city, province> — open to remote |
| Remote preference | Remote preferred |
| Salary expectation | Leave as "negotiable" unless the user wants a specific figure — run the `salary_research` skill rather than guessing a number here |
| Availability | Immediate, unless the user says otherwise |
| Matching / visibility toggle | Set to actively matching / visible to employers |

---

## Step 5 — Write the Draft Document

After presenting Steps 1–4 in the conversation, also write the full paste-ready
output to `outputs/profiles/jobgether/<date>.md` in the vault (`python -m jobomatic generate-jobgether` writes the same file)
(create it if missing, overwrite if present — it's a generated draft, not
hand-maintained).

1. Include all of Steps 1–4 verbatim (fragments substituted) — the file is the
   deliverable, not a pointer back to this skill.
2. Include the result of the Resume File Dependency Check above, even if the
   resume was found current — don't silently omit the check.
3. Head the file with an HTML comment noting it's generated and which
   the public profile data it reflects, e.g.:
   ```
   <!-- GENERATED DRAFT — regenerate by running the update-jobgether-profile skill.
        Reflects the public profile data (hash abc123def456). -->
   ```
4. End with a short "After applying" note reminding the candidate to update the
   Current State vs Target diff table above once the candidate has pasted a field in.
5. Report the file path in the completion summary so it's easy to find.

---

## Post-Exam Update Checklist
Run this checklist after AI-200 results:

| Field | AI-200 Passed |
|---|---|
| Title / Headline | Add "· AI-200 Certified" |
| About / Bio | Replace "actively working toward AI-200" paragraph with certified language |
| Job preferences | No change needed |
