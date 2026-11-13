"""The Pluralsight import page of the local web UI (ADR 0025): choose, see the dry run, then apply."""

from __future__ import annotations

import io
import json

import pytest

pytest.importorskip("flask")

from jobomatic import bootstrap, paths  # noqa: E402
from jobomatic.learning.adapters import pluralsight_json  # noqa: E402
from tests.web_support import BASE, Browser, signed_in  # noqa: E402


@pytest.fixture
def browser() -> Browser:
    return signed_in()


def _entry(name: str, slug: str, done: bool = True) -> dict:
    return {
        "name": name,
        "type": "Course",
        "url": f"https://app.pluralsight.com/library/courses/{slug}",
        "completion_percentage": "100.0%" if done else "40.0%",
        "completed_on": "2026-02-03",
        "completed_date": "Feb 03, 2026",
        "duration": "2h 10m",
        "view_time": "2h 0m",
        "progress": "2h 10m",
        "timing_profile": "Full Course",
    }


def _export(*entries: dict) -> bytes:
    return json.dumps(
        {
            "format": pluralsight_json.FORMAT,
            "version": pluralsight_json.VERSION,
            "generated_on": "2026-02-04",
            "entries": list(entries),
        }
    ).encode()


NEW = [
    _entry("Brand New Course One", "brand-new-one"),
    _entry("Brand New Course Two", "brand-new-two"),
]


def _upload(browser: Browser, data: bytes, name: str = "history.json"):  # type: ignore[no-untyped-def]
    return browser.post(
        "/pluralsight/preview",
        {"export": (io.BytesIO(data), name)},
        content_type="multipart/form-data",
    )


def _page(reply) -> str:  # type: ignore[no-untyped-def]
    return reply.get_data(as_text=True)


def _stored_titles() -> set[str]:
    return {item.title for item in bootstrap.learning_store().load()}


def _kept_files() -> list:
    folder = paths.imports_dir() / "pluralsight"
    return sorted(folder.glob("*")) if folder.exists() else []


def test_the_page_starts_with_a_labelled_file_choice_and_no_apply(browser: Browser) -> None:
    page = _page(browser.get("/pluralsight"))
    assert '<label for="export">' in page and 'type="file"' in page
    assert ">Apply</button>" not in page and "upload_id" not in page
    assert "/pluralsight/apply" not in page


def test_a_dry_run_shows_what_is_new_and_saves_nothing(browser: Browser) -> None:
    before, kept_before = _stored_titles(), _kept_files()
    reply = _upload(browser, _export(*NEW))
    page = _page(reply)
    assert reply.status_code == 200
    assert "2 new" in page and "Brand New Course One" in page and "Brand New Course Two" in page
    assert _stored_titles() == before and _kept_files() == kept_before


def test_apply_appears_only_after_a_dry_run_with_something_to_save(browser: Browser) -> None:
    page = _page(_upload(browser, _export(*NEW)))
    assert 'name="upload_id"' in page and ">Apply</button>" in page


def test_apply_saves_the_items_and_keeps_the_file(browser: Browser) -> None:
    page = _page(_upload(browser, _export(*NEW)))
    upload_id = page.split('name="upload_id" value="')[1].split('"')[0]
    reply = browser.post("/pluralsight/apply", {"upload_id": upload_id})
    assert reply.status_code == 200 and "2 new item(s) saved" in _page(reply)
    assert {"Brand New Course One", "Brand New Course Two"} <= _stored_titles()
    assert len(_kept_files()) == 1


def test_an_upload_can_be_applied_once_only(browser: Browser) -> None:
    page = _page(_upload(browser, _export(*NEW)))
    upload_id = page.split('name="upload_id" value="')[1].split('"')[0]
    assert browser.post("/pluralsight/apply", {"upload_id": upload_id}).status_code == 200
    again = browser.post("/pluralsight/apply", {"upload_id": upload_id})
    assert again.status_code == 400 and "expired" in _page(again)
    assert len(_kept_files()) == 1


@pytest.mark.parametrize("fake", ["", "guess", "../../etc/passwd", "/etc/passwd"])
def test_apply_cannot_name_a_file(browser: Browser, fake: str) -> None:
    before = _stored_titles()
    reply = browser.post("/pluralsight/apply", {"upload_id": fake})
    assert reply.status_code == 400 and "expired" in _page(reply)
    assert _stored_titles() == before


def test_a_file_with_nothing_new_offers_no_apply(browser: Browser) -> None:
    first = _page(_upload(browser, _export(*NEW)))
    upload_id = first.split('name="upload_id" value="')[1].split('"')[0]
    browser.post("/pluralsight/apply", {"upload_id": upload_id})
    page = _page(_upload(browser, _export(*NEW)))
    assert "There is nothing new to save." in page
    assert 'name="upload_id"' not in page and ">Apply</button>" not in page


def test_an_unfinished_course_is_not_offered(browser: Browser) -> None:
    page = _page(_upload(browser, _export(_entry("Half Done Course", "half", done=False))))
    assert "Half Done Course" not in page and 'name="upload_id"' not in page


def test_a_file_that_is_not_an_import_file_is_a_message_not_a_trace(browser: Browser) -> None:
    reply = _upload(browser, b"this is not json or a history page", "notes.txt")
    page = _page(reply)
    assert "Traceback" not in page
    assert 'role="alert"' in page and 'name="upload_id"' not in page


def test_broken_json_is_a_message_not_a_trace(browser: Browser) -> None:
    page = _page(
        _upload(browser, b'{"format": "jobomatic-pluralsight-history", "entries": [', "x.json")
    )
    assert "Traceback" not in page and 'name="upload_id"' not in page


def test_no_file_and_a_binary_file_are_refused_with_a_message(browser: Browser) -> None:
    empty = _upload(browser, b"")
    assert empty.status_code == 400 and "Choose a file first." in _page(empty)
    binary = _upload(browser, bytes(range(128, 256)) * 4, "x.html")
    assert binary.status_code == 400 and "not text" in _page(binary)


def test_a_course_title_with_markup_is_shown_as_text(browser: Browser) -> None:
    risky = _entry("<script>alert(1)</script> Course", "risky")
    page = _page(_upload(browser, _export(risky)))
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt; Course" in page


def test_the_preview_and_apply_need_the_form_token_and_origin(browser: Browser) -> None:
    before = _stored_titles()
    no_token = browser.client.post(
        "/pluralsight/preview",
        data={"export": (io.BytesIO(_export(*NEW)), "h.json")},
        content_type="multipart/form-data",
        headers={"Origin": BASE},
        base_url=BASE,
    )
    page = _page(_upload(browser, _export(*NEW)))
    upload_id = page.split('name="upload_id" value="')[1].split('"')[0]
    foreign = browser.client.post(
        "/pluralsight/apply",
        data={"upload_id": upload_id, "csrf": browser.csrf},
        headers={"Origin": "http://evil.test"},
        base_url=BASE,
    )
    assert no_token.status_code == 403 and foreign.status_code == 403
    assert _stored_titles() == before


def test_a_file_over_the_limit_is_refused_with_a_page(browser: Browser) -> None:
    reply = _upload(browser, b"x" * (2 * 1024 * 1024 + 1024))
    assert reply.status_code == 413 and "Too large" in _page(reply)


def test_a_saved_history_page_is_accepted_like_the_command_accepts_it(browser: Browser) -> None:
    # Not an import file and not a Pluralsight table: the reader says so in words.
    page = _page(_upload(browser, b"<html><body><table></table></body></html>", "saved.html"))
    assert "Traceback" not in page and 'name="upload_id"' not in page
