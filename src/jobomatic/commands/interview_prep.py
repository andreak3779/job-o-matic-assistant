#!/usr/bin/env python3
"""Generate a tailored interview-prep DOCX from a job description and profile profile."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Literal, cast

from docx import Document
from docx.shared import Pt

from jobomatic import bootstrap, paths
from jobomatic.applications import outputs
from jobomatic.commands.support import (
    DocumentData,
    note_logged,
    produce_document,
    require_path,
    say,
    story_mentions,
)
from jobomatic.documents.adapters.docx_advanced import (
    banner,
    callout_box,
    qa_card,
    star_card,
    two_column_table,
)
from jobomatic.documents.adapters.docx_layout import add_paragraph, section_heading
from jobomatic.fit.engine import FitResult, find_gap_coaching_entry, rate_parsed_jd
from jobomatic.fit.gap_coaching import GapCoachingEntry, parse_gap_coaching
from jobomatic.fit.parser import parse_jd
from jobomatic.profile.ports import ProfileRepository
from jobomatic.profile.service import mark_stories_used
from jobomatic.provenance import write_sidecar
from jobomatic.results import CommandResult, Message, emit, failure

Stage = Literal["phone_screen", "technical_screen", "final_round"]

_STAGE_LABELS: dict[Stage, str] = {
    "phone_screen": "Phone Screen",
    "technical_screen": "Technical Screen",
    "final_round": "Final Round",
}

# Phone Screen gets a lean 2 stories; the other two stages get the full
# ranked pool (up to 5), per the SKILL.md's stage table.
_STAGE_STAR_COUNT: dict[Stage, int] = {
    "phone_screen": 2,
    "technical_screen": 5,
    "final_round": 5,
}

_STATUS_LABELS: dict[str, str] = {
    "match": "Strong Match",
    "portfolio": "Learning / Portfolio",
    "course": "Learning / Portfolio",
    "legacy": "🕰️ Legacy Experience",
    "gap": "Genuine Gap",
}


def _select_star_stories(
    profile: Any, required: list[str], nice_to_have: list[str], *, limit: int = 5
) -> list[dict[str, Any]]:
    """Return up to ``limit`` best-fitting STAR stories, ranked by JD-tag overlap."""
    pool = [s.lower() for s in required + nice_to_have]
    scored: list[tuple[int, Any]] = []
    for story in profile.stories:
        text = f"{story.title} {' '.join(story.jd_tags)} {story.situation} {story.action} {story.result}".lower()
        score = sum(1 for term in pool if story_mentions(text, term))
        if score:
            scored.append((score, story))
    scored.sort(key=lambda t: t[0], reverse=True)
    out: list[dict[str, Any]] = []
    for _, story in scored[:limit]:
        out.append(
            {
                "title": story.title,
                "tags": list(story.jd_tags),
                "situation": story.situation,
                "task": story.task,
                "action": story.action,
                "result": story.result,
                "adapt_when": list(getattr(story, "adapt_when", [])),
            }
        )
    return out


_LEADING_DESCRIPTORS_RE = re.compile(
    r"(?i)^\s*(?:strong|solid|good|expertise|experience\s+with|hands-on\s+experience\s+with|deep\s+experience\s+with)\s+"
)
_PARENS_NON_GREEDY_RE = re.compile(r"\([^)]*\)")
_SPLIT_LIST_RE = re.compile(r",|\s+and\s+|/")


def _atomic_skills(skills: list[str]) -> list[str]:
    """Split compound JD skill lines into concrete tokens (case-folded, deduped).

    Handles ``"Strong experience with Azure DevOps, GitHub Actions and Docker"``
    → ``["azure devops", "github actions", "docker"]`` (preserves first-seen
    casing while dropping near-duplicates like ``"Azure"`` / ``"azure"``).
    """
    seen: set[str] = set()
    atoms: list[str] = []
    for skill in skills:
        cleaned = _LEADING_DESCRIPTORS_RE.sub("", skill.strip())
        cleaned = _PARENS_NON_GREEDY_RE.sub("", cleaned).strip(" ,./:;")
        if "," in cleaned or "/" in cleaned or re.search(r"\s+and\s+", cleaned, re.IGNORECASE):
            parts = [p.strip(" ,./:;") for p in _SPLIT_LIST_RE.split(cleaned)]
            for p in parts:
                _maybe_add(atoms, p, seen)
        else:
            _maybe_add(atoms, cleaned, seen)
    return atoms


def _maybe_add(atoms: list[str], candidate: str, seen: set[str]) -> None:
    key = candidate.lower()
    if len(key) > 1 and key not in seen:
        seen.add(key)
        atoms.append(candidate)


def _evidence_label(evidence: str) -> str:
    """Return the evidence source label (company/project) before the colon."""
    raw = (evidence or "").strip()
    if ":" in raw:
        return raw.rsplit(":", 1)[0].strip()
    return ""


def _strip_quotes(text: str) -> str:
    """Strip a matching pair of wrapping double quotes, if present."""
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        return stripped[1:-1]
    return stripped


def _attach_gap_coaching(card: dict[str, str], entry: GapCoachingEntry) -> None:
    """Layer a gap-coaching entry's tip and gap-note onto an existing Q&A card.

    Never touches the question or answer — the caller sets the answer using
    the entry's own "what to say" framing when one exists, since that's
    hand-authored, verified content and a stronger grounding than the
    generic evidence stub.
    """
    if entry.what_not_to_say:
        card["tip"] = "Avoid: " + " · ".join(entry.what_not_to_say)
    notes = [n for n in (entry.honest_floor, entry.best_star_bridge) if n]
    if notes:
        card["gap_note"] = " · ".join(notes)


def _qa_cards_and_reminders(
    result: FitResult, gap_entries: list[GapCoachingEntry]
) -> tuple[list[dict[str, str]], list[str]]:
    """Build Q&A cards for required skills, plus honesty reminders for the rest.

    A skill with a matching gap-coaching entry (any status — coaching notes
    cover both framing gaps on grounded skills, like TDD, and genuine gaps)
    gets that entry's exact "what to say" framing as the answer, its
    "what not to say" list as the Tip line, and its honest floor / best
    STAR bridge as a gap-note callout — never fabricated, always the
    reference file's own words. A grounded skill with no coaching entry
    falls back to the evidence trace as its answer. An ungrounded skill
    with no coaching entry gets a plain honesty reminder instead of a card,
    since there's no honest content to put in an answer.

    This is the one Q&A category this script generates itself; the other
    four LLM-authored categories (resume walkthrough, engineering judgment,
    collaboration, situational) merge in later via ``--qa-cards`` (Phase 5)
    — the script never fabricates prose for them.
    """
    cards: list[dict[str, str]] = []
    reminders: list[str] = []

    for m in result.grounded_required[:6]:
        entry = find_gap_coaching_entry(m.skill, gap_entries)
        label = _evidence_label(m.evidence)
        if m.status == "match" and label:
            question = f"Walk me through how you used {m.skill} at {label} in a production system."
        elif m.status == "portfolio" and label:
            question = f"Tell me about {m.skill} on {label} — what problem did it solve?"
        else:
            question = f"Tell me about a time you used {m.skill} in a real project."
        card = {
            "question": question,
            "answer": _strip_quotes(entry.what_to_say)
            if entry
            else f"Evidence on file: {m.evidence}",
        }
        if entry:
            _attach_gap_coaching(card, entry)
        cards.append(card)

    # Legacy matches are real experience, just not on the resume — gap framing
    # ("how would you address X") would misrepresent them.
    for m in result.required:
        if m.status == "legacy":
            source = _evidence_label(m.evidence) or "an earlier role"
            reminders.append(
                f"{m.skill}: you have real legacy experience ({source}) that isn't on your "
                "resume. Decide before the interview whether to bring it up if asked, and "
                "prepare a one-line honest answer either way."
            )

    for m in [m for m in result.ungrounded_required if m.status != "legacy"][:2]:
        entry = find_gap_coaching_entry(m.skill, gap_entries)
        if entry:
            card = {
                "question": f"How would you address {m.skill} if it comes up?",
                "answer": _strip_quotes(entry.what_to_say),
            }
            _attach_gap_coaching(card, entry)
            cards.append(card)
        else:
            reminders.append(
                f"If {m.skill} comes up, answer honestly about your current level — "
                "no production or portfolio evidence for it in the profile."
            )

    return cards, reminders


def _experience_match_rows(result: FitResult) -> list[tuple[str, str]]:
    """Build (skill, status + evidence) rows for the Experience Match table."""
    rows: list[tuple[str, str]] = []
    for m in result.required + result.nice_to_have:
        label = _STATUS_LABELS.get(m.status, m.status)
        evidence = (
            m.evidence if m.status != "gap" else "Not present in resume, portfolio, or coursework"
        )
        rows.append((m.skill, f"{label} — {evidence}"))
    return rows


def _blank(text: str | None) -> bool:
    """True when ``text`` is ``None`` or contains only whitespace."""
    return text is None or not text.strip()


def _validate_qa_cards(qa_cards: list[dict[str, str]]) -> None:
    """Fail closed if any supplied Q&A card is missing its required fields.

    ``qa_cards`` is LLM-authored content the script never generates itself
    (see the plan's Scope Boundary) — a malformed entry must raise, not be
    silently skipped or padded with placeholder text.
    """
    for idx, card in enumerate(qa_cards, start=1):
        for key in ("question", "answer"):
            if not card.get(key):
                raise ValueError(f"qa_cards entry {idx} is missing required field {key!r}")


def generate_interview_prep(
    jd_path: Path,
    *,
    profile: Any | None = None,
    out_path: Path | None = None,
    stage: Stage = "technical_screen",
    gap_coaching_path: Path | None = None,
    write_star_bank: bool = False,
    profile_repository: ProfileRepository | None = None,
    company_research: str | None = None,
    recruiter_briefing: str | None = None,
    qa_cards: list[dict[str, str]] | None = None,
    salary_section: str | None = None,
    notes: list[Message] | None = None,
) -> tuple[Path, Path, FitResult]:
    """Build and write the interview-prep DOCX plus provenance sidecar, from a posting file.

    See ``generate_interview_prep_from_text``.
    """
    return generate_interview_prep_from_text(
        jd_path.read_text(encoding="utf-8"),
        source=jd_path,
        profile=profile,
        out_path=out_path,
        stage=stage,
        gap_coaching_path=gap_coaching_path,
        write_star_bank=write_star_bank,
        profile_repository=profile_repository,
        company_research=company_research,
        recruiter_briefing=recruiter_briefing,
        qa_cards=qa_cards,
        salary_section=salary_section,
        notes=notes,
    )


def generate_interview_prep_from_text(
    jd_text: str,
    *,
    source: Path | None = None,
    profile: Any | None = None,
    out_path: Path | None = None,
    stage: Stage = "technical_screen",
    gap_coaching_path: Path | None = None,
    write_star_bank: bool = False,
    profile_repository: ProfileRepository | None = None,
    company_research: str | None = None,
    recruiter_briefing: str | None = None,
    qa_cards: list[dict[str, str]] | None = None,
    salary_section: str | None = None,
    notes: list[Message] | None = None,
) -> tuple[Path, Path, FitResult]:
    """Build and write the interview-prep DOCX plus provenance sidecar.

    ``source`` is where the posting came from, recorded in the sidecar (``None`` for pasted text);
    ``notes``, when given, collects what would otherwise be printed (see ``say``).

    ``stage`` gates document scope per the SKILL.md's stage table: Phone
    Screen gets 2 STAR stories, Technical Screen and Final Round get the
    full ranked pool. Company research, recruiter briefing, the LLM-authored
    Q&A categories, and the salary section layer in later (see the plan's
    Phase 5) — this deterministic core covers only what the profile and fit
    engine can verify without inventing content.

    ``gap_coaching_path`` defaults to ``profile/gap-coaching.md`` in the vault; a
    test-only override keeps tests from depending on the real reference file. Missing the file entirely is not
    an error — coaching notes are optional enrichment, not required input.

    ``write_star_bank`` (opt-in, default ``False``, per the plan's Phase 4
    write-back safety design) updates ``last_used``/``used_for`` on every
    STAR story actually selected in this run — the same list rendered into
    the STAR Stories section, respecting the stage-based ``limit`` — and saves only
    ``stories.yaml``. ``profile_repository`` is a test-only override that keeps tests from
    touching the real profile. A story title that matches nothing raises ``ProfileError``
    before anything is written — fail closed, never guess.

    ``company_research``, ``recruiter_briefing``, ``qa_cards``, and
    ``salary_section`` are the plan's Phase 5 hybrid LLM-content inputs —
    real prose/structured content supplied from outside the script (web
    search, a pasted briefing, LLM-authored Q&A, salary research), never
    fabricated here. Each is optional and its section is omitted entirely
    (no placeholder text) when absent. ``qa_cards`` entries missing
    ``"question"`` or ``"answer"`` raise ``ValueError`` before anything is
    rendered. ``salary_section`` only renders when ``stage ==
    "final_round"``; supplying it at any other stage prints a warning and
    skips the section instead of raising — a deliberate "warn and ignore"
    exception to this function's otherwise fail-closed conventions.
    """
    if qa_cards:
        _validate_qa_cards(qa_cards)

    profile = profile or bootstrap.load_profile()
    parsed = parse_jd(jd_text)
    result = rate_parsed_jd(parsed, profile)

    if gap_coaching_path is None:
        gap_coaching_path = paths.gap_coaching_path()
    gap_entries = (
        parse_gap_coaching(gap_coaching_path.read_text(encoding="utf-8"))
        if gap_coaching_path.exists()
        else []
    )

    located = outputs.locate_application(
        jd_text,
        log=False,
        documents=("interview_prep",),
        fit_rating=result.rating,
        create_folder=out_path is None,
    )
    if out_path is None:
        out_path = located.folder / "interview-prep.docx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    note_logged(notes, located)

    stage_label = _STAGE_LABELS[stage]
    today = date.today().strftime("%B %d, %Y")

    doc = Document()
    banner(
        doc,
        title=parsed.title,
        subtitle_lines=[parsed.company, profile.identity.name, f"{stage_label} · {today}"],
    )

    if not _blank(recruiter_briefing):
        callout_box(doc, "Recruiter Briefing", (recruiter_briefing or "").strip())

    if not _blank(company_research):
        section_heading(doc, "Company Research")
        add_paragraph(doc, (company_research or "").strip(), space_after=Pt(6))

    section_heading(doc, "Experience Match")
    two_column_table(doc, ["They Need", "Your Evidence"], _experience_match_rows(result))

    section_heading(doc, "Anticipated Questions")
    cards, reminders = _qa_cards_and_reminders(result, gap_entries)
    for card in cards:
        qa_card(
            doc,
            card["question"],
            card["answer"],
            tip=card.get("tip"),
            gap_note=card.get("gap_note"),
        )
    for supplied in qa_cards or []:
        qa_card(doc, supplied["question"], supplied["answer"], tip=supplied.get("tip"))
    for reminder in reminders:
        add_paragraph(
            doc, reminder, italic=True, size=Pt(9.5), space_before=Pt(4), space_after=Pt(4)
        )

    section_heading(doc, "STAR Stories")
    stories = _select_star_stories(
        profile, parsed.required, parsed.nice_to_have, limit=_STAGE_STAR_COUNT[stage]
    )
    if stories:
        for story in stories:
            star_card(
                doc,
                story["title"],
                story["tags"],
                story["situation"],
                story["task"],
                story["action"],
                story["result"],
                adapt_when=story["adapt_when"],
            )
    else:
        add_paragraph(
            doc, "No tagged STAR stories found. Add some to the profile profile.", italic=True
        )

    if not _blank(salary_section):
        if stage == "final_round":
            section_heading(doc, "Salary / Negotiation")
            add_paragraph(doc, (salary_section or "").strip(), space_after=Pt(6))
        else:
            say(notes, "info", "Salary section supplied but stage is not final_round — omitted.")

    section_heading(doc, "Fit Rating")
    add_paragraph(doc, f"{result.rating} — {result.rationale}", space_after=Pt(6))

    add_paragraph(
        doc,
        f"Generated {today} · {profile.identity.name} · {parsed.title} · {stage_label}",
        italic=True,
        size=Pt(9),
        space_before=Pt(16),
    )

    doc.save(str(out_path))

    if write_star_bank and stories:
        used_for_entry = f"{parsed.company} — {parsed.title}"
        last_used_value = date.today().strftime("%B %Y")
        titles = [story["title"] for story in stories]
        updated = mark_stories_used(
            profile, titles, last_used=last_used_value, used_for=used_for_entry
        )
        repository = profile_repository or bootstrap.profile_repository()
        repository.save_stories(updated)
        for title in titles:
            say(
                notes,
                "info",
                f"STAR story {title!r}: last_used -> {last_used_value}; used for {used_for_entry}",
            )

    low_confidence = result.skills_only_rating in ("Pass", "Stretch", "Worth a try") and bool(
        result.ungrounded_required
    )
    sidecar = write_sidecar(
        out_path,
        script="interview_prep.py",
        profile=profile,
        inputs=[str(source)] if source else [],
        fit_rating=result.rating,
        evidence_sources=result.evidence_sources(),
        warnings=["low evidence — manually review before using"] if low_confidence else [],
    )
    return out_path, sidecar, result


def run(
    jd_text: str,
    *,
    source: Path | None = None,
    out: Path | None = None,
    stage: str = "technical_screen",
    update_star_bank: bool = False,
    company_research: str | None = None,
    recruiter_briefing: str | None = None,
    qa_cards_json: str | None = None,
    salary_section: str | None = None,
) -> CommandResult[DocumentData]:
    """Write the interview-prep document for the posting.

    ``qa_cards_json`` is the text of a JSON list of Q&A cards; the other optional inputs are the
    text of what was supplied. ``update_star_bank`` records which stories were used in the vault's
    ``stories.yaml``, so the run holds the vault write lock.
    """
    if stage not in _STAGE_LABELS:
        return failure(f"unknown stage {stage!r}; expected one of {', '.join(_STAGE_LABELS)}")

    def make(profile: Any, notes: list[Message]) -> tuple[Path, Path, FitResult]:
        try:
            qa_cards = json.loads(qa_cards_json) if qa_cards_json is not None else None
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in --qa-cards file: {exc}") from exc
        return generate_interview_prep_from_text(
            jd_text,
            source=source,
            out_path=out,
            stage=cast(Stage, stage),
            write_star_bank=update_star_bank,
            company_research=company_research,
            recruiter_briefing=recruiter_briefing,
            qa_cards=qa_cards,
            salary_section=salary_section,
            notes=notes,
        )

    return produce_document(make=make)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="interview-prep", description="Generate an interview prep DOCX for a job description"
    )
    parser.add_argument("jd", type=Path, help="Path to job description markdown file")
    parser.add_argument(
        "--stage",
        choices=["phone_screen", "technical_screen", "final_round"],
        default="technical_screen",
        help="Interview stage — gates document scope (default: technical_screen)",
    )
    parser.add_argument("--out", type=Path, help="Output DOCX file path")
    parser.add_argument(
        "--update-star-bank",
        action="store_true",
        help="Write updated last_used/used_for back to stories.yaml "
        "for every STAR story selected in this run",
    )
    parser.add_argument(
        "--company-research",
        type=Path,
        help="Path to a text file of company-research prose (e.g. web_search findings — "
        "never fabricated by this script)",
    )
    parser.add_argument(
        "--recruiter-briefing",
        type=Path,
        help="Path to a text file with a pasted recruiter briefing",
    )
    parser.add_argument(
        "--qa-cards",
        type=Path,
        help="Path to a JSON file of LLM-authored Q&A cards "
        '(list of {"question", "answer", optional "tip"/"category"})',
    )
    parser.add_argument(
        "--salary-section",
        type=Path,
        help="Path to a text file of salary/negotiation prose (rendered only when "
        "--stage final_round)",
    )
    args = parser.parse_args(argv)

    try:
        require_path(args.jd, "JD file")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    company_research = None
    recruiter_briefing = None
    qa_cards_json = None
    salary_section = None
    try:
        if args.company_research is not None:
            require_path(args.company_research, "Company research file")
            company_research = args.company_research.read_text(encoding="utf-8")
        if args.recruiter_briefing is not None:
            require_path(args.recruiter_briefing, "Recruiter briefing file")
            recruiter_briefing = args.recruiter_briefing.read_text(encoding="utf-8")
        if args.qa_cards is not None:
            require_path(args.qa_cards, "Q&A cards file")
            qa_cards_json = args.qa_cards.read_text(encoding="utf-8")
        if args.salary_section is not None:
            require_path(args.salary_section, "Salary section file")
            salary_section = args.salary_section.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return emit(
        run(
            args.jd.read_text(encoding="utf-8"),
            source=args.jd,
            out=args.out,
            stage=args.stage,
            update_star_bank=args.update_star_bank,
            company_research=company_research,
            recruiter_briefing=recruiter_briefing,
            qa_cards_json=qa_cards_json,
            salary_section=salary_section,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
