"""The fit page and the profile page of the local web UI (ADR 0025).

They render the same results the command line and the MCP tools return, from the typed data.
"""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import pytest

pytest.importorskip("flask")

from jobomatic import applications, paths  # noqa: E402
from jobomatic.commands import fit_check  # noqa: E402
from tests.command_cases import QUEBEC, STRONG  # noqa: E402
from tests.web_support import Browser, signed_in  # noqa: E402


@pytest.fixture
def browser() -> Browser:
    return signed_in()


def _posting(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _page(reply) -> str:  # type: ignore[no-untyped-def]
    return reply.get_data(as_text=True)


def test_the_fit_page_has_a_labelled_form_with_the_form_token(browser: Browser) -> None:
    page = _page(browser.get("/fit"))
    assert '<label for="posting">' in page and 'id="posting"' in page
    assert f'name="csrf" value="{browser.csrf}"' in page


def test_the_home_page_links_to_both_pages(browser: Browser) -> None:
    page = _page(browser.get("/"))
    assert 'href="/fit"' in page and 'href="/profile"' in page


def test_a_posting_gets_its_rating_in_words_and_its_reasons(browser: Browser) -> None:
    posting = _posting(STRONG)
    shown = fit_check.run(posting).data
    page = _page(browser.post("/fit", {"posting": posting}))
    assert (
        f'<span class="rating strong">{shown.fit.rating}</span>' in page or shown.fit.rating in page
    )
    assert html.escape(shown.fit.rationale) in page
    for match in [*shown.fit.required, *shown.fit.nice_to_have]:
        assert html.escape(match.skill) in page, match.skill


def test_the_page_is_a_rendering_of_the_result_and_drops_nothing(browser: Browser) -> None:
    posting = _posting(STRONG)
    data = fit_check.run(posting).data
    page = _page(browser.post("/fit", {"posting": posting}))
    for line in data.fit.unscored_required:
        assert html.escape(line) in page
    for soft in data.fit.soft_requirements:
        assert html.escape(soft.line) in page


def test_a_location_pass_says_pass_and_why(browser: Browser) -> None:
    posting = _posting(QUEBEC)
    data = fit_check.run(posting).data
    assert data.fit.rating == "Pass" and data.fit.location_disqualifiers
    page = _page(browser.post("/fit", {"posting": posting}))
    assert 'class="rating pass"' in page
    for reason in data.fit.location_disqualifiers:
        assert html.escape(reason) in page


def test_the_duplicate_check_is_shown_and_sees_an_earlier_application(
    browser: Browser,
) -> None:
    posting = _posting(STRONG)
    first = _page(browser.post("/fit", {"posting": posting}))
    assert "Have you applied before?" in first and "New." in first
    from jobomatic.interfaces.cli.main import main

    assert main(["applications", "applied", "--jd", str(STRONG)]) == 0
    second = _page(browser.post("/fit", {"posting": posting}))
    assert "Duplicate" in second or "Repeat" in second


def test_a_posting_with_markup_in_it_is_shown_as_text(browser: Browser) -> None:
    posting = (
        "# <script>alert('title')</script> Developer\n\n"
        "Company: <img src=x onerror=alert('company')>\n\n"
        "## Required Skills\n- <script>alert('skill')</script>\n- C#\n- SQL\n"
    )
    page = _page(browser.post("/fit", {"posting": posting}))
    assert "<script>alert" not in page
    assert (
        "onerror=alert" not in page.replace("&gt;", ">").replace("&lt;", "<").split("<textarea")[0]
    )
    assert "&lt;script&gt;" in page  # shown as text, in the textarea at the least


def test_the_pasted_text_comes_back_in_the_box_escaped(browser: Browser) -> None:
    page = _page(browser.post("/fit", {"posting": "</textarea><script>alert(1)</script>"}))
    assert "</textarea><script>" not in page
    assert "&lt;/textarea&gt;&lt;script&gt;" in page


def test_an_empty_posting_is_a_message_not_a_trace(browser: Browser) -> None:
    reply = browser.post("/fit", {"posting": "   "})
    assert reply.status_code == 400
    assert "Paste a posting first." in _page(reply)


def test_checking_a_posting_writes_nothing(browser: Browser) -> None:
    log = paths.applications_log()
    before = log.read_bytes() if log.exists() else None
    browser.post("/fit", {"posting": _posting(STRONG)})
    assert (log.read_bytes() if log.exists() else None) == before
    assert applications.find_for_jd(_posting(STRONG)) is None


def test_the_posting_is_not_accepted_without_the_form_token(browser: Browser) -> None:
    reply = browser.client.post(
        "/fit",
        data={"posting": _posting(STRONG)},
        headers={"Origin": "http://127.0.0.1:5000"},
        base_url="http://127.0.0.1:5000",
    )
    assert reply.status_code == 403


def test_the_profile_page_validates_the_demo_profile(browser: Browser) -> None:
    page = _page(browser.post("/profile"))
    assert "The profile is valid" in page
    assert re.search(r"\d+ roles, \d+ certifications, \d+ projects, \d+ stories", page)


def test_a_broken_profile_is_a_page_with_the_problem(browser: Browser) -> None:
    vault = paths.vault_root()
    shutil.rmtree(vault / "profile")
    page = _page(browser.post("/profile"))
    assert "The profile has problems" in page
    assert "Traceback" not in page
    assert 'role="alert"' in page


def test_the_profile_page_changes_nothing(browser: Browser) -> None:
    profile_dir = paths.profile_dir()
    before = {p: p.read_bytes() for p in profile_dir.rglob("*") if p.is_file()}
    browser.post("/profile")
    assert before == {p: p.read_bytes() for p in profile_dir.rglob("*") if p.is_file()}
