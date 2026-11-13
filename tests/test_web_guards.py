"""The guards of the local web UI (ADR 0025): who may talk to it, and what every response says.

Most tests use Flask's test client. A few use a real server on a real socket, because the bind
address, the port read back and the ``Host`` header are exactly what a test client does not prove.
"""

from __future__ import annotations

import http.client
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("flask")

from flask import Flask  # noqa: E402

from jobomatic.interfaces.web import guards  # noqa: E402
from jobomatic.interfaces.web.app import MAX_REQUEST_BYTES, create_app  # noqa: E402
from jobomatic.interfaces.web.launch import QuietHandler, build_server  # noqa: E402

BASE = "http://127.0.0.1:5000"
TOKEN = "launch-token"


@pytest.fixture
def app() -> Flask:
    app = create_app(launch_token=TOKEN)
    app.config["ALLOWED_HOSTS"] = frozenset({"127.0.0.1:5000", "localhost:5000"})

    @app.post("/__echo")
    def echo() -> str:  # a route that changes something, to test the POST guards
        return "done"

    @app.get("/__boom")
    def boom() -> str:
        raise RuntimeError("secret detail that must not reach the page")

    return app


@pytest.fixture
def client(app: Flask):  # type: ignore[no-untyped-def]
    return app.test_client()


@pytest.fixture
def signed_in(client):  # type: ignore[no-untyped-def]
    assert client.get(f"/?token={TOKEN}", base_url=BASE).status_code == 302
    return client


def _csrf(client) -> str:  # type: ignore[no-untyped-def]
    with client.session_transaction(base_url=BASE) as session:
        return str(session["csrf"])


# -- the launch token and the session ----------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/brand/tokens.css", "/static/app.css", "/download/x"])
def test_nothing_is_served_without_the_session(client, path: str) -> None:  # type: ignore[no-untyped-def]
    assert client.get(path, base_url=BASE).status_code == 403


def test_the_launch_token_starts_a_session_and_leaves_the_address(client) -> None:  # type: ignore[no-untyped-def]
    reply = client.get(f"/?token={TOKEN}", base_url=BASE)
    assert reply.status_code == 302
    assert reply.headers["Location"] == "/"  # the token is not left in the history
    cookie = reply.headers["Set-Cookie"]
    assert cookie.startswith("jobo_session=")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert "Domain" not in cookie
    assert client.get("/", base_url=BASE).status_code == 200


def test_the_launch_token_works_once(app: Flask) -> None:
    first, second = app.test_client(), app.test_client()
    assert first.get(f"/?token={TOKEN}", base_url=BASE).status_code == 302
    assert second.get(f"/?token={TOKEN}", base_url=BASE).status_code == 403
    assert second.get("/", base_url=BASE).status_code == 403


def test_a_wrong_token_is_refused_and_does_not_use_up_the_right_one(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/?token=nope", base_url=BASE).status_code == 403
    assert client.get(f"/?token={TOKEN}", base_url=BASE).status_code == 302


def test_the_token_is_accepted_only_at_the_front_door(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get(f"/brand/tokens.css?token={TOKEN}", base_url=BASE).status_code == 403
    assert client.get(f"/?token={TOKEN}", base_url=BASE).status_code == 302


def test_a_post_cannot_use_the_token(client) -> None:  # type: ignore[no-untyped-def]
    assert client.post(f"/?token={TOKEN}", base_url=BASE).status_code == 403
    assert client.get(f"/?token={TOKEN}", base_url=BASE).status_code == 302


# -- the Host header (DNS rebinding) -----------------------------------------------------------


@pytest.mark.parametrize(
    "host", ["evil.test:5000", "127.0.0.1", "127.0.0.1:5001", "127.0.0.1.evil.test:5000", ""]
)
def test_a_foreign_host_is_refused_even_with_a_session(signed_in, host: str) -> None:  # type: ignore[no-untyped-def]
    assert signed_in.get("/", headers={"Host": host}, base_url=BASE).status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1:5000", "localhost:5000"])
def test_the_two_names_of_this_server_are_accepted(app: Flask, host: str) -> None:
    base = f"http://{host}"
    client = app.test_client()
    assert client.get(f"/?token={TOKEN}", base_url=base).status_code == 302
    assert client.get("/", base_url=base).status_code == 200


# -- changes need the right origin and the form token ------------------------------------------


def _post(client, **overrides):  # type: ignore[no-untyped-def]
    headers = {"Origin": BASE}
    headers.update(overrides.pop("headers", {}))
    data = {"csrf": _csrf(client)}
    data.update(overrides.pop("data", {}))
    return client.post("/__echo", data=data, headers=headers, base_url=BASE)


def test_a_post_with_the_right_origin_and_token_goes_through(signed_in) -> None:  # type: ignore[no-untyped-def]
    assert _post(signed_in).status_code == 200


def test_a_post_with_no_origin_is_refused(signed_in) -> None:  # type: ignore[no-untyped-def]
    reply = signed_in.post("/__echo", data={"csrf": _csrf(signed_in)}, base_url=BASE)
    assert reply.status_code == 403


@pytest.mark.parametrize(
    "origin", ["http://evil.test", "http://127.0.0.1:5001", "null", "https://127.0.0.1:5000"]
)
def test_a_post_from_another_origin_is_refused(signed_in, origin: str) -> None:  # type: ignore[no-untyped-def]
    assert _post(signed_in, headers={"Origin": origin}).status_code == 403


def test_a_post_with_no_or_a_wrong_form_token_is_refused(signed_in) -> None:  # type: ignore[no-untyped-def]
    assert _post(signed_in, data={"csrf": ""}).status_code == 403
    assert _post(signed_in, data={"csrf": "guess"}).status_code == 403
    no_field = signed_in.post("/__echo", headers={"Origin": BASE}, base_url=BASE)
    assert no_field.status_code == 403


def test_the_form_token_may_come_in_a_header_for_partial_updates(signed_in) -> None:  # type: ignore[no-untyped-def]
    reply = signed_in.post(
        "/__echo", headers={"Origin": BASE, "X-CSRF-Token": _csrf(signed_in)}, base_url=BASE
    )
    assert reply.status_code == 200


def test_a_post_without_a_session_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    reply = client.post("/__echo", data={"csrf": "x"}, headers={"Origin": BASE}, base_url=BASE)
    assert reply.status_code == 403


def test_a_cross_origin_preflight_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    reply = client.options("/__echo", headers={"Origin": "http://evil.test"}, base_url=BASE)
    assert reply.status_code == 403


# -- every response ----------------------------------------------------------------------------


def test_every_response_carries_the_defensive_headers(signed_in) -> None:  # type: ignore[no-untyped-def]
    replies = [
        signed_in.get("/", base_url=BASE),  # 200
        signed_in.get("/nothing-here", base_url=BASE),  # 404
        signed_in.get("/", headers={"Host": "evil.test"}, base_url=BASE),  # 403
        signed_in.get("/brand/tokens.css", base_url=BASE),  # a file
        signed_in.get("/?token=zzz", base_url=BASE),  # a refused token
    ]
    for reply in replies:
        for name, value in guards.HEADERS.items():
            assert reply.headers[name] == value, (reply.status_code, name)


def test_the_policy_forbids_framing_other_origins_and_inline_code() -> None:
    policy = guards.CONTENT_SECURITY_POLICY
    for part in (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "base-uri 'none'",
    ):
        assert part in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy and "*" not in policy
    assert guards.HEADERS["Cache-Control"] == "no-store"


def test_no_cross_origin_sharing_header_is_ever_sent(signed_in) -> None:  # type: ignore[no-untyped-def]
    reply = signed_in.get("/", headers={"Origin": "http://evil.test"}, base_url=BASE)
    assert not [h for h in reply.headers.keys() if h.lower().startswith("access-control-")]


def test_the_debugger_is_off_and_an_error_shows_no_detail(signed_in, app: Flask) -> None:  # type: ignore[no-untyped-def]
    assert app.debug is False
    reply = signed_in.get("/__boom", base_url=BASE)
    body = reply.get_data(as_text=True)
    assert reply.status_code == 500
    assert "secret detail" not in body and "Traceback" not in body
    assert "Something went wrong" in body


def test_a_request_over_the_limit_is_refused_with_a_page(signed_in) -> None:  # type: ignore[no-untyped-def]
    big = "x" * (MAX_REQUEST_BYTES + 10)
    reply = signed_in.post(
        "/__echo",
        data={"csrf": _csrf(signed_in), "text": big},
        headers={"Origin": BASE},
        base_url=BASE,
    )
    assert reply.status_code == 413
    assert "Too large" in reply.get_data(as_text=True)


def test_the_browsers_own_favicon_request_is_answered_after_sign_in(app: Flask, signed_in) -> None:  # type: ignore[no-untyped-def]
    assert signed_in.get("/favicon.ico", base_url=BASE).status_code == 200
    assert app.test_client().get("/favicon.ico", base_url=BASE).status_code == 403


def test_only_the_named_branding_files_can_be_fetched(signed_in) -> None:  # type: ignore[no-untyped-def]
    assert signed_in.get("/brand/tokens.css", base_url=BASE).status_code == 200
    assert signed_in.get("/brand/job-o-matic-icon.svg", base_url=BASE).status_code == 200
    for name in (
        "../paths.py",
        "tokens.css/..",
        "job-o-matic-logo.png",
        "README.md",
        "..%2fpaths.py",
    ):
        assert signed_in.get(f"/brand/{name}", base_url=BASE).status_code == 404, name


# -- downloads: by an id the server issued, never by a name ------------------------------------


def test_a_download_is_served_by_its_issued_id(signed_in, app: Flask, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    document = tmp_path / "resume.docx"
    document.write_bytes(b"document bytes")
    download_id = app.extensions["downloads"].issue(document)
    reply = signed_in.get(f"/download/{download_id}", base_url=BASE)
    assert reply.status_code == 200 and reply.data == b"document bytes"
    assert "attachment" in reply.headers["Content-Disposition"]


def test_a_download_cannot_name_a_path(signed_in, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    secret = tmp_path / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    for attempt in (str(secret), "../../etc/passwd", "%2e%2e/%2e%2e/etc/passwd", "unknown-id"):
        assert signed_in.get(f"/download/{attempt}", base_url=BASE).status_code == 404, attempt


def test_a_file_that_is_gone_is_not_served(signed_in, app: Flask, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    document = tmp_path / "gone.docx"
    document.write_bytes(b"x")
    download_id = app.extensions["downloads"].issue(document)
    document.unlink()
    assert signed_in.get(f"/download/{download_id}", base_url=BASE).status_code == 404


# -- a real server on a real socket ------------------------------------------------------------


@pytest.fixture
def live() -> Iterator[tuple[int, str]]:
    server, url = build_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(port: int, path: str, headers: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", path, headers=headers or {})
    reply = connection.getresponse()
    body = reply.read()
    connection.close()
    return reply, body


def test_the_server_listens_on_loopback_only() -> None:
    server, _ = build_server(0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_port > 0  # the system chose one, and it is read back
    finally:
        server.server_close()


def test_the_launch_address_names_the_port_the_server_really_has(live) -> None:  # type: ignore[no-untyped-def]
    port, url = live
    assert url.startswith(f"http://127.0.0.1:{port}/?token=")


def test_a_real_request_needs_the_token_and_then_the_cookie(live) -> None:  # type: ignore[no-untyped-def]
    port, url = live
    path = url.split(f":{port}", 1)[1]
    assert _get(port, "/")[0].status == 403
    reply, _ = _get(port, path)
    assert reply.status == 302 and reply.getheader("Location") == "/"
    cookie = reply.getheader("Set-Cookie", "").split(";")[0]
    assert _get(port, "/", {"Cookie": cookie})[0].status == 200
    assert _get(port, path)[0].status == 403  # the token was used


def test_a_real_request_with_a_foreign_host_is_refused(live) -> None:  # type: ignore[no-untyped-def]
    port, url = live
    path = url.split(f":{port}", 1)[1]
    reply, _ = _get(port, path, {"Host": f"evil.test:{port}"})
    assert reply.status == 403
    assert _get(port, path)[0].status == 302  # the refused request did not use the token up


def test_the_request_log_never_holds_the_launch_token(live, caplog) -> None:  # type: ignore[no-untyped-def]
    port, url = live
    token = url.split("token=")[1]
    with caplog.at_level("INFO", logger="werkzeug"):
        _get(port, url.split(f":{port}", 1)[1])
    assert token not in caplog.text
    assert '"GET /" 302' in caplog.text


def test_the_quiet_handler_is_what_the_server_uses() -> None:
    server, _ = build_server(0)
    try:
        assert server.RequestHandlerClass is QuietHandler
    finally:
        server.server_close()
