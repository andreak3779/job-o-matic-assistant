"""The documents page of the local web UI (ADR 0025): the gate applies exactly as elsewhere."""

from __future__ import annotations

import json
import re

import pytest

pytest.importorskip("flask")

from jobomatic import gate, paths  # noqa: E402
from tests.command_cases import PASS_SKILLS, QUEBEC, STRETCH_SKILLS, STRONG  # noqa: E402
from tests.web_support import Browser, signed_in  # noqa: E402


@pytest.fixture
def browser() -> Browser:
    return signed_in()


def _page(reply) -> str:  # type: ignore[no-untyped-def]
    return reply.get_data(as_text=True)


def _posting(*skills: str) -> str:
    lines = "".join(f"- {s}\n" for s in skills)
    return f"# Dev | Acme Corp\n\n## Requirements\n{lines}"


STRONG_TEXT = STRONG.read_text(encoding="utf-8")


def _documents() -> list:
    return sorted(paths.outputs_dir().rglob("*.docx"))


def _generate(browser: Browser, posting: str, **fields):  # type: ignore[no-untyped-def]
    return browser.post("/documents", {"posting": posting, **fields})


def test_the_page_has_a_labelled_form_the_notice_and_no_override_box(browser: Browser) -> None:
    page = _page(browser.get("/documents"))
    assert '<label for="posting">' in page
    assert "never include self-identification" in page
    assert 'type="checkbox"' not in page


def test_a_strong_posting_writes_both_documents_and_offers_them_by_id(browser: Browser) -> None:
    page = _page(_generate(browser, STRONG_TEXT))
    assert len(_documents()) == 2
    links = re.findall(r'href="/download/([^"]+)"', page)
    assert len(links) == 2
    assert "Resume (Word document)" in page and "Cover letter (Word document)" in page
    reply = browser.get(f"/download/{links[0]}")
    assert reply.status_code == 200 and reply.data[:2] == b"PK"  # a .docx is a zip file


def test_only_the_documents_are_offered_not_their_provenance_files(browser: Browser) -> None:
    page = _page(_generate(browser, STRONG_TEXT))
    written = {p.name for p in paths.outputs_dir().rglob("*") if p.is_file()}
    assert any(name.endswith(".meta.json") for name in written)  # the sidecars exist...
    assert ".meta.json" not in page and ".raw-inputs" not in page  # ...and are not offered


def test_the_downloads_are_files_the_result_listed(browser: Browser) -> None:
    _generate(browser, STRONG_TEXT)
    issued = browser.app.extensions["downloads"]._paths.values()
    outputs = paths.outputs_dir().resolve()
    assert issued and all(p.resolve().is_relative_to(outputs) for p in issued)


def test_a_stretch_is_refused_with_one_unticked_box_and_writes_nothing(browser: Browser) -> None:
    page = _page(_generate(browser, _posting(*STRETCH_SKILLS)))
    assert _documents() == []
    assert (
        "Resume: refused" in page and "Cover letter:" not in page
    )  # it stops at the first refusal
    assert f'name="{gate.CONFIRM_GAPS}"' in page
    box = re.search(r'<input[^>]*name="confirm_gaps"[^>]*>', page)
    assert box and "checked" not in box.group(0)
    assert page.count('type="checkbox"') == 1


def test_ticking_the_box_is_a_decision_that_lets_the_stretch_through(browser: Browser) -> None:
    posting = _posting(*STRETCH_SKILLS)
    _generate(browser, posting)
    assert _documents() == []
    page = _page(_generate(browser, posting, confirm_gaps="on"))
    assert len(_documents()) == 2 and "Resume: written" in page


def test_a_skills_pass_has_no_box_and_cannot_be_confirmed(browser: Browser) -> None:
    posting = _posting(*PASS_SKILLS)
    refused = _page(_generate(browser, posting))
    assert "cannot be confirmed past" in refused and 'type="checkbox"' not in refused
    forced = _page(_generate(browser, posting, confirm_gaps="on", confirm_reapply="on"))
    assert "cannot be confirmed past" in forced
    assert _documents() == []


def test_a_location_pass_has_no_box_and_cannot_be_confirmed(browser: Browser) -> None:
    posting = QUEBEC.read_text(encoding="utf-8")
    page = _page(_generate(browser, posting, confirm_gaps="on", confirm_reapply="on"))
    assert "cannot be confirmed past" in page and 'type="checkbox"' not in page
    assert _documents() == []


def test_a_repeat_application_asks_to_confirm_the_reapply(browser: Browser) -> None:
    from jobomatic.interfaces.cli.main import main

    assert main(["applications", "applied", "--jd", str(STRONG)]) == 0
    page = _page(_generate(browser, STRONG_TEXT))
    assert f'name="{gate.CONFIRM_REAPPLY}"' in page and _documents() == []
    page = _page(_generate(browser, STRONG_TEXT, confirm_reapply="on"))
    assert len(_documents()) == 2


def test_pay_below_the_minimum_asks_to_confirm_it(browser: Browser) -> None:
    paths.private_dir().mkdir(parents=True, exist_ok=True)
    (paths.private_dir() / "search-constraints.json").write_text(
        json.dumps({"min_permanent_base_cad": 90000}), encoding="utf-8"
    )
    posting = STRONG_TEXT + "\n\nSalary: $40,000 - $50,000 per year\n"
    page = _page(_generate(browser, posting))
    assert f'name="{gate.CONFIRM_BELOW_MINIMUM}"' in page and _documents() == []
    assert len(_documents()) == 0
    done = _page(_generate(browser, posting, confirm_below_minimum="on"))
    assert len(_documents()) == 2 and "written" in done


def test_two_overrides_in_a_row_keep_the_first_one_given_but_never_ticked_for_you(
    browser: Browser,
) -> None:
    """A Stretch that was also applied to: confirm the gaps, then the page asks about the repeat and
    carries the first answer as a hidden value, not as a ticked box."""
    from jobomatic.interfaces.cli.main import main

    lines = "".join(f"- {s}\n" for s in STRETCH_SKILLS)
    posting = f"# Developer\n\n**Company:** Acme Corp\n\n## Requirements\n{lines}"
    assert main(["applications", "applied", "--jd", str(_write(posting))]) == 0
    first = _page(_generate(browser, posting))
    assert f'name="{gate.CONFIRM_GAPS}"' in first
    second = _page(_generate(browser, posting, confirm_gaps="on"))
    assert f'name="{gate.CONFIRM_REAPPLY}"' in second
    assert 'type="hidden" name="confirm_gaps" value="on"' in second
    assert not re.search(r'type="checkbox"[^>]*checked', second)
    assert _documents() == []
    third = _page(_generate(browser, posting, confirm_gaps="on", confirm_reapply="on"))
    assert len(_documents()) == 2 and "written" in third


def _write(posting: str):  # type: ignore[no-untyped-def]
    from pathlib import Path

    path = Path(paths.vault_root()).parent / "posting.md"
    path.write_text(posting, encoding="utf-8")
    return path


def test_an_unknown_override_in_the_request_is_ignored(browser: Browser) -> None:
    page = _page(
        _generate(browser, _posting(*PASS_SKILLS), confirm_everything="on", override="all")
    )
    assert "cannot be confirmed past" in page and _documents() == []


def test_an_empty_posting_is_a_message(browser: Browser) -> None:
    reply = _generate(browser, "  ")
    assert reply.status_code == 400 and "Paste a posting first." in _page(reply)


def test_a_posting_with_markup_is_shown_as_text(browser: Browser) -> None:
    posting = "# <script>alert(1)</script> | <img src=x onerror=alert(2)>\n\n## Requirements\n- Rust\n- Kotlin\n"
    page = _page(_generate(browser, posting))
    assert "<script>alert(1)" not in page and "<img src=x" not in page


def test_generating_needs_the_form_token_and_origin(browser: Browser) -> None:
    no_token = browser.client.post(
        "/documents",
        data={"posting": STRONG_TEXT},
        headers={"Origin": "http://127.0.0.1:5000"},
        base_url="http://127.0.0.1:5000",
    )
    foreign = browser.client.post(
        "/documents",
        data={"posting": STRONG_TEXT, "csrf": browser.csrf},
        headers={"Origin": "http://evil.test"},
        base_url="http://127.0.0.1:5000",
    )
    assert no_token.status_code == 403 and foreign.status_code == 403
    assert _documents() == []
