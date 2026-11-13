"""The snapshot tests hide machine-specific paths; they must not damage a path that merely starts
like one (ADR 0033).

With the checkout at ``/app`` (the working folder of the project's own container image), replacing
the repository path by plain substring also rewrote the ``/app`` that begins ``/applications``,
and two snapshot tests failed on every Python version.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests import test_command_snapshots as snapshots


@pytest.fixture
def at_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshots, "REPO", Path("/app"))


def test_a_checkout_at_app_does_not_damage_a_path_that_starts_with_app(
    at_app: None, tmp_path: Path
) -> None:
    scratch = Path(os.environ["JOBOMATIC_VAULT"]).parent
    text = f"{scratch}/vault/outputs/applications/2026-01-01_acme\n"
    assert snapshots._normalize(text, tmp_path) == (
        "<SCRATCH>/vault/outputs/applications/2026-01-01_acme\n"
    )


def test_the_repository_path_is_still_replaced_where_it_is_the_repository(
    at_app: None, tmp_path: Path
) -> None:
    text = "see /app/src/jobomatic/x.py and /app\n"
    assert snapshots._normalize(text, tmp_path) == "see <REPO>/src/jobomatic/x.py and <REPO>\n"


def test_a_folder_called_app_somewhere_else_is_left_alone(at_app: None, tmp_path: Path) -> None:
    assert snapshots._normalize("/home/someone/app/x", tmp_path) == "/home/someone/app/x"
    assert snapshots._normalize("/app-two/x /app.old", tmp_path) == "/app-two/x /app.old"


def test_dates_are_still_replaced_even_when_followed_by_an_underscore(tmp_path: Path) -> None:
    from datetime import date

    text = f"{date.today().isoformat()}_acme"
    assert snapshots._normalize(text, tmp_path) == "<TODAY>_acme"


def test_a_utc_timestamp_is_hidden_whatever_its_date(tmp_path: Path) -> None:
    # After 19:00 in a zone five hours behind UTC, the sidecar's UTC date is tomorrow's: the
    # snapshot tests failed every evening on such a machine until any date was matched here.
    text = '"created": "2099-01-01T01:02:03.456789Z" and "2031-12-31T23:59:59Z"'
    assert snapshots._normalize(text, tmp_path) == '"created": "<NOW>" and "<NOW>"'


def test_the_utc_date_of_today_is_hidden_as_today(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    utc_day = datetime.now(UTC).date().isoformat()
    assert snapshots._normalize(f"{utc_day}_acme", tmp_path) == "<TODAY>_acme"
