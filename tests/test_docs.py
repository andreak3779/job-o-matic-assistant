"""The user-facing documents point at files and headings that exist (ADR 0026).

The setup guide was renamed and rewritten, and several files link into it, so a broken link is the
likely mistake. This reads the markdown, ignores code, and checks every relative link and anchor.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

DOCS = sorted(
    {
        ROOT / "README.md",
        ROOT / "GETTING_STARTED.md",
        ROOT / "CLAUDE.md",
        ROOT / "samples" / "README.md",
        ROOT / "skills" / "README.md",
        ROOT / "src" / "jobomatic" / "interfaces" / "mcp" / "README.md",
        *(ROOT / "docs").rglob("*.md"),
    }
)

FENCE = re.compile(r"^\s*(```|~~~)")
LINK = re.compile(r"(?<!\\)!?\[(?:[^\]\[]|\[[^\]]*\])*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _prose_lines(text: str, *, blank_code: bool = True) -> Iterator[tuple[int, str]]:
    """Each line of ``text`` outside a code fence; inline code is blanked unless ``blank_code`` is off
    (a heading keeps its code, because GitHub puts that text in the anchor)."""
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield number, INLINE_CODE.sub("", line) if blank_code else line


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, markup and punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "")
    return re.sub(r"[^\w\- ]", "", text.lower()).strip().replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for _, line in _prose_lines(path.read_text(encoding="utf-8"), blank_code=False):
        match = HEADING.match(line)
        if not match:
            continue
        base = _slug(match.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def _links(path: Path) -> Iterator[tuple[int, str]]:
    for number, line in _prose_lines(path.read_text(encoding="utf-8")):
        for match in LINK.finditer(line):
            yield number, match.group(1)


def _problems(path: Path, root: Path = ROOT) -> list[str]:
    found: list[str] = []
    for number, target in _links(path):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        file_part, _, anchor = target.partition("#")
        destination = path if not file_part else (path.parent / file_part).resolve()
        where = f"{path.relative_to(root)}:{number} -> {target}"
        if not destination.exists():
            found.append(f"{where} (no such file)")
        elif anchor and destination.suffix == ".md" and anchor not in _anchors(destination):
            found.append(f"{where} (no such heading)")
    return found


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_relative_link_and_anchor_resolves(doc: Path) -> None:
    assert _problems(doc) == []


def test_the_checker_catches_a_broken_link_and_a_broken_anchor(tmp_path: Path) -> None:
    other = tmp_path / "other.md"
    other.write_text(
        "# Real heading\n\n## Part 3: Optional extras\n\n### Page counts (`--check-pages`)\n",
        encoding="utf-8",
    )
    page = tmp_path / "page.md"
    page.write_text(
        "[ok](other.md#real-heading) [ok too](other.md#part-3-optional-extras) "
        "[code in heading](other.md#page-counts---check-pages) "
        "[missing file](gone.md) [missing heading](other.md#nope) [web](https://example.com/x)\n"
        "```text\n[in code](ignored.md)\n```\n`[inline](ignored.md)`\n",
        encoding="utf-8",
    )
    problems = _problems(page, tmp_path)
    assert len(problems) == 2
    assert "no such file" in problems[0] and "gone.md" in problems[0]
    assert "no such heading" in problems[1] and "#nope" in problems[1]
