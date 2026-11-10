"""Per-skill gap-coaching notes, read from the vault's ``profile/gap-coaching.md``.

The markdown file is hand-written reference material, so it stays markdown and is parsed when
interview prep runs. The parser is deliberately small and fails closed on a malformed entry.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GapCoachingEntry:
    """A hand-authored coaching note for one skill gap.

    Source: ``profile/gap-coaching.md`` in the vault. Not
    part of any profile — read and parsed directly by ``interview_prep.py``,
    since it's reference material for a single skill, not a career fact.
    """

    heading: str
    status: str
    what_to_say: str
    what_not_to_say: list[str] = field(default_factory=list)
    best_star_bridge: str = ""
    honest_floor: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_gap_coaching(text: str) -> list[GapCoachingEntry]:
    """Parse ``profile/gap-coaching.md`` in the vault into typed coaching entries.

    Each ``## <Gap Type>`` section has bold-labeled fields: ``**Status:**``,
    ``**What to say:**`` (quoted framing on the following line(s)),
    ``**What not to say:**`` (usually a bullet list, occasionally a single
    inline sentence when the gap needs no hedging \u2014 see the TDD/CI-CD
    entries), ``**Best STAR bridge:**``, and ``**Honest floor:**`` (both
    inline). The trailing "Notes on Using This File" section is authoring
    guidance, not a coaching entry, and is skipped.
    """
    sections = _split_sections(text)
    entries: list[GapCoachingEntry] = []
    for heading, body in sections.items():
        if heading in ("Notes on Using This File", ""):
            continue
        entries.append(_parse_gap_coaching_block(heading, body))
    return entries


def _parse_gap_coaching_block(heading: str, block: str) -> GapCoachingEntry:
    status = ""
    what_to_say_lines: list[str] = []
    what_not_to_say: list[str] = []
    best_star_bridge = ""
    honest_floor = ""
    current_field: str | None = None

    for raw_line in block.splitlines():
        stripped = raw_line.strip()
        field_match = _STAR_FIELD_RE.match(stripped)
        if field_match:
            key, value = field_match.group(1).strip(), field_match.group(2).strip()
            key_lower = key.lower()
            current_field = None
            if key_lower == "status":
                status = value
            elif key_lower == "what to say":
                current_field = "what_to_say"
                if value:
                    what_to_say_lines.append(value)
            elif key_lower == "what not to say":
                if value:
                    what_not_to_say.append(value)
                else:
                    current_field = "what_not_to_say"
            elif key_lower == "best star bridge":
                best_star_bridge = value
            elif key_lower == "honest floor":
                honest_floor = value
        elif not stripped:
            continue
        elif current_field == "what_to_say":
            what_to_say_lines.append(stripped)
        elif current_field == "what_not_to_say" and stripped.startswith(("-", "*")):
            item = stripped.lstrip("-* ").strip()
            if item:
                what_not_to_say.append(item)

    return GapCoachingEntry(
        heading=heading,
        status=status,
        what_to_say=" ".join(what_to_say_lines).strip(),
        what_not_to_say=what_not_to_say,
        best_star_bridge=best_star_bridge,
        honest_floor=honest_floor,
    )


_STAR_HEADING_RE = re.compile(r"^##\s+Story\s+(\d+)\s+\u2014\s+(.+?)\s*$", re.MULTILINE)
_STAR_FIELD_RE = re.compile(r"^\*\*([^*]+):\*\*\s*(.*)$")
_STAR_SECTIONS = {
    "Situation": "S",
    "Task": "T",
    "Action": "A",
    "Result": "R",
}


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown into h2 sections."""
    pattern = re.compile(r"^##\s+(.*?)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[title] = text[start:end].strip()
    return sections
