"""The applications page of the local web UI (ADR 0025): the list, and the way to change a status."""

from __future__ import annotations

import html

import pytest

pytest.importorskip("flask")

from jobomatic import applications as apps  # noqa: E402
from jobomatic import paths  # noqa: E402
from tests.web_support import Browser, signed_in  # noqa: E402


@pytest.fixture
def browser() -> Browser:
    return signed_in()


def _page(reply) -> str:  # type: ignore[no-untyped-def]
    return reply.get_data(as_text=True)


def _draft(company: str = "Acme", title: str = "Dev") -> str:
    return apps.create_application(company, title)


def _log_bytes() -> bytes:
    log = paths.applications_log()
    return log.read_bytes() if log.exists() else b""


def test_the_page_lists_the_log_with_the_same_rows_as_the_command(browser: Browser) -> None:
    ids = [_draft("Acme", "Dev"), _draft("Globex", "Engineer")]
    page = _page(browser.get("/applications"))
    for name in ("Acme", "Dev", "Globex", "Engineer"):
        assert name in page
    for application_id in ids:
        assert f'id="row-{application_id}"' in page


def test_an_empty_log_says_so(browser: Browser) -> None:
    assert "No applications match." in _page(browser.get("/applications"))


def test_the_filters_narrow_the_list_like_the_command(browser: Browser) -> None:
    drafted = _draft("Acme", "Dev")
    other = _draft("Globex", "Engineer")
    apps.set_status(other, "technical")
    by_status = _page(browser.get("/applications?status=technical"))
    assert "Globex" in by_status and "Acme" not in by_status
    by_company = _page(browser.get("/applications?company=Acme"))
    assert "Acme" in by_company and "Globex" not in by_company
    assert f"row-{drafted}" in by_company


def test_an_unknown_status_in_the_filter_is_a_message_not_a_trace(browser: Browser) -> None:
    page = _page(browser.get("/applications?status=banana"))
    assert 'role="alert"' in page and "Traceback" not in page


def test_every_control_in_a_row_names_the_row_it_changes(browser: Browser) -> None:
    _draft("Acme", "Dev")
    page = _page(browser.get("/applications"))
    assert "New status for Acme, Dev" in page and "Next step for Acme, Dev" in page


def test_a_status_change_is_recorded_and_shown(browser: Browser) -> None:
    application_id = _draft()
    reply = browser.post(
        f"/applications/{application_id}/status",
        {"status": "phone_screen", "next_step": "Call on Friday"},
    )
    assert reply.status_code == 302 and reply.headers["Location"].endswith("/applications")
    page = _page(browser.get("/applications"))
    assert "phone_screen" in page and "Call on Friday" in page
    assert apps.get_application(application_id).status == "phone_screen"


def test_the_log_only_grows_when_a_status_changes(browser: Browser) -> None:
    application_id = _draft()
    before = _log_bytes()
    browser.post(f"/applications/{application_id}/status", {"status": "technical"})
    after = _log_bytes()
    assert after.startswith(before) and len(after) > len(before)


def test_a_partial_update_returns_just_the_row(browser: Browser) -> None:
    application_id = _draft()
    reply = browser.post(
        f"/applications/{application_id}/status",
        {"status": "offer"},
        headers={"HX-Request": "true"},
    )
    body = _page(reply)
    assert reply.status_code == 200
    assert body.lstrip().startswith("<tr") and "offer" in body
    assert "<html" not in body


def test_a_status_control_cannot_set_applied(browser: Browser) -> None:
    application_id = _draft()
    before = _log_bytes()
    for status in ("applied", "drafted", "banana", ""):
        reply = browser.post(f"/applications/{application_id}/status", {"status": status})
        assert reply.status_code == 400, status
    assert _log_bytes() == before
    assert apps.get_application(application_id).status == "drafted"


def test_the_applied_action_is_not_among_the_status_options(browser: Browser) -> None:
    application_id = _draft()
    page = _page(browser.get("/applications"))
    start = page.index(f'id="status-{application_id}"')
    row_select = page[start : page.index("</select>", start)]
    assert 'value="applied"' not in row_select and 'value="drafted"' not in row_select
    assert 'value="offer"' in row_select


def test_marking_applied_asks_first_and_names_the_posting(browser: Browser) -> None:
    application_id = _draft("Acme", "Staff Developer")
    page = _page(browser.get(f"/applications/{application_id}/applied"))
    assert "Acme" in page and "Staff Developer" in page and "you submitted" in page
    assert apps.get_application(application_id).status == "drafted"  # asking changed nothing


def test_marking_applied_happens_only_on_the_confirmed_post(browser: Browser) -> None:
    application_id = _draft("Acme", "Dev")
    reply = browser.post(f"/applications/{application_id}/applied")
    assert reply.status_code == 302
    done = apps.get_application(application_id)
    assert done.status == "applied" and done.applied_on
    assert "Marked applied" in _page(browser.get("/applications"))


def test_a_submitted_row_offers_no_mark_applied_link(browser: Browser) -> None:
    application_id = _draft()
    apps.mark_applied(application_id, None)
    assert "Mark applied…" not in _page(browser.get("/applications"))


def test_an_unknown_application_is_a_404_not_a_trace(browser: Browser) -> None:
    assert browser.get("/applications/nope/applied").status_code == 404
    assert browser.post("/applications/nope/applied").status_code == 404
    reply = browser.post("/applications/nope/status", {"status": "offer"})
    assert reply.status_code == 400 and "Traceback" not in _page(reply)


def test_company_names_with_markup_are_shown_as_text(browser: Browser) -> None:
    _draft("<script>alert(1)</script>", "<img src=x onerror=alert(2)>")
    page = _page(browser.get("/applications"))
    assert "<script>alert(1)" not in page and "<img src=x" not in page
    assert html.escape("<script>alert(1)</script>") in page


def test_no_change_is_accepted_without_the_form_token_or_origin(browser: Browser) -> None:
    application_id = _draft()
    before = _log_bytes()
    no_token = browser.client.post(
        f"/applications/{application_id}/status",
        data={"status": "offer"},
        headers={"Origin": "http://127.0.0.1:5000"},
        base_url="http://127.0.0.1:5000",
    )
    foreign = browser.client.post(
        f"/applications/{application_id}/applied",
        data={"csrf": browser.csrf},
        headers={"Origin": "http://evil.test"},
        base_url="http://127.0.0.1:5000",
    )
    assert no_token.status_code == 403 and foreign.status_code == 403
    assert _log_bytes() == before
