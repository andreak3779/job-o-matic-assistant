---
name: linkedin-profile-update
description: >
  Updates the candidate's LinkedIn profile fields with accurate, ready-to-paste
  content. Use when the user asks to update, refresh, or improve their LinkedIn
  profile, or asks what to change on LinkedIn. Also trigger after AZ-900 or
  AZ-204 exam results to update cert-related fields. Contains exact copy for
  every updatable field, character limits, and a diff of current vs target state.
---

> **Placeholders.** `<home city, province>`, `<github-user>` and `<linkedin-user>` stand for the candidate's own details. Fill them at generation time from `python -m jobomatic profile show contact` (location) and `profile show facts` (links); never write real values into this file.

# LinkedIn Profile Update Skill

> **Source**: run `python -m jobomatic profile show
> --public full` before
> regenerating any field content — this skill needs nearly every section
> (Copy Fragments, Headline, Cert Status, Technical Skills, Professional
> Experience, Portfolio Projects). Check its cert table before filling any
> cert-related field. Any `{fragment_name}` placeholder below must be filled
> from that output's **Copy Fragments** section before presenting the final
> paste-ready text — never leave a literal `{fragment_name}` in delivered
> output. If that section is missing (older profile data, pre-fragments),
> fall back to computing the value the same way
> the Copy Fragments rules in `src/jobomatic/profile/copy_fragments.py` Step 2.5 does, from
> `profile-facts.md` / `skills-summary.md` directly.

## Character Limits
| Field | Limit | Notes |
|---|---|---|
| Headline | 220 chars | Compute the actual length of the rendered headline at generation time — do not rely on a stored count, it drifts. |
| About | 2,600 chars | Compute the actual length of the rendered About text (Step 1, after fragments are substituted) at generation time. |
| Experience description | 2,000 chars per role | |
| Skills | 50 max; pin top 5 | LinkedIn uses controlled vocabulary — search exact term |

---

## Current State vs Target (diff)

This table describes LinkedIn's *live* profile state as last confirmed by the user —
the profile has no visibility into what's actually posted on LinkedIn, so this row set
can't self-update. Re-confirm with the user before trusting "Current" values that are
more than a couple of sessions old; update this table by hand once a field has been
applied.

| Field | Current (last confirmed) | Action |
|---|---|---|
| Headline | Matches profile headline | Replace — see Headline section below |
| About | Narrative, soft | Replace — see Step 1 |
| Open to Work banner | Unknown | Enable — see Step 2 |
| Experience — Prof Dev | Missing | Add — see Step 3 |
| Experience — existing roles (Acme Software, Globex Industrial, etc.) | Unconfirmed — may predate latest resume edits | Sync bullet-for-bullet — see Step 3.5 |
| Top Skills | GitHub, Angular CLI, HTML | Replace — see Step 4 |
| Certifications | Old MS certs only | Leave until exam passed — see Step 5 |
| Courses section | Missing | Add — see Step 6 |
| Featured section | Missing | Add — see Step 7 |
| Education | ✅ Pluralsight paths present | No change |

---

## Headline
*(Paste as plain text. Report the actual rendered character count against the 220-char
limit. The profile's own headline, `Full-Stack .NET Developer | Enterprise
Applications`, is a shorter fallback if this one needs trimming. The headline
deliberately omits "Senior" and "10+ years"; the Acme Software entry keeps the
title actually held, and the About keeps "10+ years".)*

```
Full-Stack .NET Developer | C#, ASP.NET Core, Angular, SQL Server | Azure (AZ-900) | AI-Assisted Development
```

---

## Step 1 — About Section
*(Replace entire current About. Paste as plain text. Report the actual rendered
character count against the 2,600-char limit after substituting fragments — see
Character Limits table above.)*

```
I'm a full-stack developer with 10+ years of enterprise experience in C#, ASP.NET Core Web API, Entity Framework Core and Microsoft SQL Server, with Angular and TypeScript on the front end. At Acme Software I built ASP.NET Core APIs and Angular 12 to 14 features for a benefits administration platform, wrote xUnit and Moq tests, and covered on-call production support.

A lot of my work has been modernizing legacy systems, and I've done it at three employers: ASP.NET Web Forms to Angular, MS Access to ASP.NET Web Forms on SQL Server, and a Clipper application to SQL Server. At Globex Industrial I built a real-time C#/ASP.NET Core API that fixed data mismatches between HubSpot and Dynamics 365 Sales. At Example Pharmacy I cut a drug data SSIS process from 8 hours to 1.

{cert_status_short}. I use GitHub Copilot, Claude Code and Ollama in my development work, and I've completed {github_copilot_course_count} GitHub Copilot courses and {leadership_course_count} leadership and communication courses. Two portfolio projects on GitHub show how I work: CookingTime, a legacy WinForms app rebuilt in .NET 10 Blazor with 118 automated tests, 80% coverage and a blocking CI gate, and career-fit-assistant, a Python MCP server.

Core stack:
Backend: C#, ASP.NET Core (Web API, MVC), .NET Framework, Entity Framework Core, REST API design
Frontend: Angular, TypeScript, RxJS, NgRx, Angular Material
Database: Microsoft SQL Server, T-SQL, stored procedures, query optimization, SSIS, SSRS
Cloud: Azure (Functions, App Services, Monitor, Entra ID), AZ-900 certified
DevOps and testing: GitLab CI/CD, Azure DevOps, GitHub Actions, Docker, xUnit, Moq, Jest

Open to software developer and full-stack .NET roles. Remote in Canada preferred. I'm based in the home city.
```

---

## Step 2 — Open to Work Banner
*(Profile → Open to → Finding a new job)*

| Setting | Value |
|---|---|
| Job titles | Full-Stack Developer · .NET Developer · Software Developer · Azure Developer |
| Job types | Full-time · Contract |
| Location | <home city, province> · Remote |
| Visibility | **All LinkedIn members** (maximizes recruiter reach) |

---

## Step 3 — Add Experience Entry
*(Add above Acme Software as most recent role)*

**Title:** Professional Development & Portfolio Building
**Employment type:** Self-employed
**Start:** May 2025 · **End:** Present
**Location:** <home city, province> · Remote

```
Upskilling and expanding portfolio while actively seeking a full-stack .NET developer role.

- {course_count_sentence} across Azure, ASP.NET Core, Angular, GitHub Copilot, DevOps, Python, and leadership.
- {cert_status_short}.
- Building portfolio projects on GitHub — derive the repo list and one-clause hook for each at generation time from the profile output's `## Portfolio Projects` table (name + shortest differentiator from its description), not from a fixed list, so a new or updated repo shows up automatically. Current example: "ai-job-search-workflow (Claude API + Python job-application automation), CookingTime (.NET 10 Blazor legacy migration, 118 automated tests), Resume_Site (GitHub Actions CI/CD), and awk_linux_scripts (hardware inspection + automated update/cleanup scripts)."
- Deepened GitHub Copilot expertise: enterprise deployment, AI agents, secure development, CI/CD integration, and automated test generation.
- Designed AI-assisted workflows using prompt engineering and structured instruction systems to produce gap analyses, learning plans, and tailored application documents.
```
Re-check the total against the 2,000-char limit after substituting the repo bullet — the table can grow, and the fixed example above is only a snapshot from today's profile version.

---

## Step 3.5 — Sync Existing Experience Entries
*(Keep LinkedIn's Acme Software, Globex Industrial, Example Hauling, and Example Health
entries bullet-for-bullet consistent with the resume. This is the step that closes the
drift the resume/LinkedIn comparison surfaced — Resume_Snapshot.md is the source of
truth, and LinkedIn must not fall behind it.)*

**Legacy roles:** the resume now starts at the resume-window start date by design;
The earliest employer and every earlier role were deliberately removed. If LinkedIn still
lists any legacy role, flag it to the candidate as a public, date-revealing entry that
may need manual removal or compression on LinkedIn itself — this skill only drafts
copy, it can't edit LinkedIn. Never draft sync copy for a legacy role.

The profile output's `## Professional Experience` section is rendered directly from
`Resume_Snapshot.md`'s per-employer bullets (via the profile's typed `experience` list) —
it is not a paraphrase and not hand-maintained, so it's safe to treat as the exact
target text for each LinkedIn role.

1. For every job entry in that section **other than** "Professional Development &
   Portfolio Building" (which Step 3 already owns), find the matching LinkedIn
   Experience entry by company name.
2. Output that entry's full bullet list verbatim, formatted for pasting into
   LinkedIn's role description field. Report the rendered character count against
   the 2,000-char-per-role limit (see Character Limits table) — a long role
   (e.g. Acme Software) may need trimming to fit. Trim by dropping near-duplicate
   bullets first, then the shortest (usually most generic) bullets, keeping the
   survivors in resume order — never by cutting from the bottom, which loses the
   production-support, Agile and API-integration bullets. Say how many bullets
   were dropped for each role.
3. Since this session has no visibility into what's actually posted on LinkedIn
   today, don't assume the existing entry is already in sync — present the full
   bullet list for every role each time this step runs, and let the user diff it
   against what's live rather than guessing which bullets changed.
4. If a role in the profile output has no obvious LinkedIn counterpart (a new
   employer added to the resume since LinkedIn was last touched), flag it as a
   **new** entry to add rather than an update.

---

## Step 4 — Skills
*(Skills → Add skill — search exact term; LinkedIn uses controlled vocabulary)*

**Top 5 to pin** (pin in this order for recruiter visibility — reflects the load-bearing
stack across the profile's Portfolio Projects and Cert Status, not just raw skill count):
```
1. C#
2. ASP.NET Core
3. Angular
4. Microsoft Azure
5. CI/CD
```
Re-evaluate this top 5 only if the primary tech stack changes (e.g. a new portfolio
project anchors a different language/framework) — don't reshuffle it for every profile
refresh.

**Full list to add — curated, 45 terms (50 is LinkedIn's cap, and 5 are pinned above):**
```
.NET
Entity Framework Core
Microsoft SQL Server
T-SQL
REST APIs
ASP.NET Web API
TypeScript
JavaScript
RxJS
NgRx
SQL Server Integration Services (SSIS)
SQL Server Reporting Services (SSRS)
Stored Procedures
Query Optimization
Test-Driven Development (TDD)
Unit Testing
Integration Testing
xUnit
Jest
Docker
GitLab
GitHub Actions
Azure DevOps
Azure Functions
Microsoft Entra ID
Git
GitHub Copilot
Prompt Engineering
Generative AI
Clean Architecture
SOLID Principles
Object-Oriented Programming (OOP)
Domain-Driven Design
Microservices
Service-Oriented Architecture (SOA)
OAuth
JSON Web Token (JWT)
Microsoft Dynamics 365
HubSpot
SharePoint
Agile Methodologies
Scrum
Code Review
Legacy System Modernization
Blazor
```

How this list is chosen, and when to change it:
1. Walking every category of the profile's `## Technical Skills` section yields several
   hundred terms, far over LinkedIn's 50-skill cap, so the list above is curated rather
   than dumped. The derived candidates are kept in the `.raw-inputs.json` sidecar for review.
2. Keep clean, single-concept nouns that map to a real LinkedIn skill tag.
3. Leave out skills the profile marks `(course-level)`, `(portfolio-level)` or `(lab-level)`
   only (for example GraphQL, gRPC, PostgreSQL, MongoDB, Redis, Kubernetes, Terraform,
   CQRS, Azure Service Bus, Azure Cosmos DB, Python). LinkedIn tags carry no such
   qualifier, so they would read as production experience. The user can add any the candidate is
   comfortable defending in an interview.
4. Revisit this list whenever the Technical Skills section changes materially (a new
   production role, or a course-level skill becoming production). Do not reshuffle it
   for every profile refresh.

> Note: Search each term individually — LinkedIn autocompletes to its own tag library.
> If `CI/CD` doesn't match, try `Continuous Integration and Continuous Delivery (CI/CD)`.

---

## Step 5 — Certifications
*(Licenses & Certifications section)*

**AZ-900 is certified with a live credential** — add it now if not already present:
1. Go to [Microsoft Learn credentials](https://learn.microsoft.com/en-us/users/me/credentials)
2. Find the AZ-900 badge → click **Share** → **Add to LinkedIn**
3. LinkedIn will auto-fill the credential ID, issuer, and date

**Do NOT add AI-200 manually** — it hasn't been earned (the exam is on hold). Wait for Microsoft to issue that credential before repeating the steps above.

**Existing old MS certs** (MS: Programming in C#, MCPS): leave as-is — they show tenure and are not harmful.

---

## Step 6 — Courses Section
*(Profile → Add section → search "Courses" in the Add section search bar if not visible under Recommended)*

Derive this list at generation time from the profile output's `## Cert Status + Badge
URLs` table — do not reuse a fixed list, it goes stale the moment newer coursework
supersedes it:

1. Always include the exam-prep course for each certified/in-progress cert row
   (e.g. "Microsoft Azure Fundamentals (AZ-900): Exam Preparation").
2. From the AI-200 (or current active cert) row's notes, list the specific named
   courses/modules called out as completed or in progress — the profile's cert notes
   are updated each regeneration specifically so this step can read real, current
   course names instead of guessing.
3. Cap at ~8–10 entries; prefer the most recent/most role-relevant over exhaustive
   coverage.

Add each individually as a Course entry (title + "Pluralsight" as the associated
institution).

---

## Step 7 — Featured Section
*(Profile → Add section → Featured → Links)*

Derive the per-project entries at generation time from the profile output's
`## Portfolio Projects` table — one Featured link per row, so a new or retired
project shows up automatically instead of going stale like Step 3's example above:

1. For each row, add a Featured link with:
   - **URL** — the row's URL column
   - **Title** — the project name
   - **Description** — the row's description, trimmed to the first 1–2 sentences
     (LinkedIn shows a preview; the full text isn't needed there)
2. Add two static entries alongside the per-project ones (not derived from the
   profile, since they aren't portfolio projects):

```
GitHub Profile         — https://github.com/<github-user>
Pluralsight Profile    — https://app.pluralsight.com/profile/<pluralsight-user>
```

Current example (from today's profile — regenerate this list whenever the
Portfolio Projects table changes):

```
1. ai-job-search-workflow — https://github.com/<github-user>/ai-job-search-workflow
   AI-assisted job application workflow: analyzes job descriptions, generates
   ATS-safe tailored resumes and cover letters, and produces phased learning plans.
2. CookingTime — https://github.com/<github-user>/CookingTime
   20-year-old WinForms cooking-time calculator refactored into a modern .NET 10
   Blazor WebAssembly app; 118 automated tests at 80% line coverage with a
   blocking CI gate.
3. Resume_Site — https://github.com/<github-user>/Resume_Site
   Responsive static resume website, automatically deployed to GitHub Pages via
   GitHub Actions on push.
4. awk_linux_scripts — https://github.com/<github-user>/awk_linux_scripts
   Linux maintenance scripts for terminal-based system administration —
   hardware inspection and automated package update/cleanup workflows for
   Debian-based distributions.
5. GitHub Profile — https://github.com/<github-user>
6. Pluralsight Profile — https://app.pluralsight.com/profile/<pluralsight-user>
```

---

## Step 8 — Write the Draft Document

After presenting Steps 1–7 in the conversation, also write the full paste-ready
output to `outputs/profiles/linkedin/<date>.md` in the vault (`python -m jobomatic generate-linkedin` writes the same file) (create it if
missing, overwrite if present — it's a generated draft, not hand-maintained).
This gives the candidate a single file to work through in the candidate's own time instead of
having to copy content back out of chat history.

1. Include all of Steps 1–7 verbatim (fragments substituted, character counts
   computed, Step 3.5 trimmed to fit) — the file is the deliverable, not a
   pointer back to this skill.
2. Head the file with an HTML comment noting it's generated and which
   the public profile data it reflects, e.g.:
   ```
   <!-- GENERATED DRAFT — regenerate by running the update_linkedin_profile skill.
        Reflects the public profile data (hash abc123def456). -->
   ```
3. End with a short "After applying" note reminding the candidate to update the
   Current State vs Target diff table above once the candidate has pasted a field in.
4. Report the file path in the completion summary so it's easy to find.

---

## Post-Exam Update Checklist
AZ-900 is already certified and reflected above. Run this checklist after AI-200 results:

| Field | AI-200 Passed |
|---|---|
| About — Cloud line | Update to "AI-200 Certified" |
| Experience — Prof Dev bullet 2 | Add AI-200 cert line |
| Certifications | Add via Microsoft Share Badge |
| Headline | Consider adding "AI-200" |
