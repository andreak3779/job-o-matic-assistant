---
name: employment-research
description: >
  Identify high-confidence job opportunities where you can succeed quickly with
  minimal learning gaps. Use this when you want to focus ONLY on roles where you
  have Strong/Good fit and can close any remaining gaps in under 3 months.
  Trigger phrases: "find roles I can apply for now", "what jobs match my skills",
  "where should I apply", "high-confidence opportunities", "jobs I can do",
  "realistic roles for me", or when you provide a list of job descriptions and
  want to focus on the best matches only. Analyzes: resume + Pluralsight courses
  + Microsoft Learn + GitHub portfolio + profile facts + job descriptions to
  identify ONLY Strong/Good fit roles with closure timeline ≤3 months. Filters
  out Worth a try/Stretch/Pass roles entirely. Output: single markdown report with actionable
  opportunities ranked by salary potential and gap closure timeline. Always use
  this skill — do not handle opportunity filtering ad hoc.
---

# Employment Research Skill

Identify and prioritize high-confidence job opportunities where you can apply immediately or with minimal learning (under 3 months).

> Run `python -m jobomatic profile show facts`
> for cert status, differentiators, gaps, portfolio, ATS keywords, and AI-200
> coverage — this skill never needs the resume/career-history prose. Any
> `{fragment_name}` placeholder below must be filled from its **Copy Fragments**
> section before presenting output — never leave a literal `{fragment_name}` in
> delivered text.

---

## Overview

This skill filters your job search to **ONLY roles where you're a Strong or Good fit** and can close any remaining gaps in under 3 months.

**What this skill does:**
1. **Eliminates Worth a try/Stretch/Pass roles entirely** — focuses only on realistic, near-term opportunities
2. **Ranks Strong/Good fit roles by salary potential** — what you can earn with your current profile
3. **Shows gap closure timeline for each role** — exactly how long to learn what's missing (if anything)
4. **Provides immediate action plan** — which roles to apply for now vs. which ones to apply for after quick upskilling

**What you get:**
- A curated list of roles where you have 80%+ skill match or can reach 90%+ in under 3 months
- Estimated salary for each role based on your current profile + gap closure
- Specific learning path (if needed) to close gaps before applying
- Priority ranking so you know which roles to focus on first

**Result:** Focused, high-confidence job applications with higher success rate and faster interviews.

---

## Canadian Market Context (Aug 2026)

This skill focuses on **your core strengths and near-term opportunities** where you can apply immediately or after minimal upskilling (under 3 months).

**Your Strongest Lanes (Best Job Fit → Apply Now or with Quick Learning):**
- **C# / ASP.NET Core** — ~25% of roles; 8,000+ positions in Canada; 10+ years production
- **SQL Server / T-SQL** — Every enterprise role; 4,000+ specialized positions; your expertise is rare
- **Azure** — Top 5 hiring with 25–35% salary premium; AZ-900 certified
- **Full-stack backend** — API design + microservices; architect/senior-level positioning
- **GitHub Copilot** — {github_copilot_course_count} courses; rare differentiator

**Skills You Can Add in Under 3 Months (Quick Learning Wins):**
- **React portfolio** — 2–3 months for solid SPA project; +$15K–$25K salary uplift
- **Python Backend (FastAPI/Django)** — 2–3 months for production-ready project; +$15K–$20K uplift
- **TypeScript** — 2–4 weeks if building React/Node project; natural pairing

**Gaps This Skill EXCLUDES (Takes Too Long):**
- Machine Learning / AI Engineering — Requires 6–12 months
- Kubernetes at scale — Requires 2–3 months dedicated
- Note: check the profile's Known Genuine Gaps before excluding a gap here — a topic that's already course-level (e.g. Terraform, PostgreSQL, Dapper, NoSQL as of profile v10) may only need production-confidence time, not the full learning-from-zero estimate

**Strategic Focus:**
This skill surfaces **ONLY roles where your existing profile matches 80%+ of requirements**, or where you can reach 90%+ in under 3 months with focused, targeted effort.

---

## What You Need to Provide

- **List of target job descriptions** (5–15 actual postings; pasted text, URLs, or file names)

Everything else loads automatically from your job search project:
- `python -m jobomatic profile show facts` — certifications, differentiators, known gaps, portfolio projects (Resume_Site, ai-job-search-workflow, awk_linux_scripts), ATS keywords, and AI-200 domain coverage, including the `{course_count_sentence}` Copy Fragment for course/lab counts. Do NOT load `pluralsight-courses.md` (~15K tokens) for this — the fragment is recomputed fresh on every build, so it's never stale
- `python -m jobomatic learning list --provider mslearn` — completed Microsoft Learn modules and paths

---

## How It Works

### Step 1: Input & Setup

1. You provide job descriptions (5–15 postings)
2. Skill loads your profile files automatically
3. Skill analyzes each role against your profile using proven gap-analysis criteria

### Step 2: Filter for Strong/Good Fit ONLY

For each job posting, the skill classifies your match:

| Fit Rating | Definition | Action |
|---|---|---|
| **Strong** | All required skills ✅; 0–2 required skills are 🟡; no 🕰️; ≥2 nice-to-haves present | ✅ **INCLUDE in report** — Apply now or with minimal prep |
| **Good** | All required skills ✅, 🟡, or 🕰️; 1–2 genuine 🔴 gaps in nice-to-haves only. Any required 🕰️ (legacy-only evidence) caps here. | ✅ **INCLUDE in report** — Apply after 1–3 months learning; note any 🕰️ skill needs a per-application decision to surface |
| **Worth a try** | No core requirement 🔴 and a tail 🔴 or 3+ required 🟡/🕰️; coverage 60%+ | ❌ **EXCLUDE from report** — below Good (handled like Stretch until the override lands) |
| **Stretch** | 1 core requirement is 🔴; or coverage 40–59% | ❌ **EXCLUDE from report** — Too much learning needed |
| **Pass** | 2+ core requirements are 🔴; or coverage under 40%; or critical domain/tech mismatch; **or** a location rule is broken (below) | ❌ **EXCLUDE from report** — Not a fit right now |

**Location rules — a Pass regardless of skill fit.** The candidate's home city comes from the vault's location preferences, so a posting is rated **Pass** (even if every skill is ✅) when it is:
- Quebec-based (any arrangement — French-language work is out of scope);
- hybrid or on-site outside the home city;
- remote/hybrid/on-site limited to Atlantic Canada (east of Ontario is outside the working time zones); or
- listing French as a requirement (French as an *asset* is only a ⚠️ flag).

On-site/hybrid roles in the home city and remote roles in the time zones the candidate's location preferences allow are fine. Ambiguous postings never Pass on their own — e.g. "CA-Nationwide" listed beside Quebec/Nova Scotia, hybrid with no stated city, "the home province" without the home city, or a city with no stated arrangement produce a ⚠️ flag: relay it and tell the user to confirm home-province eligibility and expected hours with the recruiter before applying. This is computed in code (`src/jobomatic/fit/location.py`, rules in `src/jobomatic/fit/location_rules.json`, ADR 0008) and surfaced by `fit-check` / `gap-analysis` as a **Location & work arrangement** section — don't re-derive it by hand, and don't override it.

**Key principle:** This skill **only shows Strong/Good fits**. Worth a try, Stretch and Pass roles are filtered out entirely — including location Passes, however strong the skill match. If a Strong/Good role carries ⚠️ location flags, keep it in the report and put the open question (eligibility, hours, which city) in its **Application Strategy** line.

### Step 3: Rank by Salary & Timeline

For each Strong/Good role, calculate:
- **Estimated salary** based on your current profile + any quick learning
- **Gap closure timeline** (0 months if Strong fit; 1–3 months if Good fit)
- **Specific learning path** if applicable (course, project, or certification)

### Step 4: Generate Report

Output: **Single markdown report** with prioritized, actionable opportunities.

---

## Report Structure

Output: **Single markdown file** focused ONLY on high-confidence opportunities:

```
# High-Confidence Job Opportunities — the candidate
[Month Year]

## Executive Summary
[Your immediate action items]
[How many Strong vs Good fit roles found]
[Estimated timeline to be ready for each group]

## 🟢 STRONG FIT ROLES — Apply Now
### Role Summary
[List of roles; organized by job title]

### For Each Role:
**[Job Title] · [Company] · [Remote/Location]**
- **Fit Rating:** Strong (90%+ match)
- **Your Match:** [2–3 bullets of why you're a strong fit]
- **Salary Range:** [$X–$Y CAD based on market data]
- **When to Apply:** ✅ Immediately
- **Preparation:** [Minimal or none — just tailor resume]

---

## 🟡 GOOD FIT ROLES — Apply After 1–3 Months Learning
### Role Summary
[List of roles; organized by job title]

### For Each Role:
**[Job Title] · [Company] · [Remote/Location]**
- **Fit Rating:** Good (80–90% match)
- **Your Match:** [2–3 bullets of existing strengths]
- **Gap:** [One specific skill/knowledge gap]
- **Time to Close Gap:** [1–3 months]
- **Learning Path:** [Specific course, project, or resource]
- **Salary Range:** [$X–$Y CAD after gap closure]
- **When to Apply:** [Specific timeline; e.g., "After completing React project in August"]
- **Application Strategy:** [1–2 specific resume edits to highlight the gap closure path]

---

## 📋 Appendix: Quick Reference
- **Total postings reviewed:** [N]
- **Strong fit roles found:** [N] (apply now)
- **Good fit roles found:** [N] (apply after learning)
- **Worth a try/Stretch/Pass roles excluded:** [N] (too much learning needed)
- **Excluded for location:** [N] (Quebec, hybrid/on-site outside the home city, Atlantic-only remote, or French required — skills not the blocker)
- **Recommended learning timeline:** [e.g., "React SPA: 2–3 months"]
- **Expected salary improvement:** [e.g., "+$15K–$25K CAD with React portfolio"]
```

---

## Key Features

**Eliminates Low-Confidence Opportunities**
- Filters out Worth a try/Stretch/Pass roles entirely
- No "might be possible" recommendations — only realistic, near-term opportunities

**Ranked by Immediate Action**
- Strong fit roles listed first (apply now)
- Good fit roles listed second (apply after 1–3 months learning)
- Clear timeline for each role

**Transparent Gap Closure**
- For Good fit roles: exactly what's missing and how long to close it
- Specific course/project recommendations (not generic advice)
- Realistic learning timeline based on your actual pace

---

## How to Use This Skill

### Standard Workflow

1. **Gather 5–15 target job postings** — Copy/paste from LinkedIn, Indeed, or your job board of choice
2. **Mention your intent** — "Find roles I can apply for now" or "What jobs match my skills?"
3. **Skill generates report** — Automatically loads your profile, analyzes each role, filters for Strong/Good fit only
4. **Review the two tiers:**
   - 🟢 **Strong Fit roles** — Apply immediately (maybe 1–2 hours resume tailoring)
   - 🟡 **Good Fit roles** — Apply after 1–3 months targeted learning (specific path provided)
5. **Take action** — Pick your target role(s) and either apply now or follow the learning path

### What Makes a Difference

- **If you find 5+ Strong fit roles:** You're in excellent market position; apply to all
- **If you find 2–3 Good fit roles:** One 1–3 month learning project (React, Python, etc.) can unlock $15K–$25K salary boost
- **If you find <2 total:** Your postings may not be in your core lane; consider broader .NET/Azure search

---

## Tips for Best Results

- **Actual job postings:** Use real postings from LinkedIn/Indeed, not generic role descriptions
- **Sample size:** 5–15 postings give most reliable picture; 3 is minimum, 20+ is overkill
- **Target your lane:** Search ".NET Azure Developer Canada" or "Senior Backend .NET" — results will be much better than generic "software developer"
- **Include salary ranges:** If postings show salary, include it — helps skill estimate your earning potential

---

## Companion Skills

- **gap-analysis-job-description** — For deep-dive on a single Strong/Good fit role (get detailed application strategy)
- **create-a-cover-letter-and-tailored-resume-for-job-description** — Once you've decided to apply
- **learning-plan-gap-analysis** — When a Good fit role requires focused learning before applying
