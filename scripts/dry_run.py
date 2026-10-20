"""Full dry-run: all 6 businesses through the 6-agent pipeline.

Zero publish calls, zero network (PIL placeholders, curated angles, mocked
subprocess). Proves the pipeline, reviewer gate, store, and dashboard API.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from pilot.businesses import BUSINESSES  # noqa: E402
from pilot.pipeline import Pipeline  # noqa: E402
from pilot.publisher import Publisher  # noqa: E402
from pilot.store import Store  # noqa: E402

# Use today's date: the dashboard API (GET /api/state) only serves drafts for
# the current day, so the smoke test below needs the pipeline run to match.
RUN_DATE = date.today().isoformat()


def main():
    tmp = tempfile.mkdtemp(prefix="postpilot-dryrun-")
    db_path = os.path.join(tmp, "pilot.db")
    media_dir = os.path.join(tmp, "media")
    store = Store(db_path)

    # Hard proof of zero publish calls: any subprocess use explodes.
    real_run = subprocess.run

    def boom(*a, **k):
        raise AssertionError("subprocess called during dry-run: %r" % (a,))

    subprocess.run = boom
    try:
        pipe = Pipeline(store, media_dir, dry_run=True, posts_per_business=2)
        reports = pipe.run_daily(RUN_DATE)

        # Even an explicit publish attempt must not shell out.
        pub = Publisher(dry_run=True)
        sample = store.list_drafts()[0]
        res = pub.publish(sample, "facebook")
        assert res.get("skipped") == "dry-run", res
        assert pub.calls, "publish attempt was not recorded"
    finally:
        subprocess.run = real_run

    # --- report ---
    total_drafts = sum(len(r["drafts"]) for r in reports)
    total_rejected = sum(len(r["rejected"]) for r in reports)
    total_errors = sum(len(r["errors"]) for r in reports)
    print("=" * 64)
    print("POST PILOT DRY-RUN  date=%s" % RUN_DATE)
    print("=" * 64)
    for r in reports:
        print("\n[%s]" % r["business"])
        for d in r["drafts"]:
            from PIL import Image
            with Image.open(d["image"]) as im:
                size = "%dx%d" % im.size
            print("  DRAFT #%d  theme=%r  img=%s  tags=%d  time=%s" % (
                d["id"], d["theme"], size, len(d["hashtags"]), d["post_time"]))
            print("    caption: %s" % d["caption"].split(chr(10))[0][:90])
        for t in r["rejected"]:
            print("  REJECTED theme=%r (reviewer gate)" % t)
        for e in r["errors"]:
            print("  ERROR %s" % e)

    # reviewer gate sanity: feed it garbage, expect rejection
    from pilot.agents import Reviewer
    from pilot.businesses import BY_SLUG
    biz = BY_SLUG["gutter-genie"]
    img = reports[0]["drafts"][0]["image"]
    ok, reasons = Reviewer().review(
        biz, "Best gutters in Winnipeg! Only $99 \u2014 guaranteed #1!",
        ["#a"], "fall leaf clog warning", img)
    assert not ok and reasons, "reviewer failed to reject bad caption"
    print("\nreviewer gate self-test: REJECTED bad caption (%d reasons)" % len(reasons))

    # dashboard API smoke test (real server, temp DB)
    import app as appmod
    appmod.store = store
    appmod.MEDIA_DIR = media_dir
    srv = None
    try:
        from http.server import ThreadingHTTPServer
        srv = ThreadingHTTPServer(("127.0.0.1", 18099), appmod.Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.5)
        with urllib.request.urlopen("http://127.0.0.1:18099/api/state") as r:
            state = json.loads(r.read())
        nbiz = len(state["businesses"])
        ndraft = sum(len(b["drafts"]) for b in state["businesses"])
        assert nbiz == 6 and ndraft == total_drafts
        print("dashboard API: OK  (6 businesses, %d drafts served)" % ndraft)
    finally:
        if srv:
            srv.shutdown()

    print("\n" + "=" * 64)
    print("RESULT: %d drafts, %d rejected by reviewer, %d errors" % (
        total_drafts, total_rejected, total_errors))
    print("publish subprocess calls: 0 (proven by monkeypatch)")
    print("=" * 64)
    store.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if total_errors == 0 and total_drafts > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
