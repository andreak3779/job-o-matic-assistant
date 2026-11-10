# Job Search Keyword Strategy — the candidate
Generated April 2026 · Last updated: September 14, 2026 · Use this file to set up job alerts on LinkedIn, Indeed, and Eluta.ca

---

## Step 1 — LinkedIn Search Strings

Use these in the **Jobs** search bar. Enter the keyword string, then filter by
**Location: Canada** and toggle **Remote** on. Run each as a separate saved search alert.
Set alert frequency to **Daily**.

### Primary Targets (highest match rate)
```
Senior .NET Developer
Senior Full-Stack Developer C#
ASP.NET Core Developer
.NET Developer Angular
Senior Software Developer .NET
```

### Cloud / Azure Angle
```
Azure .NET Developer
Cloud Developer C# Azure
Azure Developer Associate .NET
```

### Broader Sweeps (when volume is low)
```
Senior Full-Stack Developer Angular
Software Developer ASP.NET Core Remote Canada
Senior Developer C# Remote
```

### LinkedIn-Specific Tips
- Save each string as an alert set to **Daily** — LinkedIn surfaces new postings within hours
- Filter by **Experience level: Mid-Senior + Director** to cut junior noise
- Add **the home city, the home province** as a second saved location search alongside Remote to catch local hybrid postings

---

## Step 2 — Indeed Search Strings

Indeed supports Boolean operators. Use the **Job title / keywords** field and set
**Location** to **Canada** or **Remote**.

### Exact Title Searches (use quotes)
```
"Senior .NET Developer"
"Senior Full-Stack Developer"
"ASP.NET Core Developer"
".NET Developer" "Angular"
"Senior Software Developer" ".NET"
```

### Boolean Combinations (broader reach)
```
(ASP.NET OR "ASP.NET Core") AND (Angular OR TypeScript) AND (Senior OR Lead)
("C#" OR ".NET") AND ("Azure" OR "Azure Functions") AND Developer
"Full-Stack" AND ("C#" OR ".NET Core") AND Remote
Senior AND (".NET" OR "ASP.NET") AND (Remote OR the home city)
```

### Indeed-Specific Tips
- Use the **Date posted: Last 3 days** filter to avoid stale listings
- After searching, click **Save this search** and set email alert to **Daily**
- Search **<home city, province>** separately for any hybrid roles not tagged remote

---

## Step 3 — Eluta.ca Search Strings

Eluta.ca indexes jobs posted directly on employer career sites (not aggregated postings), so it
surfaces roles that don't always appear on LinkedIn/Indeed — worth running as a third parallel
alert. Use the basic search box for quick keyword strings, or `/search_advanced` for the full form
(occupation category, employer, salary range, radius, remote toggle).

### Basic Search Box — Keyword Strings
```
Senior .NET Developer
ASP.NET Core Angular Developer
Senior Full-Stack Developer C#
Azure .NET Developer
```

### Search Syntax
- **AND is implicit** — space-separated terms must all match: `.NET Angular Senior`
- **Exclude with a hyphen:** `.NET Developer -junior -intern`
- **Phrase search with quotes:** `"ASP.NET Core"` or `field:"human resource"`
- **Field-specific qualifiers:**
  - `title:` — restricts match to job title only, e.g. `title:".NET Developer"`
  - `employer:` — jobs from a specific company
  - `field:` — occupation category (e.g. `field:computing`)
  - `location:` — city, province, postal code, or FSA, e.g. `location:"<home city, province>"` or `location:"R3C"`
  - `km:` — radius in kilometers from the `location:` point

### Advanced Search Form (`/search_advanced`)
- Set **Occupation** to "Computing" to cut noise from unrelated categories
- Use the separate **included words** / **excluded words** fields instead of stuffing everything
  into one box — cleaner than trying to chain multiple hyphenated excludes
- Set **Employment Type** to Full-time (excludes Seasonal/Internship postings)
- Set **Local/Anywhere** remote toggle on, and set radius (25–50 km) around the home city for hybrid
- No native date-posted filter — rely on the emailed alert to catch new postings instead of
  re-sorting old results by hand

### Eluta-Specific Tips
- Job alert emails are opt-in per search — enter your email on the results page for that query to
  get notified as new matches are indexed; repeat per saved search since alerts aren't bundled
- Because Eluta pulls straight from employer sites, postings can appear here before they hit
  LinkedIn/Indeed's aggregators — check it on the same daily cadence, not as an afterthought
- Cross-check company names against ones already tracked in your Step 5 list before applying —
  Eluta surfaces the same employer's posting independently of LinkedIn/Indeed, which is the
  duplicate-submission risk this alert channel adds

---

## Step 4 — Keywords to Watch for in Postings

When scanning results, these terms in a posting title or description are strong
signals it is a good fit:

| Signal | Why |
|---|---|
| "C#" + "Angular" together | Direct full-stack match |
| "Legacy modernization" or "migration" | Differentiator — 3 employers |
| "Azure Functions" or "Azure Developer" | AZ-900 certified + AI-200 in progress |
| "Entity Framework" or "EF Core" | Production depth |
| "CI/CD" + "Azure DevOps" or "GitLab" | Direct match |
| "TDD" or "xUnit" | Acme Software evidence |
| "SQL Server" + "T-SQL" | 10+ year depth |
| "Kubernetes" or "container orchestration" | Now the single most recurring named gap (BeyondTrust, Foci Solutions, Aequilibrium, Aug 2026) — course-level only today; MoviesApp containerization + a planned K8s deployment closes this |
| "Playwright" or "E2E testing" | Named by BeyondTrust (Aug 2026) — closing via CookingTime, prioritizing Playwright over Cypress |

---

## Step 5 — Maintain a Short Tracking List

Once you start applying, keep a record of each application to prevent duplicating
submissions when the same posting appears across platforms — Eluta pulls straight from
employer sites, so the same posting can independently surface there too.

Minimum columns to track:

| Company | Role | Platform | Date Applied | Status | Next Step |
|---|---|---|---|---|---|
| Example Corp | Senior .NET Developer | LinkedIn | Apr 21, 2026 | Applied | Follow up Apr 28 |

Statuses: **Applied · Phone Screen · Technical · Offer · Rejected · Withdrawn**

> Use the `JobSearch_ApplicationTracker.xlsx` file for the full tracked version
> with dropdowns, a live dashboard, and keyword lists in one place.
