"""Post Pilot test suite. Stdlib unittest; no network, no publishing.

Run:  python3 -m unittest discover -s tests -v
Or:   python3 tests/test_pilot.py
"""

import datetime
import json
import os
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from pilot import formats as formats_mod  # noqa: E402
from pilot import media_gen  # noqa: E402
from pilot.agents import (Copywriter, Designer, HashtagSEO, Reviewer,  # noqa: E402
                          TrendScout)
from pilot.businesses import BUSINESSES, BY_SLUG, POST_TIMES  # noqa: E402
from pilot.publisher import Publisher  # noqa: E402
from pilot.store import Store  # noqa: E402

GG = BY_SLUG["gutter-genie"]
TODAY = "2026-10-20"


def make_store():
    tmp = tempfile.mkdtemp(prefix="pp-test-")
    return Store(os.path.join(tmp, "t.db")), tmp


def good_caption(biz=GG):
    return "Leaves are filling gutters right now.\n\nClogged gutters before " \
        "freeze-up means ice and water damage. A cleaning now saves a " \
        "repair later.\n\nCall or text 204-972-0325 for a free, no-pressure quote."


class TestReviewer(unittest.TestCase):
    def setUp(self):
        self.store, self.tmp = make_store()
        self.img = os.path.join(self.tmp, "img.png")
        media_gen._placeholder(GG, "hook", self.img)

    def tearDown(self):
        self.store.close()

    def review(self, caption, tags=None, theme="fall leaf clog warning",
               fmt=None):
        return Reviewer().review(
            GG, caption, tags or ["#GutterGenie", "#Winnipeg", "#Gutters"],
            theme, self.img, fmt=fmt, store=self.store, run_date=TODAY)

    def test_clean_caption_passes(self):
        ok, reasons = self.review(good_caption())
        self.assertTrue(ok, reasons)

    def test_em_dash_rejected(self):
        ok, reasons = self.review("Gutters \u2014 the silent killer.")
        self.assertFalse(ok)
        self.assertTrue(any("dash" in r for r in reasons))

    def test_price_rejected(self):
        ok, reasons = self.review("Cleaning for only $99 today.")
        self.assertFalse(ok)
        self.assertTrue(any("price" in r for r in reasons))

    def test_superlative_rejected(self):
        for bad in ("Best gutters in Winnipeg!", "We are #1",
                    "Guaranteed results", "5-star service"):
            ok, reasons = self.review(bad + " Call 204-972-0325.")
            self.assertFalse(ok, bad)
            self.assertTrue(any("superlative" in r for r in reasons), bad)

    def test_hashtag_count_bounds(self):
        ok, _ = self.review(good_caption(), tags=["#a", "#b"])
        self.assertFalse(ok)
        ok, _ = self.review(good_caption(),
                            tags=["#%d" % i for i in range(7)])
        self.assertFalse(ok)
        ok, reasons = self.review(good_caption(),
                                  tags=["#%d" % i for i in range(5)])
        self.assertTrue(ok, reasons)

    def test_unapproved_url_rejected(self):
        ok, reasons = self.review("See https://evil.example.com for deals.")
        self.assertFalse(ok)
        self.assertTrue(any("unapproved URL" in r for r in reasons))

    def test_allowed_url_passes(self):
        ok, reasons = self.review(
            "See https://gutter-genie.vercel.app/ for our work. " +
            good_caption())
        self.assertTrue(ok, reasons)

    def test_subdomain_of_allowed_passes(self):
        ok, reasons = self.review(
            "See https://www.gutter-genie.vercel.app/ today. " + good_caption())
        self.assertTrue(ok, reasons)

    def test_duplicate_theme_rejected(self):
        # Fake a recent post in the log by pointing the reviewer at a stub.
        log = os.path.join(self.tmp, "post-log.md")
        with open(log, "w") as f:
            f.write("- 2026-10-19 | business: gutter-genie | facebook: x via "
                    "post-pilot | theme: fall leaf clog warning | result: PUBLISHED\n")
        r = Reviewer(post_log_path=log)
        ok, reasons = r.review(GG, good_caption(),
                               ["#GutterGenie", "#Winnipeg", "#Gutters"],
                               "fall leaf clog warning", self.img)
        self.assertFalse(ok)
        self.assertTrue(any("too close to recent" in x for x in reasons))

    def test_wrong_image_dims_rejected(self):
        from PIL import Image
        bad = os.path.join(self.tmp, "bad.png")
        Image.new("RGB", (100, 100)).save(bad)
        ok, reasons = Reviewer().review(
            GG, good_caption(), ["#a", "#b", "#c"], "some theme", bad)
        self.assertFalse(ok)
        self.assertTrue(any("1080x1350" in r for r in reasons))

    def test_caption_length_cap(self):
        ok, reasons = self.review("x" * 2201)
        self.assertFalse(ok)
        self.assertTrue(any("2200" in r for r in reasons))

    def test_format_rotation_violation_rejected(self):
        self.store.save_draft(
            "gutter-genie", "2026-10-19", "t", "c", "[]", "09:00",
            None, None, None, format="tip-card")
        ok, reasons = self.review(good_caption(), fmt="tip-card")
        self.assertFalse(ok)
        self.assertTrue(any("rotation" in r for r in reasons))

    def test_format_rotation_clean_passes(self):
        self.store.save_draft(
            "gutter-genie", "2026-10-19", "t", "c", "[]", "09:00",
            None, None, None, format="tip-card")
        ok, reasons = self.review(good_caption(), fmt="photo-story")
        self.assertTrue(ok, reasons)


class TestCopywriter(unittest.TestCase):
    def test_sanitize_removes_em_dashes(self):
        out = Copywriter.sanitize("a \u2014 b \u2013 c \u2011 d")
        self.assertNotIn("\u2014", out)
        self.assertNotIn("\u2013", out)
        self.assertNotIn("\u2011", out)

    def test_sanitize_collapses_whitespace(self):
        out = Copywriter.sanitize("a   b\n\n\n\nc")
        self.assertNotIn("   ", out)
        self.assertNotIn("\n\n\n", out)

    def test_write_structure(self):
        angle = {"theme": "t", "hook": "Leaves are filling gutters",
                 "body": "Clean them now."}
        cap = Copywriter().write(GG, angle, seed=0)
        self.assertIn("Leaves are filling gutters.", cap)
        self.assertIn("Clean them now.", cap)
        self.assertIn(GG["cta"], cap)
        self.assertNotIn("\u2014", cap)

    def test_revise_strips_prices_and_hype(self):
        angle = {"theme": "t", "hook": "h", "body": "Only $99, guaranteed #1!"}
        out = Copywriter().revise(GG, angle, "x", ["price"], seed=1)
        self.assertNotIn("$99", out)
        self.assertNotIn("guaranteed", out)
        self.assertNotIn("#1", out)

    def test_revise_strips_urls(self):
        angle = {"theme": "t", "hook": "h",
                 "body": "See https://evil.example.com now"}
        out = Copywriter().revise(GG, angle, "x", ["url"], seed=1)
        self.assertNotIn("evil.example.com", out)


class TestScout(unittest.TestCase):
    def test_deterministic_picks(self):
        store, _ = make_store()
        s = TrendScout(dry_run=True)
        a1 = s.scout(GG, TODAY, {}, n=4, store=store)
        a2 = s.scout(GG, TODAY, {}, n=4, store=store)
        self.assertEqual([a["theme"] for a in a1],
                         [a["theme"] for a in a2])
        store.close()

    def test_no_duplicate_themes(self):
        store, _ = make_store()
        angles = TrendScout(dry_run=True).scout(GG, TODAY, {}, n=6,
                                               store=store)
        themes = [a["theme"] for a in angles]
        self.assertEqual(len(themes), len(set(themes)))
        store.close()

    def test_winners_bias_first(self):
        store, _ = make_store()
        s = TrendScout(dry_run=True)
        learn = {"winning_themes": ["ice dam prevention"]}
        angles = s.scout(GG, TODAY, learn, n=4, store=store)
        self.assertEqual(angles[0]["theme"], "ice dam prevention")
        store.close()

    def test_formats_assigned_and_valid(self):
        store, _ = make_store()
        angles = TrendScout(dry_run=True).scout(GG, TODAY, {}, n=4,
                                               store=store)
        fmts = [a["format"] for a in angles]
        self.assertTrue(all(f in formats_mod.FORMAT_BY_NAME for f in fmts),
                        fmts)
        self.assertEqual(len(set(fmts)), len(fmts))  # no dup in one day
        store.close()

    def test_without_store_no_format_key(self):
        angles = TrendScout(dry_run=True).scout(GG, TODAY, {}, n=2)
        self.assertEqual(len(angles), 2)
        self.assertTrue(all("format" not in a for a in angles))


class TestHashtagSEO(unittest.TestCase):
    def test_brand_tag_first_and_count(self):
        tags, _ = HashtagSEO().pick(GG, {"theme": "t"}, TODAY, 0)
        self.assertEqual(tags[0], GG["hashtags"][0])
        self.assertTrue(3 <= len(tags) <= 6)

    def test_deterministic(self):
        a = HashtagSEO().pick(GG, {"theme": "t"}, TODAY, 2)
        b = HashtagSEO().pick(GG, {"theme": "t"}, TODAY, 2)
        self.assertEqual(a, b)

    def test_post_time_valid(self):
        for biz in BUSINESSES:
            _, t = HashtagSEO().pick(biz, {"theme": "t"}, TODAY, 0)
            self.assertIn(t, POST_TIMES)


class TestFormats(unittest.TestCase):
    def test_catalog_unique(self):
        names = [f["name"] for f in formats_mod.FORMATS]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("template-reel", formats_mod.WEEKLY_CAPS)

    def test_assign_deterministic(self):
        store, _ = make_store()
        a = formats_mod.assign_formats(store, "move-metal", TODAY, 4)
        b = formats_mod.assign_formats(store, "move-metal", TODAY, 4)
        self.assertEqual(a, b)
        store.close()

    def test_no_repeat_yesterday(self):
        store, _ = make_store()
        store.save_draft("demoboss", "2026-10-19", "t", "c", "[]", "09:00",
                         None, None, None, format="how-it-works")
        elig = formats_mod.eligible_formats(store, "demoboss", TODAY)
        self.assertNotIn("how-it-works", elig)
        store.close()

    def test_weekly_cap(self):
        store, _ = make_store()
        for d in range(1, 4):
            day = (datetime.date(2026, 10, 20) -
                   datetime.timedelta(days=d)).isoformat()
            store.save_draft("bnb-media", day, "t", "c", "[]", "09:00",
                             None, None, None, format="template-reel")
        # 1x/week cap: even one prior use in the window blocks it.
        elig = formats_mod.eligible_formats(store, "bnb-media", TODAY)
        self.assertNotIn("template-reel", elig)
        store.close()

    def test_check_rotation_reports_all_violations(self):
        store, _ = make_store()
        day = (datetime.date(2026, 10, 20) -
               datetime.timedelta(days=1)).isoformat()
        store.save_draft("quonset-place", day, "t", "c", "[]", "09:00",
                         None, None, None, format="offer-card")
        v = formats_mod.check_rotation(store, "quonset-place", TODAY,
                                       "offer-card")
        self.assertTrue(any("yesterday" in x for x in v))
        v2 = formats_mod.check_rotation(store, "quonset-place", TODAY,
                                        "tip-card")
        self.assertEqual(v2, [])
        store.close()

    def test_fallback_when_everything_excluded(self):
        # Degenerate: pool must never come back empty.
        store, _ = make_store()
        elig = formats_mod.eligible_formats(store, "gutter-genie", TODAY)
        self.assertTrue(elig)
        store.close()


class TestStore(unittest.TestCase):
    def test_roundtrip(self):
        store, _ = make_store()
        did = store.save_draft("gutter-genie", TODAY, "theme", "cap",
                               ["#a"], "09:00", "/img.png", "fb", "ig",
                               format="tip-card")
        d = store.get_draft(did)
        self.assertEqual(d["caption"], "cap")
        self.assertEqual(d["format"], "tip-card")
        self.assertEqual(json.loads(d["hashtags"]), ["#a"])
        self.assertEqual(d["status"], "draft")
        store.set_status(did, "approved")
        self.assertEqual(store.get_draft(did)["status"], "approved")
        store.update_caption(did, "new cap")
        self.assertEqual(store.get_draft(did)["caption"], "new cap")
        rows = store.list_drafts(run_date=TODAY, business="gutter-genie",
                                 status="approved")
        self.assertEqual(len(rows), 1)
        store.close()

    def test_migration_adds_format_column(self):
        # Simulate a pre-format DB: create table without the column, then
        # let Store migrate it.
        import sqlite3
        tmp = tempfile.mkdtemp(prefix="pp-mig-")
        path = os.path.join(tmp, "old.db")
        conn = sqlite3.connect(path)
        # Real old schema: everything except the format column.
        conn.execute("""CREATE TABLE drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, business TEXT NOT NULL,
            run_date TEXT NOT NULL, angle_theme TEXT NOT NULL,
            caption TEXT NOT NULL, hashtags TEXT NOT NULL,
            post_time TEXT NOT NULL, image_path TEXT,
            target_facebook TEXT, target_instagram TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewer_notes TEXT, created_at INTEGER NOT NULL)""")
        conn.commit()
        conn.close()
        store = Store(path)
        cols = [r[1] for r in
                store.conn.execute("PRAGMA table_info(drafts)").fetchall()]
        self.assertIn("format", cols)
        store.close()

    def test_publish_and_metrics(self):
        store, _ = make_store()
        did = store.save_draft("gutter-genie", TODAY, "t", "c", ["#a"],
                               "09:00", None, None, None)
        store.record_publish(did, "fbpage", "facebook", post_id="123")
        self.assertEqual(len(store.published_today("gutter-genie", TODAY)), 1)
        store.record_metrics("gutter-genie", "fbpage", 100, 80)
        m = store.latest_metrics("gutter-genie")
        self.assertEqual(m[0]["views"], 100)
        store.close()

    def test_learnings(self):
        store, _ = make_store()
        self.assertEqual(store.get_learnings("gutter-genie"), {})
        store.save_learnings("gutter-genie", {"winning_themes": ["x"]})
        self.assertEqual(store.get_learnings("gutter-genie")["winning_themes"],
                         ["x"])
        store.close()


class TestMediaGen(unittest.TestCase):
    def test_all_format_layouts_render_correct_size(self):
        from PIL import Image
        tmp = tempfile.mkdtemp(prefix="pp-media-")
        for biz in BUSINESSES:
            for fmt in formats_mod.FORMAT_NAMES + [None, "bogus"]:
                out = os.path.join(tmp, "%s-%s.png" % (biz["slug"], fmt))
                media_gen.generate(biz, "Test headline here", "prompt", out,
                                   dry_run=True, fmt=fmt)
                with Image.open(out) as im:
                    self.assertEqual(im.size, (1080, 1350),
                                     (biz["slug"], fmt))

    def test_banner_only_uses_config_text(self):
        lines = media_gen._banner_lines(GG)
        self.assertEqual(lines[0], "GUTTER GENIE")
        self.assertIn("204-972-0325", lines)
        no_phone = dict(GG, phone=None)
        self.assertEqual(media_gen._banner_lines(no_phone), ["GUTTER GENIE"])


class TestPublisherDryRun(unittest.TestCase):
    def test_dry_run_records_and_never_runs(self):
        import subprocess
        pub = Publisher(dry_run=True)
        real_run = subprocess.run

        def boom(*a, **k):
            raise AssertionError("subprocess must never run in dry-run")

        subprocess.run = boom
        try:
            draft = {"id": 7, "business": "gutter-genie",
                     "caption": "c", "hashtags": json.dumps(["#a"]),
                     "image_path": "/x.png", "angle_theme": "t",
                     "run_date": TODAY, "target_facebook": "1",
                     "target_instagram": None}
            res = pub.publish(draft, "facebook")
            self.assertEqual(res.get("skipped"), "dry-run")
            self.assertEqual(len(pub.calls), 1)
            self.assertEqual(pub.calls[0]["draft_id"], 7)
        finally:
            subprocess.run = real_run

    def test_dry_run_list_returns_empty(self):
        pub = Publisher(dry_run=True)
        self.assertEqual(pub.list_facebook_today("1", TODAY), [])
        self.assertEqual(pub.list_instagram_today("1", TODAY), [])


class TestPipelineDryRun(unittest.TestCase):
    def test_full_business_run(self):
        from pilot.pipeline import Pipeline
        store, tmp = make_store()
        media = os.path.join(tmp, "media")
        pipe = Pipeline(store, media, dry_run=True, posts_per_business=1)
        report = pipe.run_business(GG, TODAY)
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["drafts"]), 1)
        d = report["drafts"][0]
        self.assertIn(d["format"], formats_mod.FORMAT_BY_NAME)
        row = store.get_draft(d["id"])
        self.assertEqual(row["format"], d["format"])
        store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
