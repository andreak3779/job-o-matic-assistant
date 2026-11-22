"""A form that ran a command answers with a redirect, so a reload never runs it again (ADR 0025)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("flask")

from jobomatic import paths  # noqa: E402
from jobomatic.commands import fit_check, profile  # noqa: E402
from jobomatic.interfaces.web import documents_page, fit_page  # noqa: E402
from jobomatic.interfaces.web.downloads import MAX_ISSUED, Downloads  # noqa: E402
from jobomatic.interfaces.web.results import MAX_HELD, Results  # noqa: E402
from tests.command_cases import STRONG  # noqa: E402
from tests.web_support import Browser, signed_in  # noqa: E402

STRONG_TEXT = STRONG.read_text(encoding="utf-8")


@pytest.fixture
def browser() -> Browser:
    return signed_in()


def _body(reply) -> str:  # type: ignore[no-untyped-def]
    return reply.get_data(as_text=True)


# -- the redirect -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "data", "result_prefix"),
    [
        ("/fit", {"posting": STRONG_TEXT}, "/fit/result/"),
        ("/documents", {"posting": STRONG_TEXT}, "/documents/result/"),
        ("/profile", {}, "/profile/result/"),
    ],
)
def test_a_post_that_ran_a_command_redirects_to_its_result(
    browser: Browser, path: str, data: dict, result_prefix: str
) -> None:
    reply = browser.post(path, data, follow_redirects=False)
    assert reply.status_code == 303  # "see other": the next request is a GET
    assert reply.headers["Location"].startswith(result_prefix)


def test_the_result_page_is_the_page_the_post_used_to_return(browser: Browser) -> None:
    shown = fit_check.run(STRONG_TEXT).data
    page = _body(browser.post("/fit", {"posting": STRONG_TEXT}))
    assert shown.fit.rating in page and "Have you applied before?" in page


def test_reloading_the_fit_result_does_not_run_the_check_again(
    browser: Browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real = fit_check.run
    monkeypatch.setattr(fit_page.fit_check, "run", lambda *a, **k: calls.append(1) or real(*a, **k))
    location = browser.post("/fit", {"posting": STRONG_TEXT}, follow_redirects=False).headers[
        "Location"
    ]
    first, second = _body(browser.get(location)), _body(browser.get(location))
    assert first == second and calls == [1]


def test_reloading_the_documents_result_writes_nothing_more(browser: Browser) -> None:
    location = browser.post("/documents", {"posting": STRONG_TEXT}, follow_redirects=False).headers[
        "Location"
    ]
    written = sorted(paths.outputs_dir().rglob("*"))
    again = browser.get(location)
    assert again.status_code == 200 and "Your files" in _body(again)
    assert sorted(paths.outputs_dir().rglob("*")) == written
    # the files offered on the held page still download
    link = _body(again).split('href="/download/', 1)[1].split('"', 1)[0]
    assert browser.get(f"/download/{link}").status_code == 200


def test_a_held_override_question_survives_a_reload(browser: Browser) -> None:
    posting = "# Dev | Acme Corp\n\n## Requirements\n- Haskell\n- Erlang\n- COBOL\n- Fortran\n"
    location = browser.post("/documents", {"posting": posting}, follow_redirects=False).headers[
        "Location"
    ]
    assert "refused" in _body(browser.get(location))


def test_an_empty_posting_is_still_answered_in_place(browser: Browser) -> None:
    for path in ("/fit", "/documents"):
        reply = browser.post(path, {"posting": "  "}, follow_redirects=False)
        assert reply.status_code == 400 and "Paste a posting first." in _body(reply)


# -- an id that is not held ---------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/fit/result/unknown", "/documents/result/unknown"])
def test_an_unknown_result_says_it_is_gone_and_offers_the_form(browser: Browser, path: str) -> None:
    reply = browser.get(path)
    assert reply.status_code == 404
    page = _body(reply)
    assert "no longer held" in page and 'name="posting"' in page


def test_an_unknown_profile_result_goes_back_to_the_form(browser: Browser) -> None:
    reply = browser.get("/profile/result/unknown", follow_redirects=False)
    assert reply.status_code == 303 and reply.headers["Location"] == "/profile"


def test_a_result_is_served_only_by_the_page_that_made_it(browser: Browser) -> None:
    fit_id = (
        browser.post("/fit", {"posting": STRONG_TEXT}, follow_redirects=False)
        .headers["Location"]
        .rsplit("/", 1)[1]
    )
    assert browser.get(f"/documents/result/{fit_id}").status_code == 404
    assert browser.get(f"/profile/result/{fit_id}", follow_redirects=False).status_code == 303


def test_the_profile_result_is_held_too(browser: Browser) -> None:
    location = browser.post("/profile", follow_redirects=False).headers["Location"]
    page = _body(browser.get(location))
    assert profile.validate().status in ("ok", "error", "refused") and "<h2" in page


# -- the stores are bounded ---------------------------------------------------------------------


def test_only_the_newest_results_are_kept() -> None:
    results = Results()
    ids = [results.hold("fit", {"n": n}) for n in range(MAX_HELD + 3)]
    assert results.get("fit", ids[0]) is None and results.get("fit", ids[2]) is None
    assert results.get("fit", ids[-1]) == {"n": MAX_HELD + 2}
    assert results.get("documents", ids[-1]) is None  # an id belongs to one page


def test_only_the_newest_download_ids_are_kept(tmp_path: Path) -> None:
    downloads = Downloads()
    file = tmp_path / "resume.docx"
    file.write_bytes(b"x")
    ids = [downloads.issue(file) for _ in range(MAX_ISSUED + 5)]
    assert downloads.get(ids[0]) is None
    assert downloads.get(ids[-1]) == file


# -- templates and routes -----------------------------------------------------------------------


def test_the_result_routes_take_an_issued_id_only() -> None:
    from jobomatic.interfaces.web.app import create_app

    rules = {r.endpoint: r for r in create_app(launch_token="t").url_map.iter_rules()}
    for endpoint in ("fit_result", "documents_result", "profile_result"):
        assert rules[endpoint].arguments == {"result_id"} and rules[endpoint].methods >= {"GET"}
        assert "POST" not in rules[endpoint].methods
    assert documents_page.GONE and fit_page.GONE
