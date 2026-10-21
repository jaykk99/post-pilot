"""Daily pipeline: 6 agents per business.

scout -> (copywriter + designer in parallel) -> hashtag/seo -> reviewer gate
  -> (one revise + re-review on fail) -> draft queue (status=draft, needs Jay)

Nothing here publishes. Publishing happens only from the dashboard after Jay
approves, via Publisher.publish().
"""

import concurrent.futures
import os
import traceback

from .agents import (Analyst, Copywriter, Designer, HashtagSEO, Reviewer,
                     TrendScout)
from .businesses import BUSINESSES, BY_SLUG
from .publisher import Publisher


class Pipeline:
    def __init__(self, store, media_dir, dry_run=False, posts_per_business=2):
        self.store = store
        self.media_dir = media_dir
        self.dry_run = dry_run
        self.posts_per_business = posts_per_business
        self.scout = TrendScout(dry_run=dry_run)
        self.copywriter = Copywriter()
        self.designer = Designer(media_dir, dry_run=dry_run)
        self.seo = HashtagSEO()
        self.reviewer = Reviewer()
        self.analyst = Analyst(store, dry_run=dry_run)

    def run_business(self, biz, run_date):
        """Run the full agent chain for one business. Returns a report dict."""
        report = {"business": biz["slug"], "drafts": [], "rejected": [],
                  "errors": []}
        try:
            learnings = self.store.get_learnings(biz["slug"])
            angles = self.scout.scout(biz, run_date, learnings,
                                      n=self.posts_per_business + 2,
                                      store=self.store)
            for idx, angle in enumerate(angles):
                if len(report["drafts"]) >= self.posts_per_business:
                    break
                try:
                    draft = self._make_draft(biz, angle, run_date, idx)
                    if draft:
                        report["drafts"].append(draft)
                    else:
                        report["rejected"].append(angle["theme"])
                except Exception as e:
                    report["errors"].append("%s: %s" % (angle.get("theme"), e))
                    traceback.print_exc()
        except Exception as e:
            report["errors"].append("pipeline: %s" % e)
            traceback.print_exc()
        return report

    def _make_draft(self, biz, angle, run_date, idx):
        fmt = angle.get("format")
        # copywriter + designer run in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fut_caption = ex.submit(self.copywriter.write, biz, angle, idx)
            fut_image = ex.submit(self.designer.design, biz, angle, run_date, idx, fmt)
            caption = fut_caption.result()
            image_path = fut_image.result()

        hashtags, post_time = self.seo.pick(biz, angle, run_date, idx)

        ok, reasons = self.reviewer.review(biz, caption, hashtags,
                                           angle["theme"], image_path,
                                           fmt=fmt, store=self.store,
                                           run_date=run_date)
        if not ok:
            # One revise + re-review, then give up.
            caption = self.copywriter.revise(biz, angle, caption, reasons, seed=idx + 1)
            ok, reasons = self.reviewer.review(biz, caption, hashtags,
                                               angle["theme"], image_path,
                                               fmt=fmt, store=self.store,
                                               run_date=run_date)
            if not ok:
                return None

        draft_id = self.store.save_draft(
            business=biz["slug"], run_date=run_date,
            angle_theme=angle["theme"], caption=caption, hashtags=hashtags,
            post_time=post_time, image_path=image_path,
            target_facebook=biz["targets"]["facebook"],
            target_instagram=biz["targets"]["instagram"],
            reviewer_notes="; ".join(reasons) if reasons else "passed first review",
            format=fmt or "")
        return {"id": draft_id, "theme": angle["theme"], "image": image_path,
                "caption": caption, "hashtags": hashtags, "post_time": post_time,
                "format": fmt or ""}

    def run_daily(self, run_date):
        """Run all 6 businesses. Returns list of per-business reports."""
        reports = []
        for biz in BUSINESSES:
            reports.append(self.run_business(biz, run_date))
        return reports

    def run_analyst(self):
        """Post-publish metrics + learnings for every business."""
        return [self.analyst.analyze(b) for b in BUSINESSES]


def make_publisher(dry_run=False):
    return Publisher(dry_run=dry_run)
