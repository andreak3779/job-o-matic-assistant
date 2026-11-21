"""The skim budget: a recruiter should know in 15 seconds whether the candidate fits (ADR 0035).

A reader gives a resume or a cover letter about fifteen seconds before deciding. In that time they
read the top of the page and the bold labels, not the paragraphs. So the budget is on what sits
where the eye goes first: a one-line headline, a short summary, a few skill lines that name the
posting's own terms first, short bullets, and a letter whose hook, labels and ask can be read alone.

``problems`` lists every way a document is over its budget, each naming the field and the limit, so
whoever wrote it (the generators, or a model writing the content) can fix exactly that. ``shorten``
cuts prose to a budget at a sentence or clause boundary, never mid-thought, so the generators can
meet it from the profile's longer text without rewriting a fact.

Pure: it reads the content models and nothing else.
"""

from __future__ import annotations

import re
from typing import Any

from jobomatic.documents.budget import (
    BRING_BODY_WORDS,
    BRING_ITEMS,
    BRING_LABEL_CHARS,
    BULLET_WORDS,
    CLOSING_SENTENCES,
    CLOSING_WORDS,
    HIGHLIGHT_BODY_WORDS,
    HIGHLIGHT_LABEL_WORDS,
    HOOK_SENTENCES,
    HOOK_WORDS,
    JOB_BULLETS,
    LETTER_WORDS,
    SKILL_LINE_WORDS,
    SKILL_LINES,
    SUMMARY_WORDS,
    TAGLINE_CHARS,
    TAGLINE_WORDS,
)
from jobomatic.documents.model import TailoredCoverLetter, TailoredResume

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_SEMICOLON = re.compile(r";\s+")
_COMMA = re.compile(r",\s+|\s+[—–]\s+")
_TRAILING = " ,;:—–-"
_DANGLING = {"and", "or", "with", "the", "a", "an", "of", "to", "in", "for", "using", "via", "by"}


def words(text: str) -> int:
    return len(text.split())


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_BREAK.split(text.strip()) if s]


def shorten(text: str, max_words: int) -> str:
    """``text`` cut to at most ``max_words``, at the last whole sentence, else the last whole
    clause (after a semicolon, then a comma or dash), else at a word. Never adds a word."""
    text = " ".join(text.split())
    if words(text) <= max_words:
        return text
    floor = max(1, max_words // 3)  # a stub of a few words is worse than a longer clause
    for pattern, joiner in ((_SENTENCE_BREAK, " "), (_SEMICOLON, "; "), (_COMMA, ", ")):
        kept: list[str] = []
        for part in pattern.split(text):
            if words(joiner.join([*kept, part])) > max_words:
                break
            kept.append(part)
        cut = joiner.join(kept).rstrip(_TRAILING)
        if kept and words(cut) >= floor:
            return cut
    cut_words = text.split()[:max_words]
    while len(cut_words) > 1 and cut_words[-1].lower().strip(_TRAILING) in _DANGLING:
        cut_words.pop()
    return " ".join(cut_words).rstrip(_TRAILING)


def pick_sentences(text: str, max_words: int, score: Any) -> str:
    """The most relevant whole sentences of ``text`` that fit ``max_words``, in their own order.

    ``score(sentence)`` is higher for a sentence that speaks to the posting. The first sentence
    is always kept (it says who this is); the rest are added best-first while they fit.
    """
    parts = sentences(" ".join(text.split()))
    if words(" ".join(parts)) <= max_words:
        return " ".join(parts)
    chosen = {0}
    used = words(parts[0]) if parts else 0
    if used > max_words:
        return shorten(parts[0], max_words)
    order = sorted(range(1, len(parts)), key=lambda i: (-score(parts[i]), i))
    for i in order:
        if used + words(parts[i]) <= max_words:
            chosen.add(i)
            used += words(parts[i])
    return " ".join(parts[i] for i in sorted(chosen))


# -- what is over budget ------------------------------------------------------------------------


def _over(field: str, count: int, limit: int, unit: str = "words", advice: str = "") -> str:
    tail = f"; {advice}" if advice else ""
    return f"{field}: {count} {unit}, the limit is {limit}{tail}"


def resume_problems(resume: TailoredResume) -> list[str]:
    found: list[str] = []
    if words(resume.tagline) > TAGLINE_WORDS or len(resume.tagline) > TAGLINE_CHARS:
        found.append(
            _over(
                "tagline",
                words(resume.tagline),
                TAGLINE_WORDS,
                advice=f"one line under {TAGLINE_CHARS} characters, 'Role | A · B · C'",
            )
        )
    summary = sum(words(p) for p in resume.summary)
    if summary > SUMMARY_WORDS:
        found.append(
            _over(
                "summary",
                summary,
                SUMMARY_WORDS,
                advice="keep the sentences that speak to this posting",
            )
        )
    if len(resume.skills) > SKILL_LINES:
        found.append(_over("skills", len(resume.skills), SKILL_LINES, "lines"))
    for i, line in enumerate(resume.skills):
        if words(line.skills) > SKILL_LINE_WORDS:
            found.append(
                _over(
                    f"skills[{i}] ({line.label})",
                    words(line.skills),
                    SKILL_LINE_WORDS,
                    advice="the posting's own terms first, the rest dropped",
                )
            )
    for i, job in enumerate(resume.experience):
        where = f"experience[{i}] ({job.title})"
        if len(job.bullets) > JOB_BULLETS:
            found.append(_over(where, len(job.bullets), JOB_BULLETS, "bullets"))
        for j, bullet in enumerate(job.bullets):
            if words(bullet) > BULLET_WORDS:
                found.append(
                    _over(
                        f"{where} bullet {j}",
                        words(bullet),
                        BULLET_WORDS,
                        advice="one fact, one result",
                    )
                )
    return found


def letter_problems(letter: TailoredCoverLetter) -> list[str]:
    found: list[str] = []
    if words(letter.hook) > HOOK_WORDS or len(sentences(letter.hook)) > HOOK_SENTENCES:
        found.append(
            _over(
                "hook", words(letter.hook), HOOK_WORDS, advice=f"at most {HOOK_SENTENCES} sentences"
            )
        )
    if len(letter.bring) > BRING_ITEMS:
        found.append(_over("bring", len(letter.bring), BRING_ITEMS, "items"))
    for i, item in enumerate(letter.bring):
        if len(item.label) > BRING_LABEL_CHARS:
            found.append(
                _over(
                    f"bring[{i}].label",
                    len(item.label),
                    BRING_LABEL_CHARS,
                    "characters",
                    "a few words, bold",
                )
            )
        if words(item.body) > BRING_BODY_WORDS:
            found.append(_over(f"bring[{i}].body", words(item.body), BRING_BODY_WORDS))
    for i, item in enumerate(letter.highlights):
        if words(item.label) > HIGHLIGHT_LABEL_WORDS:
            found.append(_over(f"highlights[{i}].label", words(item.label), HIGHLIGHT_LABEL_WORDS))
        if words(item.body) > HIGHLIGHT_BODY_WORDS:
            found.append(_over(f"highlights[{i}].body", words(item.body), HIGHLIGHT_BODY_WORDS))
    if words(letter.closing) > CLOSING_WORDS or len(sentences(letter.closing)) > CLOSING_SENTENCES:
        found.append(
            _over(
                "closing",
                words(letter.closing),
                CLOSING_WORDS,
                advice=f"at most {CLOSING_SENTENCES} sentences",
            )
        )
    total = letter_words(letter)
    if total > LETTER_WORDS:
        found.append(
            _over("the letter as a whole", total, LETTER_WORDS, advice="cut the weakest item")
        )
    return found


def letter_words(letter: TailoredCoverLetter) -> int:
    parts = [letter.hook, letter.closing]
    parts += [f"{i.label} {i.body}" for i in (*letter.bring, *letter.highlights)]
    return sum(words(p) for p in parts)


def problems(content: Any) -> list[str]:
    """Every way ``content`` is over the skim budget. Empty for a kind with no budget."""
    if isinstance(content, TailoredResume):
        return resume_problems(content)
    if isinstance(content, TailoredCoverLetter):
        return letter_problems(content)
    return []
