"""A signed-in test client for the local web UI (ADR 0025), shared by its page tests."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Flask
from flask.testing import FlaskClient

from jobomatic.interfaces.web.app import create_app

BASE = "http://127.0.0.1:5000"
TOKEN = "launch-token"


@dataclass
class Browser:
    """A client that has used the launch token, and knows its form token."""

    app: Flask
    client: FlaskClient

    @property
    def csrf(self) -> str:
        with self.client.session_transaction(base_url=BASE) as session:
            return str(session["csrf"])

    def get(self, path: str, **kw):  # type: ignore[no-untyped-def]
        return self.client.get(path, base_url=BASE, **kw)

    def post(self, path: str, data: dict | None = None, **kw):  # type: ignore[no-untyped-def]
        """A form post the way a browser makes it: its own origin and the form token."""
        fields = {"csrf": self.csrf, **(data or {})}
        headers = {"Origin": BASE, **kw.pop("headers", {})}
        return self.client.post(path, data=fields, headers=headers, base_url=BASE, **kw)


def signed_in() -> Browser:
    app = create_app(launch_token=TOKEN)
    app.config["ALLOWED_HOSTS"] = frozenset({"127.0.0.1:5000"})
    client = app.test_client()
    assert client.get(f"/?token={TOKEN}", base_url=BASE).status_code == 302
    return Browser(app, client)
