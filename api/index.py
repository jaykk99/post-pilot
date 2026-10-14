"""Vercel serverless entrypoint for Post Pilot.

Post Pilot is a stdlib http.server app. This module adapts its
BaseHTTPRequestHandler subclass to ASGI so Vercel's Python runtime can
serve it. The vercel.json rewrite sends every path here with the original
path in the __path query param; the wrapper restores it.

Note: SQLite (data/pilot.db) is ephemeral on Vercel's read-only filesystem.
Drafts created here will not survive cold starts. Use the Render deployment
for persistent state.
"""
import io
import os
import sys
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import Handler  # noqa: E402


class _CIHeaders(dict):
    """Case-insensitive header dict (BaseHTTPRequestHandler headers are)."""
    def get(self, key, default=None):
        lk = key.lower()
        for k, v in self.items():
            if k.lower() == lk:
                return v
        return default


class _ASGIHandler(Handler):
    """Handler subclass that bypasses socket __init__ and captures output."""

    def __init__(self, method, path, headers, body):
        # Do NOT call BaseHTTPRequestHandler.__init__ (needs a socket).
        self.command = method
        self.path = path
        self.headers = _CIHeaders(headers)
        self.rfile = io.BytesIO(body)
        self._status = 200
        self._resp_headers = []
        self._wbuf = io.BytesIO()

    @property
    def wfile(self):
        return self._wbuf

    def send_response(self, code, message=None):
        self._status = code

    def send_header(self, key, value):
        self._resp_headers.append((key, value))

    def end_headers(self):
        pass


async def app(scope, receive, send):
    if scope["type"] != "http":
        return

    qs_raw = scope.get("query_string", b"").decode()
    qs = parse_qs(qs_raw, keep_blank_values=True)
    orig = (qs.get("__path") or [None])[0]
    if orig:
        # Rewritten request: restore original path, drop __path param.
        qs.pop("__path", None)
        qs_raw = "&".join("%s=%s" % (k, v) for k, vs in qs.items() for v in vs)
        path = orig
    else:
        # Direct hit (no rewrite): strip the /api/index prefix if present.
        path = scope.get("path", "/")
        if path == "/api/index":
            path = "/"
        elif path.startswith("/api/index/"):
            path = path[len("/api/index"):]
    # Ensure path starts with / for the stdlib handler's urlparse logic.
    if not path.startswith("/"):
        path = "/" + path
    full_path = path + ("?" + qs_raw if qs_raw else "")

    body = b""
    while True:
        msg = await receive()
        if msg["type"] == "http.request":
            body += msg.get("body", b"")
            if not msg.get("more_body"):
                break
        elif msg["type"] == "http.disconnect":
            return

    headers = {}
    for k, v in scope.get("headers", []):
        headers[k.decode("latin1")] = v.decode("latin1")

    method = scope.get("method", "GET").upper()
    h = _ASGIHandler(method, full_path, headers, body)
    # Temporary debug: include path info in 404 responses
    _debug_info = f"path={path!r} full={full_path!r} scope_path={scope.get('path')!r} qs={qs_raw!r}"
    try:
        if method == "GET":
            h.do_GET()
        elif method == "POST":
            h.do_POST()
        else:
            h._send(405, {"error": "method not allowed"})
    except BrokenPipeError:
        pass
    except Exception as e:
        h = _ASGIHandler(method, full_path, headers, body)
        h._send(500, {"error": str(e)[:300]})

    resp_headers = [(k.encode("latin1"), v.encode("latin1"))
                    for k, v in h._resp_headers]
    await send({
        "type": "http.response.start",
        "status": h._status,
        "headers": resp_headers,
    })
    await send({
        "type": "http.response.body",
        "body": h._wbuf.getvalue(),
    })
