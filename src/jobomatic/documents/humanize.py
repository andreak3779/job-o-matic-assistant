"""Flag wording that makes recruiter-facing documents read as AI-generated.

Letters and resumes go to hiring managers, so they should sound like a
person: professional but relaxed, plain words, no hype. ``find_ai_tells``
is a lint pass (it never rewrites text); ``add_paragraph`` calls it and
prints warnings to stderr so a human can fix the copy before sending.
"""

from __future__ import annotations

import re

_PHRASES = (
    r"excited (?:to|about)",
    r"thrilled",
    r"eager to",
    r"passionate about",
    r"i am writing (?:to|in)",
    r"i would welcome",
    r"i'?d welcome",
    r"welcome the opportunity",
    r"don'?t hesitate to",
    r"proven track record",
    r"results-driven",
    r"detail-oriented",
    r"team player",
    r"dynamic",
    r"leverag(?:e|ed|ing)",
    r"spearhead(?:ed|ing)?",
    r"synerg\w+",
    r"seamless(?:ly)?",
    r"cutting-edge",
    r"delve",
    r"tapestry",
    r"testament to",
    r"robust",
    r"holistic",
    r"scale that impact",
    r"exactly where my background",
    r"lines? up with what the team needs",
    r"production-level depth",
    r"utiliz(?:e|ed|ing)",
)
_PATTERNS = [(p, re.compile(rf"\b{p}\b", re.IGNORECASE)) for p in _PHRASES]


def find_ai_tells(text: str) -> list[str]:
    """Return the stock-AI phrases (and heavy em-dash use) found in ``text``."""
    hits = [m.group(0).lower() for _, rx in _PATTERNS for m in rx.finditer(text)]
    if text.count("—") >= 2:
        hits.append("em dashes (2+ in one paragraph)")
    return hits
