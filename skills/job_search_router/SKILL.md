---
name: job-search-router
description: |
  Delegates to the monorepo CLI:
  - `jobo fit-check <jd>` for a quick fit rating
  - `jobo gap-analysis <jd>` for a full gap report
  - `jobo generate-resume <jd>` / `generate-cover-letter <jd>` for documents
  - `jobo interview-prep <jd>` for interview prep
  Use whenever the user asks how to handle a job opportunity and route it to
  the right action.
---

# Job Search Router

Route the user's intent to one of the monorepo CLI commands.

- **Quick yes/no fit** → `jobo fit-check <path/to/jd.md>`
- **Detailed gap analysis** → `jobo gap-analysis <path/to/jd.md>`
- **Tailored documents** → `jobo generate-resume <path/to/jd.md> --company Company` and `jobo generate-cover-letter <path/to/jd.md> --company Company`
- **Interview prep** → `jobo interview-prep <path/to/jd.md>`

Before routing to tailored documents, confirm this isn't a repeat cold application to the same posting — the `create-a-cover-letter-and-tailored-resume-for-job-description` skill's Step 0a gate covers this if you hand off there, but a direct CLI route bypasses that gate, so ask here instead.

Run commands from the repository root:

```bash
python3 -m jobomatic <command> ...
```

Then summarize the generated output for the user and state the file paths.
