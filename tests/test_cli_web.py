"""``jobo web``: the command that starts the local web UI (ADR 0025)."""

from __future__ import annotations

import sys

import pytest

from jobomatic.interfaces.cli.main import main


def test_jobo_web_without_flask_says_what_to_install(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Importing the launcher fails as it does when the extra is not installed. Another test may have
    # imported it already, and then `from package import module` finds the attribute, so remove that
    # too (this test once started a real server and hung the whole suite).
    import jobomatic.interfaces.web as web_package

    monkeypatch.setitem(sys.modules, "jobomatic.interfaces.web.launch", None)
    monkeypatch.delattr(web_package, "launch", raising=False)
    assert main(["web"]) == 1
    err = capsys.readouterr().err
    assert "needs Flask" in err and "setup.sh --web" in err and "Traceback" not in err


def test_jobo_web_starts_the_server_on_the_port_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("flask")
    from jobomatic.interfaces.web import launch

    seen: dict[str, object] = {}

    def fake_serve(*, port: int = 0, open_browser: bool = True, **_: object) -> int:
        seen.update(port=port, open_browser=open_browser)
        return 0

    monkeypatch.setattr(launch, "serve", fake_serve)
    assert main(["web", "--port", "8765", "--no-browser"]) == 0
    assert seen == {"port": 8765, "open_browser": False}


def test_jobo_web_opens_a_browser_unless_told_not_to(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("flask")
    from jobomatic.interfaces.web import launch

    seen: dict[str, object] = {}
    monkeypatch.setattr(launch, "serve", lambda **kw: seen.update(kw) or 0)
    assert main(["web"]) == 0
    assert seen == {"port": 0, "open_browser": True}


def test_the_help_lists_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "web" in capsys.readouterr().out
