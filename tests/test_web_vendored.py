"""The vendored htmx file is the one that was checked, and is set up safely (ADR 0025)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "jobomatic" / "interfaces" / "web"
HTMX = WEB / "static" / "htmx.min.js"
NOTE = (WEB / "static" / "VENDORED.md").read_text(encoding="utf-8")
BASE = (WEB / "templates" / "base.html").read_text(encoding="utf-8")


def test_the_file_is_the_one_recorded_in_vendored_md() -> None:
    recorded = re.search(r"SHA-256 of the file[^`]*`([0-9a-f]{64})`", NOTE)
    assert recorded, "VENDORED.md records no SHA-256"
    assert hashlib.sha256(HTMX.read_bytes()).hexdigest() == recorded.group(1)


def test_the_note_names_the_version_the_file_reports() -> None:
    version = re.search(r'version:"(\d+\.\d+\.\d+)"', HTMX.read_text(encoding="utf-8"))
    assert version and f"htmx {version.group(1)}" in NOTE


def test_the_licence_text_ships_with_it() -> None:
    assert "Zero-Clause BSD" in (WEB / "static" / "htmx.LICENSE").read_text(encoding="utf-8")


def test_the_settings_are_the_safe_ones() -> None:
    meta = re.search(r"<meta name=\"htmx-config\" content='([^']+)'", BASE)
    assert meta, "base.html has no htmx-config"
    settings = json.loads(meta.group(1))
    assert settings["selfRequestsOnly"] is True
    assert settings["allowEval"] is False
    assert settings["allowScriptTags"] is False
    assert settings["historyEnabled"] is False
    assert settings["includeIndicatorStyles"] is False


def test_only_a_400_and_success_are_swapped_so_no_error_page_lands_in_a_row() -> None:
    meta = re.search(r"<meta name=\"htmx-config\" content='([^']+)'", BASE)
    assert meta
    rules = json.loads(meta.group(1))["responseHandling"]
    swapped = {r["code"] for r in rules if r["swap"]}
    assert swapped == {"[23]..", "400"}
    # Anything else that fails is an error event, which static/app.js turns into a visible message.
    assert {"code": "[45]..", "swap": False, "error": True} in rules


def test_the_failure_script_is_ours_loaded_from_this_server_and_writes_text_only() -> None:
    assert "{{ url_for('static', filename='app.js') }}" in BASE
    script = (WEB / "static" / "app.js").read_text(encoding="utf-8")
    for event in ("htmx:responseError", "htmx:sendError"):
        assert event in script
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "document.write"):
        assert unsafe not in script, unsafe


def test_every_setting_named_is_one_this_version_has() -> None:
    meta = re.search(r"<meta name=\"htmx-config\" content='([^']+)'", BASE)
    assert meta
    source = HTMX.read_text(encoding="utf-8")
    for key in json.loads(meta.group(1)):
        assert key in source, f"{key} is not an htmx setting in this version"


def test_the_scripts_are_loaded_from_this_server_only() -> None:
    # htmx, then our own small file; nothing else, and always through url_for (never a full URL).
    assert re.findall(r"<script[^>]*\ssrc=\"([^\"]+)\"", BASE) == [
        "{{ url_for('static', filename='htmx.min.js') }}",
        "{{ url_for('static', filename='app.js') }}",
    ]


def test_no_template_runs_code_through_htmx() -> None:
    for path in (WEB / "templates").glob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\bhx-on\b|hx-on[:\-]", text), path.name
        assert not re.search(r"\bjs:", text), path.name
        assert "hx-vars" not in text, path.name


def test_the_private_value_scans_skip_only_this_vendored_file() -> None:
    """The scan reads a short word in the minified file as an employer name, which is a coincidence
    in somebody else's code. The exemption is safe only because the file's hash is pinned above, and
    it must not turn into a place to park other files."""
    root = Path(__file__).resolve().parents[1]
    entries = {
        line.strip()
        for line in (root / "scripts" / "pii-allowlist.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    assert entries <= {"src/jobomatic/interfaces/web/static/htmx.min.js"}
