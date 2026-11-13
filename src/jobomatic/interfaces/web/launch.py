"""Start the local web UI: loopback only, in the foreground, stopped with Ctrl+C (ADR 0025)."""

from __future__ import annotations

import secrets
import sys
import webbrowser
from typing import Any, TextIO

from werkzeug.serving import BaseWSGIServer, WSGIRequestHandler, make_server

from jobomatic.interfaces.web.app import create_app

HOST = "127.0.0.1"


class QuietHandler(WSGIRequestHandler):
    """Logs the method and path of a request, never its query: the launch token is in one."""

    def log_request(self, code: Any = "-", size: Any = "-") -> None:
        self.log("info", '"%s %s" %s', self.command, self.path.split("?")[0], code)


def build_server(port: int = 0) -> tuple[BaseWSGIServer, str]:
    """A server bound to ``127.0.0.1`` (port 0 lets the system choose), and the one-use address.

    The debugger and the reloader are never enabled: the debugger runs code.
    """
    token = secrets.token_urlsafe(32)
    app = create_app(launch_token=token)
    server = make_server(HOST, port, app, threaded=True, request_handler=QuietHandler)
    real_port = server.server_port
    app.config["ALLOWED_HOSTS"] = frozenset({f"127.0.0.1:{real_port}", f"localhost:{real_port}"})
    return server, f"http://127.0.0.1:{real_port}/?token={token}"


def serve(*, port: int = 0, open_browser: bool = True, out: TextIO = sys.stdout) -> int:
    server, url = build_server(port)
    print("job-o-matic web UI. Press Ctrl+C to stop it.", file=out, flush=True)
    print(f"Open this address (it works once): {url}", file=out, flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
