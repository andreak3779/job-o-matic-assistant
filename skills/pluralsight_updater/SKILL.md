---
name: pluralsight-updater
description: >
  Imports newly completed Pluralsight courses and labs into the learning data when the
  candidate finishes them. Trigger whenever the user says "I finished a Pluralsight course",
  "I completed a new course", "update my Pluralsight courses", "I just finished [course name]",
  or provides a new Pluralsight history export (HTML or the import file). Also trigger when the user mentions any
  new Pluralsight course title or lab completion, even casually, e.g. "I just did the Redis
  course on Pluralsight." Always use this skill for Pluralsight updates. Do NOT use for
  Microsoft Learn updates; those go through the ms-learn-updater skill. After a real import it
  hands the new items to the pluralsight-summary-enricher skill automatically.
---

# Pluralsight Course Updater

Completed Pluralsight courses and labs live as items in `profile/learning/items.yaml` in the
vault, written only by `learning import`. There is no hand-kept course list and no hand-kept
count: totals and per-topic hours are computed. Items are matched by id (the course link), so a
course that was in progress last time and is finished now simply shows up as new.

> **Never `Read` a Pluralsight export** (HTML or JSON) or paste its contents into context; a large
> export can overflow the prompt. The importer reads the file itself.

## Workflow

1. **Get the export.** Either works; ask for the path:
   - the Pluralsight history page saved as HTML, or
   - the **import file** (`pluralsight_import_<date>.json`) from
     `templates/pluralsight_import_template.html`: open it in a browser, paste the history table
     HTML (or open the saved page), and click "Download import file". It holds only the completed
     entries and is parsed locally; nothing is uploaded.

   If they only mention a course, tell them an export is the reliable source (it carries the
   link, duration and completion date), and ask for one.
2. **Dry run:**
   `python -m jobomatic learning import <export.html or import.json>`
   A `.json` file is recognised as a Pluralsight import file by its `format` marker (a Learn
   transcript has none). The older bare-list JSON still imports, with a warning.
   It checks the page structure (and stops with "Nothing was imported" if Pluralsight changed it),
   then prints what is **new**, what **changed**, which stored items now have a **different id**
   (same title, new link: kept as one item), and any new item that matched no **topic** rule.
3. **Show the user the diff** and say what you notice: a new item with no topic, an unexpected
   change, items stored but missing from this export. Do not summarise it away.
4. **On the user's yes,** run the same command with `--apply`. The export is kept in the vault's
   `imports/pluralsight/` so the import can be replayed. A second run reports no changes.
5. **Topics for unmatched items.** Add a keyword to `src/jobomatic/learning/topics.yaml` (or the
   vault's `profile/learning/topics.yaml` for a personal rule) and import again; do not edit
   `items.yaml` by hand for this.
6. **Hand off** to `pluralsight-summary-enricher` with the ids of the new items.
7. **Downstream impact check** (flag to the user; never auto-edit these files):

   | Condition | Action to flag |
   |---|---|
   | A new course fills a **Genuine Gap** from `profile-facts.md` | "Consider updating Known Genuine Gaps: this is now course-level coverage" |
   | A new course is in a **critical AI-200 domain** (Service Bus, Cosmos DB, Redis, Key Vault, Event Grid, Azure OpenAI, vector databases, agentic patterns) | "This closes an AI-200 gap: update the AI-200 Domain Coverage table in skills-summary.md" |
   | A new **technology area** not in `skills-summary.md` | "New skill area: consider adding a bullet to skills-summary.md" |

   Then run `python -m jobomatic profile validate`: it warns when counts written in the
   profile text (for example "Pace of learning: N courses") no longer match the imported data.
   Offer to update that wording; do not change it without a yes.
8. **Refresh the evidence index, last,** after the summaries are saved:
   `python -m jobomatic index build`
   Each course is indexed as its title plus its summary, so run it only once step 6 is done, or
   the new items are indexed by title alone and need another build. It embeds only what is new
   or changed (seconds) and runs on the local Ollama service, so nothing leaves the machine.
   Report the line it prints (for example "13 new, 1 removed"). If Ollama is not running, say
   so and leave the index as it is; the evidence search is advisory and a later build catches up.

## A single completion mentioned in chat

Ask for the export. If the user has none and insists, do not invent an item: say what is missing
(link, duration, date) and wait. Hand-written items are not supported yet.

## Correcting a stored completion date

An import never overwrites a stored date (the first one wins), so a wrong date is fixed on
purpose, not by re-importing: `python -m jobomatic learning set-date <item-id> <YYYY-MM-DD>`.
Do it only when the user confirms the right date from their Pluralsight history; never edit
`items.yaml` by hand. Two different courses can share a title, so use the id, not the title.

## Reading the data

- `python -m jobomatic learning lookup "<title>" ["<title>" ...]` finds items (duration, date).
- `python -m jobomatic learning list [--provider pluralsight] [--topic "<topic>"]`.
- `python -m jobomatic learning stats` gives totals and hours per topic.

Never load `items.yaml` whole into context.

## Companion skills

- `pluralsight-summary-enricher`: adds a paraphrased summary to new items.
- `ms-learn-updater`: the Microsoft Learn counterpart. Pluralsight and Learn overlap on GitHub
  Copilot and C#; do not double-count when writing skills text.
