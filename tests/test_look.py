"""The shared look: one token file, verbatim copies, and contrast that stays true (ADR 0025).

``src/jobomatic/branding/tokens.css`` is the one source. A standalone page opens from disk, so it
cannot link a stylesheet; it embeds a verbatim copy between ``tokens:start`` and ``tokens:end``.
The web UI serves the file itself. These tests keep the copies equal, keep every text colour above
the WCAG ratio it needs, and keep the pages from fetching anything.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / "src" / "jobomatic" / "branding"
TOKENS = (BRANDING / "tokens.css").read_text(encoding="utf-8")
STANDALONE = [ROOT / "site" / "index.html", ROOT / "templates" / "pluralsight_import_template.html"]
START, END = "/* tokens:start */", "/* tokens:end */"


def _block(text: str) -> str:
    assert START in text and END in text, "no tokens:start / tokens:end markers"
    return text[text.index(START) : text.index(END) + len(END)]


def _declarations(css: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", css))


def _modes() -> tuple[dict[str, str], dict[str, str]]:
    """The light values, and the dark values (light ones that dark does not override stay)."""
    block = _block(TOKENS)
    light = _declarations(block[block.index(":root {") : block.index("@media")])
    media = block[block.index("@media") : block.index(':root[data-theme="dark"]')]
    dark = {**light, **_declarations(media)}
    return light, dark


# -- the copies --------------------------------------------------------------------------------


@pytest.mark.parametrize("page", STANDALONE, ids=lambda p: p.name)
def test_every_standalone_page_embeds_the_token_file_verbatim(page: Path) -> None:
    assert _block(page.read_text(encoding="utf-8")) == _block(TOKENS)


def test_the_dark_values_are_the_same_whether_the_system_or_the_page_asks_for_dark() -> None:
    block = _block(TOKENS)
    media = block[block.index("@media") : block.index(':root[data-theme="dark"]')]
    explicit = block[block.index(':root[data-theme="dark"]') :]
    assert _declarations(media) == _declarations(explicit)


# -- contrast ----------------------------------------------------------------------------------


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _ratio(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# (foreground, background, the least ratio). 4.5 is WCAG's AA for body text; 3 is for large text
# and for the edge of a control. The light teal fails 4.5 on the cream (3.6), so it is a fill, a
# border and large text only, and small text and links use --accent-text.
PAIRS = [
    ("--text", "--bg", 4.5),
    ("--text", "--surface", 4.5),
    ("--text", "--new", 4.5),
    ("--muted", "--bg", 4.5),
    ("--muted", "--surface", 4.5),
    ("--muted", "--new", 4.5),
    ("--accent-text", "--bg", 4.5),
    ("--accent-text", "--surface", 4.5),
    ("--accent-text", "--new", 4.5),
    ("--accent-ink", "--accent-text", 4.5),  # a button's label on its fill
    ("--accent-ink", "--accent", 3.0),  # large text on the light fill
    ("--pink-ink", "--pink", 4.5),
    ("--pink", "--bg", 4.5),
    ("--ok", "--surface", 4.5),
    ("--warn", "--surface", 4.5),
    ("--err", "--surface", 4.5),
    ("--ok", "--bg", 4.5),
    ("--warn", "--bg", 4.5),
    ("--err", "--bg", 4.5),
    ("--navy", "--sun", 4.5),  # the header band
    ("--fit-ink", "--fit-pass", 4.5),
    ("--fit-ink", "--fit-stretch", 4.5),
    ("--fit-ink", "--fit-worth", 4.5),
    ("--fit-ink", "--fit-good", 4.5),
    ("--fit-ink", "--fit-strong", 4.5),
    ("--muted", "--bg", 3.0),  # the edge of an input is drawn in --muted
]


@pytest.mark.parametrize("mode", [0, 1], ids=["light", "dark"])
def test_every_text_pair_meets_its_contrast_ratio(mode: int) -> None:
    values = _modes()[mode]
    failing = [
        f"{fg} on {bg}: {_ratio(values[fg], values[bg]):.2f} < {need}"
        for fg, bg, need in PAIRS
        if _ratio(values[fg], values[bg]) < need
    ]
    assert not failing, "\n".join(failing)


def test_the_figures_the_adr_quotes_are_true() -> None:
    light, _ = _modes()
    assert round(_ratio(light["--accent"], light["--bg"]), 1) == 3.6
    assert round(_ratio(light["--accent-text"], light["--bg"]), 1) == 5.6
    assert round(_ratio(light["--accent-ink"], light["--accent-text"]), 1) == 6.0
    assert round(_ratio(light["--text"], light["--bg"]), 1) == 14.5


# -- the rest of the look ----------------------------------------------------------------------


@pytest.mark.parametrize("page", STANDALONE, ids=lambda p: p.name)
def test_the_light_teal_is_never_used_for_text(page: Path) -> None:
    css = re.sub(r"/\*.*?\*/", "", page.read_text(encoding="utf-8"), flags=re.DOTALL)
    assert not re.search(r"(?<![-\w])color:\s*var\(--accent\)", css)


@pytest.mark.parametrize("page", STANDALONE, ids=lambda p: p.name)
def test_a_standalone_page_fetches_nothing_from_another_origin(page: Path) -> None:
    html = page.read_text(encoding="utf-8")
    fetched = re.findall(r'<(?:script|img|source|iframe)\b[^>]*\ssrc="(https?:[^"]+)"', html)
    fetched += re.findall(r'<link\b[^>]*\shref="(https?:[^"]+)"', html)
    fetched += re.findall(r"url\(\s*['\"]?(https?:[^)'\"]+)", html)
    fetched += re.findall(r"@import\s+['\"]?(https?:[^;'\"]+)", html)
    assert not fetched, fetched


def test_the_pluralsight_page_embeds_the_gauge_icon_byte_for_byte() -> None:
    html = (ROOT / "templates" / "pluralsight_import_template.html").read_text(encoding="utf-8")
    original = (BRANDING / "job-o-matic-icon.svg").read_bytes()
    embedded = re.findall(r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)", html)
    assert len(embedded) == 2  # the favicon and the header mark
    assert all(base64.b64decode(e) == original for e in embedded)


def test_every_control_on_the_pluralsight_page_has_a_label() -> None:
    """A placeholder is not a label: each control has an aria-label or a <label for=...>."""
    html = (ROOT / "templates" / "pluralsight_import_template.html").read_text(encoding="utf-8")
    for tag in re.findall(r"<(?:input|select|textarea)\b[^>]*>", html):
        found = re.search(r'\bid="([^"]+)"', tag)
        named = re.search(r"\baria-label(?:ledby)?=", tag)
        labelled = found is not None and f'for="{found.group(1)}"' in html
        assert named or labelled, tag
