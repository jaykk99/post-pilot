"""Post Pilot dashboard server. Stdlib only (http.server + sqlite3).

Serves the mobile-friendly approval dashboard and a JSON API.
Nothing auto-publishes: drafts sit in status=draft until Jay approves,
then a publish call goes out per approved draft per target.

Optional access gate: set POST_PILOT_CODE env var. The dashboard prompts
once and keeps it in localStorage.
"""

import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pilot.businesses import BUSINESSES, BY_SLUG
from pilot.pipeline import Pipeline
from pilot.publisher import Publisher, PublishSkipped
from pilot.store import Store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
DB_PATH = os.path.join(DATA_DIR, "pilot.db")
POST_LOG = os.path.expanduser("~/workspace/advertising/post-log.md")

store = Store(DB_PATH)
publisher = Publisher(dry_run=False)
ACCESS_CODE = os.environ.get("POST_PILOT_CODE", "")
_run_lock = threading.Lock()


def _today():
    import datetime
    return datetime.date.today().isoformat()


def _check_auth(handler):
    if not ACCESS_CODE:
        return True
    q = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    if q.get("code", [""])[0] == ACCESS_CODE:
        return True
    if handler.headers.get("X-Access-Code") == ACCESS_CODE:
        return True
    return False


def _draft_json(d):
    import json as _j
    d = dict(d)
    d["hashtags"] = _j.loads(d["hashtags"])
    d["image_url"] = "/media/" + os.path.basename(d["image_path"] or "") \
        if d.get("image_path") else None
    return d


def api_state():
    today = _today()
    bizs = []
    for b in BUSINESSES:
        drafts = [_draft_json(d) for d in store.list_drafts(run_date=today,
                                                             business=b["slug"])]
        targets = []
        if b["targets"]["facebook"]:
            targets.append({"platform": "facebook", "id": b["targets"]["facebook"]})
        else:
            targets.append({"platform": "facebook", "id": None,
                            "note": "no page connected"})
        if b["targets"]["instagram"]:
            targets.append({"platform": "instagram", "id": b["targets"]["instagram"]})
        else:
            targets.append({"platform": "instagram", "id": None,
                            "note": "no account connected"})
        bizs.append({"slug": b["slug"], "name": b["name"],
                     "tagline": b["tagline"], "targets": targets,
                     "drafts": drafts,
                     "metrics": store.latest_metrics(b["slug"])[:4]})
    return {"date": today, "businesses": bizs,
            "auth_required": bool(ACCESS_CODE)}


def append_post_log(line):
    try:
        with open(POST_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "PostPilot/1.0"

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/":
            return self._serve_file("static/index.html", "text/html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path.startswith("/media/"):
            name = os.path.basename(path)
            if ".." in name:
                return self._send(400, {"error": "bad path"})
            return self._serve_file(os.path.join("data", "media", name),
                                    "image/png")
        if path == "/api/state":
            if not _check_auth(self):
                return self._send(401, {"error": "access code required"})
            return self._send(200, api_state())
        return self._send(404, {"error": "not found"})

    def _serve_file(self, rel, ctype):
        full = os.path.join(BASE_DIR, rel)
        if not os.path.isfile(full):
            return self._send(404, {"error": "not found"})
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, name):
        if ".." in name or name.startswith("/"):
            return self._send(400, {"error": "bad path"})
        ctype = "text/plain"
        if name.endswith(".html"):
            ctype = "text/html"
        elif name.endswith(".js"):
            ctype = "application/javascript"
        elif name.endswith(".css"):
            ctype = "text/css"
        return self._serve_file(os.path.join("static", name), ctype)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/") and not _check_auth(self):
            return self._send(401, {"error": "access code required"})
        body = self._body()

        if path == "/api/run":
            if not _run_lock.acquire(blocking=False):
                return self._send(409, {"error": "a run is already in progress"})
            try:
                pipe = Pipeline(store, MEDIA_DIR, dry_run=False)
                reports = pipe.run_daily(_today())
                return self._send(200, {"ok": True, "reports": reports})
            finally:
                _run_lock.release()

        if path == "/api/analyze":
            pipe = Pipeline(store, MEDIA_DIR, dry_run=False)
            return self._send(200, {"ok": True,
                                    "results": pipe.run_analyst()})

        m = None
        import re
        m = re.match(r"^/api/drafts/(\d+)/(approve|reject)$", path)
        if m:
            draft_id, action = int(m.group(1)), m.group(2)
            d = store.get_draft(draft_id)
            if not d:
                return self._send(404, {"error": "no such draft"})
            store.set_status(draft_id, "approved" if action == "approve" else "rejected")
            return self._send(200, {"ok": True, "status": action + "d"})

        m = re.match(r"^/api/drafts/(\d+)/edit$", path)
        if m:
            draft_id = int(m.group(1))
            d = store.get_draft(draft_id)
            if not d:
                return self._send(404, {"error": "no such draft"})
            from pilot.agents import Copywriter, Reviewer
            caption = Copywriter.sanitize(body.get("caption", ""))
            biz = BY_SLUG[d["business"]]
            import json as _j
            ok, reasons = Reviewer().review(biz, caption, _j.loads(d["hashtags"]),
                                            d["angle_theme"], d["image_path"])
            store.update_caption(draft_id, caption)
            store.set_status(draft_id, "draft",
                             "edited by Jay; review: " + ("pass" if ok else "; ".join(reasons)))
            return self._send(200, {"ok": True, "review_pass": ok,
                                    "reasons": reasons})

        m = re.match(r"^/api/publish/(\d+)$", path)
        if m:
            draft_id = int(m.group(1))
            d = store.get_draft(draft_id)
            if not d:
                return self._send(404, {"error": "no such draft"})
            if d["status"] != "approved":
                return self._send(409, {"error": "draft must be approved first"})
            platform = body.get("platform", "facebook")
            try:
                result = publisher.publish(d, platform)
            except PublishSkipped as e:
                return self._send(200, {"ok": False, "skipped": str(e)})
            except Exception as e:
                return self._send(500, {"error": str(e)[:300]})
            if result.get("ok"):
                store.record_publish(draft_id, result.get("target", ""),
                                     platform, result.get("post_id"),
                                     result.get("url"))
                store.set_status(draft_id, "published")
                append_post_log(
                    "- %s | business: %s | %s: %s via post-pilot | theme: %s | "
                    "image: %s | result: PUBLISHED - %s" % (
                        d["run_date"], d["business"], platform,
                        result.get("target", ""), d["angle_theme"],
                        os.path.basename(d["image_path"] or ""),
                        result.get("post_id", "")))
            return self._send(200, result)

        return self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):  # quieter logs
        pass


def main():
    port = int(os.environ.get("PORT", "8099"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("Post Pilot on http://localhost:%d (auth %s)" %
          (port, "ON" if ACCESS_CODE else "off"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
