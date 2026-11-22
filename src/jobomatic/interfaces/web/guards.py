"""Who may talk to the local web UI (ADR 0025).

The server listens on loopback only, but any web page open in the same browser can send requests to
``localhost``, and a hostile DNS name can resolve to ``127.0.0.1``. So every request, to every
route, passes one ``before_request`` hook, and no route can skip it:

* the ``Host`` header must be exactly the address and port this server was started on (the
  rebinding allowlist ADR 0004 mentioned);
* the only way in is a launch token that works once: it is exchanged for a session cookie
  (``HttpOnly``, ``SameSite=Strict``, no ``Domain``) and the browser is redirected to the bare
  address, so the token is not left in the history or in a ``Referer``;
* a browser that is already signed in and opens the launch address again is sent on to the bare
  address (the token stays unused, so it is not a second way in);
* every request that is not a ``GET`` or ``HEAD`` also needs an ``Origin`` equal to this server and
  the session's form token.

``add_headers`` puts the same defensive headers on every response, errors included. The pages show a
real profile and real postings, so nothing is cached, nothing is framed, and nothing is fetched or
run from anywhere but this server.
"""

from __future__ import annotations

import hmac
import secrets

from flask import Flask, Response, current_app, redirect, request, session
from werkzeug.exceptions import Forbidden
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
    # Not "no-referrer": the Fetch spec makes a browser send ``Origin: null`` on a same-origin form
    # POST under that policy (Firefox does), and the Origin check below would then refuse every
    # form. "same-origin" sends no Referer to any other site and still sends the real Origin here.
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    # No other page may hold a reference to a window of ours, or embed our files, and the pages ask
    # for no device. Cheap, and they cost nothing here: the pages load only from this server.
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

SAFE_METHODS = ("GET", "HEAD")

# Why a request was refused, in words a person can act on. The key is the reason's name; the error
# page shows the text and the terminal gets the key and a short detail. Nothing here repeats the
# launch token or the form token.
REFUSALS = {
    "host": (
        "Wrong address",
        "This address does not match the one the server is listening on. Open the address that "
        "`jobo web` printed in the terminal (127.0.0.1 or localhost, with the same port).",
    ),
    "no_session": (
        "Not signed in",
        "Your browser has no valid session for this server. That happens when the page was opened "
        "without the launch address, or after `jobo web` was restarted. Open the address printed "
        "in the terminal by `jobo web`; it works once, so start `jobo web` again if you used it.",
    ),
    "token": (
        "Launch address not accepted",
        "That launch address was already used, or it is not the one this server printed. It works "
        "once. Start `jobo web` again for a new one.",
    ),
    "origin": (
        "The browser did not say where the form came from",
        "A form was sent without an Origin header that matches this server, so it was refused as "
        "a precaution. Go back, reload the page and try again. If it keeps happening, note your "
        "browser and its version; the terminal shows what it sent.",
    ),
    "csrf": (
        "This form is out of date",
        "The form's security token is missing or does not match this session, usually because the "
        "page was loaded before `jobo web` was restarted or in another window. Reload the page and "
        "send it again.",
    ),
}


def refuse(reason: str, detail: str = "") -> None:
    """Stop the request with a 403 that says why, and log the reason (never a token) in the terminal."""
    current_app.logger.warning(
        "refused %s %s: %s%s",
        request.method,
        request.path,
        reason,
        f" ({detail})" if detail else "",
    )
    raise Forbidden(description=reason)


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
        refuse("host", f"Host {request.host!r}")
    if request.path == "/" and "token" in request.args and request.method in SAFE_METHODS:
        if session.get("ok"):  # opened twice in the same browser, or the address was reloaded
            return redirect(
                "/"
            )  # already signed in: nothing to exchange, and the token stays unused
        return _exchange_launch_token()
    if not session.get("ok"):
        refuse("no_session")
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("Origin")
        if origin != f"http://{request.host}":
            refuse("origin", f"Origin {origin!r}, expected 'http://{request.host}'")
        sent = request.form.get("csrf") or request.headers.get("X-CSRF-Token") or ""
        if not hmac.compare_digest(sent, str(session.get("csrf", ""))):
            refuse("csrf")
    return None


def _exchange_launch_token() -> BaseResponse:
    """Accept the launch token once; start the session; leave the token out of the address."""
    config = current_app.config
    with config["LAUNCH_LOCK"]:
        offered = request.args.get("token", "")
        if config["LAUNCH_USED"] or not hmac.compare_digest(offered, config["LAUNCH_TOKEN"]):
            refuse("token", "already used" if config["LAUNCH_USED"] else "does not match")
        config["LAUNCH_USED"] = True
    session.clear()
    session["ok"] = True
    session["csrf"] = secrets.token_urlsafe(32)
    return redirect("/")


def add_headers(response: Response) -> Response:
    for name, value in HEADERS.items():
        response.headers[name] = value
    return response
