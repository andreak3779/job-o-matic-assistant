"""What every page of the local web UI must be, checked over the template files (ADR 0025).

The pages show a real profile and text that came from outside (postings, course titles, notes), so
these tests read the templates and stylesheet rather than trusting each new page to remember:
escaping stays on, nothing runs inline, nothing is fetched from elsewhere, every control is
labelled, every form carries the form token, and no route or field takes a path.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("flask")

from jobomatic.interfaces.web.app import create_app  # noqa: E402

WEB = Path(__file__).resolve().parents[1] / "src" / "jobomatic" / "interfaces" / "web"
TEMPLATES = sorted((WEB / "templates").glob("*.html"))
STATIC = sorted(p for p in (WEB / "static").iterdir() if p.is_file())
CODE = sorted(WEB.glob("*.py"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_escaping_is_never_switched_off(path: Path) -> None:
    text = _text(path)
    assert "|safe" not in text.replace(" ", "")
    assert not re.search(r"{%-?\s*autoescape\s+(false|off)", text, re.IGNORECASE)
    assert "Markup(" not in text


@pytest.mark.parametrize("path", CODE, ids=lambda p: p.name)
def test_the_code_never_marks_text_as_safe(path: Path) -> None:
    text = _text(path)
    assert "Markup(" not in text and "render_template_string" not in text
    assert "|safe" not in text


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_nothing_runs_or_is_styled_inline(path: Path) -> None:
    text = _text(path)
    assert not re.search(r"<script\b(?![^>]*\ssrc=)", text), "an inline <script>"
    assert not re.search(r"<script\b[^>]*\ssrc=\"https?:", text)
    assert not re.search(r"\son[a-z]+\s*=", text), "an inline event handler"
    assert not re.search(r"\sstyle\s*=", text), "an inline style attribute"
    assert "<style" not in text, "an inline <style> block"
    assert "javascript:" not in text.lower()


@pytest.mark.parametrize("path", [*TEMPLATES, *STATIC], ids=lambda p: p.name)
def test_nothing_is_fetched_from_another_origin(path: Path) -> None:
    text = _text(path)
    fetched = re.findall(r'\b(?:src|action|data|poster)\s*=\s*"(?:https?:)?//[^"]+', text)
    fetched += re.findall(r'<link\b[^>]*\shref="(?:https?:)?//[^"]+', text)
    fetched += re.findall(r"url\(\s*['\"]?(?:https?:)?//", text)
    fetched += re.findall(r"@import\s+['\"]?(?:https?:)?//", text)
    assert not fetched, fetched


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_every_control_has_a_label(path: Path) -> None:
    text = _text(path)
    for tag in re.findall(r"<(?:input|select|textarea)\b[^>]*>", text):
        if re.search(r'type="(hidden|submit)"', tag):
            continue
        found = re.search(r'\bid="([^"]+)"', tag)
        named = re.search(r"\baria-label(?:ledby)?=", tag)
        labelled = found is not None and f'for="{found.group(1)}"' in text
        assert named or labelled, tag


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_every_form_that_changes_something_carries_the_form_token(path: Path) -> None:
    text = _text(path)
    for form in re.findall(r"<form\b.*?</form>", text, re.DOTALL | re.IGNORECASE):
        if re.search(r'method="post"', form, re.IGNORECASE):
            assert 'name="csrf"' in form, "a POST form without the form token"


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_no_field_takes_a_path(path: Path) -> None:
    text = _text(path)
    for name in re.findall(r'<(?:input|select|textarea)\b[^>]*\sname="([^"]+)"', text):
        assert not re.search(r"(^|_)(path|dir|folder|filename|out)($|_)", name), name


def test_no_route_takes_a_path() -> None:
    app = create_app(launch_token="t")
    for rule in app.url_map.iter_rules():
        for argument in rule.arguments:
            if rule.endpoint == "static":
                continue
            assert not re.search(r"(^|_)(path|dir|folder|file|filename)($|_)", argument), (
                rule.rule,
                argument,
            )


def test_the_stylesheet_uses_the_tokens_and_no_fixed_colours() -> None:
    css = _text(WEB / "static" / "app.css")
    assert "var(--" in css
    colours = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", css)
    assert not colours, f"colours belong in branding/tokens.css: {colours}"
