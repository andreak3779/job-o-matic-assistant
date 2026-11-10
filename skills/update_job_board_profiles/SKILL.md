---
name: update-job-board-profiles
description: >
  Updates the candidate's Indeed and ZipRecruiter candidate profile fields
  (headline, summary, skills, job preferences) with accurate, ready-to-paste
  content. Use when the user asks to update, refresh, or improve their Indeed
  or ZipRecruiter profile, or asks what to change on those job boards. Also
  trigger after AZ-900 or AI-200 exam results to update cert-related fields.
  Unlike LinkedIn/GitHub, these platforms publish no fixed field character
  limits — content targets are practical, not enforced. Also flags whether the
  uploaded resume file is stale relative to the current profile, since both
  platforms lean on the uploaded resume more than on typed profile fields.
---

> **Placeholders.** `<home city, province>`, `<github-user>` and `<linkedin-user>` stand for the candidate's own details. Fill them at generation time from `python -m jobomatic profile show contact` (location) and `profile show facts` (links); never write real values into this file.

# Indeed & ZipRecruiter Profile Update Skill

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

Indeed and ZipRecruiter are treated as one skill because their candidate profile
shape is nearly identical — headline, summary, skills, and job preferences, both
backed primarily by an uploaded resume rather than hand-typed experience entries
the way LinkedIn is. Content for the two platforms is shared; only job-alert/visibility
settings differ.

## Character Limits
| Field | Limit | Notes |
|---|---|---|
| Headline / Job title | ~100 chars (practical target) | Neither platform publishes a hard limit — keep it scannable in a search-results row. |
| Summary / About | ~1,000–1,500 chars (practical target) | No published cap; shorter than LinkedIn's 2,600 since these surfaces show a preview in job-search contexts. |
| Skills | ~20 tags (practical target) | No published cap; keep to the most ATS-relevant subset rather than the full LinkedIn 50. |

---

## Resume File Dependency Check — run this first

Both platforms parse an uploaded resume into most of the profile automatically.
Before writing any field content below:

1. Check the modification date of `outputs/templates/resume.docx` in the vault
   against the public profile's `generated` date (and the `last_modified` dates of
   `profile-facts.md` / `Resume_Snapshot.md` / `skills-summary.md` in Project 2).
2. If the resume file predates any of those sources, tell the user it's stale and
   offer to run the `fullstack_net_profile_resume` skill to regenerate it before
   they upload — the typed fields below only cover headline/summary/skills/preferences,
   not the parsed work history the platforms build from the resume itself.

---

## Current State vs Target (diff)

This table describes Indeed/ZipRecruiter's *live* profile state as last confirmed
by the user — this skill has no visibility into what's actually posted on either
site. Re-confirm with the user before trusting a "Current" value more than a
couple of sessions old; update this table by hand once a field has been applied.

| Field | Current (last confirmed) | Action |
|---|---|---|
| Headline / Job title | Unknown — first run of this skill | Set — see Step 1 |
| Summary / About | Unknown | Set — see Step 2 |
| Skills | Unknown | Set — see Step 3 |
| Job preferences (desired titles, types, location, salary) | Unknown | Set — see Step 4 |
| "Actively looking" / resume visibility | Unknown | Enable — see Step 4 |
| Resume file | See freshness check above | Regenerate if stale |

---

## Step 1 — Headline / Job Title
*(Indeed: Profile → Job title. ZipRecruiter: Profile → Headline.)*

```
Full-Stack .NET Developer | C# · ASP.NET Core · Angular · Azure | {cert_status_short}
```

---

## Step 2 — Summary / About
*(Indeed: Profile → Summary. ZipRecruiter: Profile → About.)*

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
| Job types | Full-time · Contract |
| Location | <home city, province> — open to remote |
| Salary expectation | Leave as "negotiable" unless the user wants a specific figure — run the `salary_research` skill rather than guessing a number here |
| "Actively looking" / resume visibility (Indeed) | Set to visible to employers |
| Job Alerts (ZipRecruiter) | Enable for: .NET Developer, Azure Developer, Full-Stack Developer — the home city / Remote (Canada) |

---

## Step 5 — Write the Draft Document

After presenting Steps 1–4 in the conversation, also write the full paste-ready
output to `outputs/profiles/job-board/<date>.md` in the vault (`python -m jobomatic generate-job-board` writes the same file)
(create it if missing, overwrite if present — it's a generated draft, not
hand-maintained).

1. Include all of Steps 1–4 verbatim (fragments substituted) for both Indeed
   and ZipRecruiter — the file is the deliverable, not a pointer back to this skill.
2. Include the result of the Resume File Dependency Check above, even if the
   resume was found current — don't silently omit the check.
3. Head the file with an HTML comment noting it's generated and which
   the public profile data it reflects, e.g.:
   ```
   <!-- GENERATED DRAFT — regenerate by running the update-job-board-profiles skill.
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
| Headline | Add "· AI-200 Certified" |
| Summary | Replace "actively working toward AI-200" paragraph with certified language |
| Job Alerts / preferences | No change needed |
