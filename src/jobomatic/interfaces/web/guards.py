"""Who may talk to the local web UI (ADR 0025).

The server listens on loopback only, but any web page open in the same browser can send requests to
``localhost``, and a hostile DNS name can resolve to ``127.0.0.1``. So every request, to every
route, passes one ``before_request`` hook, and no route can skip it:

* the ``Host`` header must be exactly the address and port this server was started on (the
  rebinding allowlist ADR 0004 mentioned);
* the only way in is a launch token that works once: it is exchanged for a session cookie
  (``HttpOnly``, ``SameSite=Strict``, no ``Domain``) and the browser is redirected to the bare
  address, so the token is not left in the history or in a ``Referer``;
* every request that is not a ``GET`` or ``HEAD`` also needs an ``Origin`` equal to this server and
  the session's form token.

``add_headers`` puts the same defensive headers on every response, errors included. The pages show a
real profile and real postings, so nothing is cached, nothing is framed, and nothing is fetched or
run from anywhere but this server.
"""

from __future__ import annotations

import hmac
import secrets

from flask import Flask, Response, abort, current_app, redirect, request, session
from werkzeug.wrappers import Response as BaseResponse

# default-src 'self': nothing is fetched from another origin. No inline script or style is allowed,
# and no page may be framed (clickjacking on the Apply button). form-action and base-uri stop a
# injected form or <base> from pointing the page somewhere else.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "base-uri 'none'",
    ]
)

HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
}

SAFE_METHODS = ("GET", "HEAD")


def install(app: Flask) -> None:
    """Attach the two hooks. Called once, by ``create_app``."""
    app.config.update(
        SESSION_COOKIE_NAME="jobo_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_DOMAIN=None,
        SESSION_COOKIE_SECURE=False,  # plain http on loopback
    )
    app.before_request(check_request)
    app.after_request(add_headers)


def check_request() -> BaseResponse | None:
    if request.host not in current_app.config["ALLOWED_HOSTS"]:
        abort(403)
    if request.path == "/" and "token" in request.args and request.method in SAFE_METHODS:
        return _exchange_launch_token()
    if not session.get("ok"):
        abort(403)
    if request.method not in SAFE_METHODS:
        if request.headers.get("Origin") != f"http://{request.host}":
            abort(403)
        sent = request.form.get("csrf") or request.headers.get("X-CSRF-Token") or ""
        if not hmac.compare_digest(sent, str(session.get("csrf", ""))):
            abort(403)
    return None


def _exchange_launch_token() -> BaseResponse:
    """Accept the launch token once; start the session; leave the token out of the address."""
    config = current_app.config
    with config["LAUNCH_LOCK"]:
        offered = request.args.get("token", "")
        if config["LAUNCH_USED"] or not hmac.compare_digest(offered, config["LAUNCH_TOKEN"]):
            abort(403)
        config["LAUNCH_USED"] = True
    session.clear()
    session["ok"] = True
    session["csrf"] = secrets.token_urlsafe(32)
    return redirect("/")


def add_headers(response: Response) -> Response:
    for name, value in HEADERS.items():
        response.headers[name] = value
    return response
