---
name: github-profile-update
description: >
  Updates the candidate's GitHub profile fields with accurate, ready-to-paste
  content. Use when the user asks to update, refresh, or improve their GitHub
  profile, bio, status, or README. Also trigger after AZ-900 or AI-200 exam
  results to update cert-related fields. Contains exact copy for every field
  with character limits enforced.
---

> **Placeholders.** `<home city, province>`, `<github-user>` and `<linkedin-user>` stand for the candidate's own details. Fill them at generation time from `python -m jobomatic profile show contact` (location) and `profile show facts` (links); never write real values into this file.

# GitHub Profile Update Skill

> **Source file**: `profile show --public` (~8K tokens) — this skill only ever needs
> the **Copy Fragments** and **Cert Status + Badge URLs** sections, never
> Experience/Skills/Portfolio, so don't load the whole file. Run
> `python -m jobomatic profile show --public section "Copy Fragments" "Cert Status + Badge URLs"`
> before regenerating any field content.
> Any `{fragment_name}` placeholder below must be filled from the **Copy Fragments**
> output before presenting the final paste-ready text — never leave a literal
> `{fragment_name}` in delivered output. If that section is missing (older profile
> version, pre-fragments), fall back to computing the value the same way
> the Copy Fragments rules in `src/jobomatic/profile/copy_fragments.py` Step 2.5 does, from `profile-facts.md` /
> `skills-summary.md` directly.

## Character Limits
| Field | Limit |
|---|---|
| Bio | 160 chars |
| Status | 80 chars (emoji + text) |
| Name | 255 chars |
| Location | Free text |
| Website | One URL (must include https://) |

---

## Current State vs Target

| Field | Current | Action |
|---|---|---|
| Bio | Verify before updating | Set — see Step 1 |
| Status | Verify before updating | Set — see Step 2 |
| Profile README | Check if repo `<github-user>/<github-user>` exists | Create or update — see Step 3 |
| Profile fields | Verify before updating | Set — see Step 4 |
| Pinned repos | Verify existing repos first | Select from actual repos — see Step 5 |

---

## Step 1 — Bio
*(Profile → Edit profile → Bio · 160 char max)*

```
Full-stack dev | C# · ASP.NET Core · Angular · Azure · SQL | CI/CD · GitHub Actions · Copilot | {cert_status_short}
```
*(recount before saving — must stay under 160 chars; trim "Copilot" first if over. Taglines omit "10+ yrs" on purpose; the README below keeps it)*

> ⚠️ After passing AI-200: replace `AZ-900 Certified · AI-200 in progress` with `AZ-900 · AI-200 Certified`
> — recount to confirm under 160 chars before saving.

---

## Step 2 — Status
*(Click profile picture → Set status · 80 char max)*

```
🚀 Open to work | .NET · Angular · Azure | Building portfolio
```
*(61 chars)*

**Settings:**
- Emoji: 🚀
- Clear after: **Never**
- Busy checkbox: **Leave unchecked** (signals availability)

> ⚠️ After accepting a job offer: clear this status immediately.

---

## Step 3 — Profile README
*(High visibility — renders at the top of your GitHub profile page)*

**Setup:** Create a repo named exactly `<github-user>` (same as your username) with a `README.md`.
If the repo already exists, edit the existing `README.md`.

```markdown
## Hi, I'm the candidate 👋

Full-stack developer with 10+ years building enterprise applications.

**Core stack:** C# · ASP.NET Core · Angular · Azure · SQL Server

**Currently:** {cert_status_short} · Open to work

**Links:**
- 🌐 [Resume](https://<github-user>.github.io/Resume_Site/)
- 💼 [LinkedIn](https://www.linkedin.com/in/<linkedin-user>)
- 📚 [Pluralsight](https://app.pluralsight.com/profile/<pluralsight-user>)
```

> ⚠️ After passing AI-200: update "Currently" line to:
> `**Currently:** AZ-900 · AI-200 Certified · Open to work`

---

## Step 4 — Profile Fields
*(Profile → Edit profile)*

| Field | Value |
|---|---|
| Name | The candidate |
| Location | <home city, province> |
| Website | https://<github-user>.github.io/Resume_Site/ |
| LinkedIn | https://www.linkedin.com/in/<linkedin-user> |

---

## Step 5 — Pinned Repositories
*(Profile → Customize your pins → select up to 6)*

**Before pinning:** visit https://github.com/<github-user>?tab=repositories to see actual available repos. Select from what exists — do not pin empty or placeholder repos.

**Only pin public repos.** GitHub shows pins to every visitor, so a private repo can't be pinned and its link won't open for a recruiter. Check visibility first, for example `gh repo list <github-user> --json name,isPrivate,description`. The same applies to any repo linked from the profile README, LinkedIn Featured or dev.to.

Prioritize repos that demonstrate:
1. Angular + ASP.NET Core (full-stack pairing)
2. GitHub Actions CI/CD workflow
3. Azure Functions or Azure integration

**For each pinned repo, verify it has:**
- A short **description** (1 sentence, name the tech used)
- A **README.md** with tech stack listed and setup instructions

---

## Post-Exam Update Checklist
AZ-900 is already certified and reflected above. Run this checklist after AI-200 results:

| Field | AI-200 Passed |
|---|---|
| Bio (Step 1) | Change to `AZ-900 · AI-200 Certified` |
| Profile README (Step 3) | Update Currently line |
| Status (Step 2) | No change needed |
