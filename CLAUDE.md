# Repo-wide rules

## Protected-characteristic disclosure in application documents

Applies to every project, skill, tool and generator in this repo (resumes, cover letters, cold-outreach letters, job-board text, LinkedIn/GitHub text, thank-you letters, interview prep).

- Never add any protected-characteristic or self-identification information (any characteristic protected under human-rights law) to a generated document by default, and never infer it from other files.
- Exception: if a job description asks applicants to self-identify (required, preferred, or an invitation to self-ID), ask the user whether to include it for that specific posting. Add it only after an explicit yes for that posting. If the answer is no or unclear, leave it out.
- Confirmation is per posting. A past yes does not carry over.
- Do not write the user's personal characteristics into repo files. Keep this rule generic; the user's details stay in private memory, not in committed files.

# Skills, reference and templates

`skills/` holds one folder per workflow (`SKILL.md`), `reference/` the material their steps load, and `templates/` layout notes and examples. `skills/README.md` lists them. `.claude/skills/<name>` are symlinks to `skills/<name>`. Personal data is never here; it lives in the vault.

## Career facts come from the profile

- Skills read the profile with `python -m jobomatic profile show full|facts|section "<name>"|contact` (add `--public` for the public view). Generators load it through `jobomatic.bootstrap.load_profile()` or `load_presence_view()`. Never read raw source files or an old export directly.
- The profile is typed YAML in the vault's `profile/` folder. There is nothing to build: edit the YAML, then run `python -m jobomatic profile validate` (it also warns when counts written in the profile text no longer match the imported learning data). If the profile looks wrong, fix the YAML in the vault; do not patch around it in a skill.
- `profile show full` is about 11,500 tokens. Use it only when the skill needs the resume and career prose (cover letter, resume, interview prep). For facts, a section or contact details, use `facts`, `section "<heading>"` or `contact`. The profile has two headings named `## Key Differentiators`; `section` matches the first.
- Completed Pluralsight and Microsoft Learn items are in the vault's `profile/learning/items.yaml`, written only by `python -m jobomatic learning import` (ADR 0017). Counts and hours are computed (`learning stats`), never typed. `learning lookup` and `list` exist so a skill never loads the whole file. Pluralsight and Learn overlap on GitHub Copilot and C#; Learn's Azure coverage is conceptual and the hands-on Azure labs are Pluralsight, so do not double-count.

## Fit ratings and gates

- The rating is computed in code (`src/jobomatic/fit/`). Skills read it from `fit-check` or `gap-analysis` output and never re-derive it. Call `rate_parsed_jd(parsed, profile)`, not a hand-built `rate_fit(...)`, so the location rules and the unscored-lines list are never forgotten.
- A location Pass (Quebec, hybrid or on-site outside the home city, Atlantic-only remote, French required) is a Pass whatever the skills say. Pass it through as "skills aren't the blocker" and do not recommend a learning plan (ADR 0008).
- Sentence-style JD bullets are reduced to skill terms by `src/jobomatic/fit/skill_vocabulary.json` (ADR 0009). Add a term there when a real posting names a technology that shows up under "Required lines not scored".
- The gate (`jobomatic.gate`, ADR 0003) decides when documents may be generated; its overrides (`--confirm-gaps`, `--confirm-reapply`, `--confirm-below-minimum`) are used only when the user says so.

## Hardcoded facts in skills

Cert status, course counts and similar numbers go stale when written as prose. Audits in August 2026 found them back in the skills twice. Use `{fragment_name}` placeholders filled from `jobomatic.profile.copy_fragments.compute_copy_fragments()` (`course_count_sentence`, `cert_status_short`, `azure_course_lab_sentence`, `github_copilot_course_count`, `leadership_course_count`) or tell the skill to derive the number at generation time. Run `python scripts/check_skill_hardcoding.py` after editing any `SKILL.md`; it is a heuristic scanner, so read each finding.

## Generated documents

- Output goes to the vault's `outputs/` (ADR 0015); `*.docx` and `*.pdf` are never committed. Generate with `python-docx`; there is no Node.js dependency. Check a generated `.docx` visually before delivering it.
- Page counts: the quick way is `--check-pages` on `generate-resume`, `generate-cover-letter`, `generate-profile-resume` or `render` (set `JOBOMATIC_LIBREOFFICE=flatpak`; ADR 0024). To measure by hand: LibreOffice is a Flatpak (`org.libreoffice.LibreOffice`), and the system `soffice` here is a partial install that cannot open a DOCX, so do not use it. Convert with absolute paths: `flatpak run --filesystem=$O --filesystem=$S org.libreoffice.LibreOffice --headless --convert-to pdf --outdir $S $O/resume.docx`, then `pdfinfo $S/resume.pdf | grep Pages`. A resume is at most 2 pages and a cover letter exactly 1. Write the PDFs to a scratch folder, not `outputs/`.
- The one deliberate write to hand-maintained interview material is `interview_prep --update-star-bank`, which updates `last_used` and `used_for` in the vault's `profile/stories.yaml` and nothing else.
- Learning-plan PDFs are rendered from a role config by `python -m jobomatic generate-learning-plan <config>`. Copy `templates/roles/_example.json`, keep real configs in the vault's `profile/roles/`, and reuse the same output filename so git history is the version history. Allowed colours: `NAVY`, `RED`, `AMBER`, `GREEN`, `PURP`, `BLUE`, `LGRAY`, `MGRAY`, `WHITE`.

## Presence skills (LinkedIn, GitHub, Jobgether, Indeed/ZipRecruiter, Pluralsight)

- They read the public view of the profile (`profile show --public`, or `load_presence_view()`); only fields marked public can reach them (ADR 0018). Draft copy uses Copy Fragments placeholders, not literal numbers.
- Each skill has a matching generator in `src/jobomatic/presence/` (command `generate-linkedin`, `generate-github`, `generate-jobgether`, `generate-job-board`, `generate-pluralsight`; also MCP tools) that reads the skill's own `SKILL.md` templates, so the conversation and the command cannot drift apart. Each writes its own draft file under the vault's `outputs/profiles/<platform>/`; keep one file per skill.
- Every presence skill has a post-exam checklist ("check cert status, then update this surface"); follow that shape for a new one. Indeed, ZipRecruiter, Jobgether and Pluralsight publish no fixed character limits, so those skills give practical targets and say so.
- `reference/JobSearch_KeywordStrategy.md` is job-search strategy, not presence content; keep it in `reference/`.
