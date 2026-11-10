# Sample output

Everything here was produced by the tool from the **fictional** demo vault (`demo-vault/`) and the
fictional postings in `tests/fixtures/`. The person, employers and contact details are invented.
No real person's data is in this folder.

Reproduce it:

```bash
export JOBOMATIC_VAULT=$PWD/demo-vault
jobo fit-check tests/fixtures/strong-fit-jd.md
jobo gap-analysis tests/fixtures/strong-fit-jd.md --out /tmp/gap.md
jobo generate-resume tests/fixtures/frontend-angular-jd.md     # refused, exit status 2
```

| Folder | What it shows |
| --- | --- |
| [strong-fit/](strong-fit/) | A posting that matches the profile. The fit check, a gap analysis, and the text of the résumé and cover letter the tool drafts. |
| [weak-fit/](weak-fit/) | A posting that does not match. The fit check and gap analysis list the gaps, and `generate-resume-output.txt` shows the gate refusing to write documents. |

## An honest note about the wording

The fit check and gap analysis are the tool's strength: they say what is matched, what is missing,
and why. The cover letter is deliberately plain. It chooses which true evidence to lead with and
fills a fixed template, so its "what I bring" bullets repeat a pattern. It is a starting draft for
the person to rewrite in their own voice, not a finished letter. See [../docs/LIMITS.md](../docs/LIMITS.md).

The sample letter and résumé are shown as text (the real output is a DOCX file) and carry a
`<TODAY>` marker where the generation date goes.
