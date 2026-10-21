"""Generate a review report for a day's drafts.

Read-only: writes a markdown report under data/reports/ so the owner can
review everything (captions, formats, slots, reviewer notes) in one place
before approving anything in the dashboard.

Run:  python3 scripts/report.py [YYYY-MM-DD]   (default: today)
"""

import datetime
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from pilot.businesses import BUSINESSES  # noqa: E402
from pilot.formats import FORMAT_BY_NAME  # noqa: E402
from pilot.queue import export_queue_markdown, queue_summary  # noqa: E402
from pilot.store import Store  # noqa: E402

DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(DATA_DIR, "reports")


def main():
    run_date = (sys.argv[1] if len(sys.argv) > 1
                else datetime.date.today().isoformat())
    store = Store(os.path.join(DATA_DIR, "pilot.db"))

    lines = ["# Post Pilot run report - %s" % run_date, ""]
    summary = queue_summary(store, run_date)
    total = sum(b["total"] for b in summary["businesses"])
    lines.append("drafts: %d across %d businesses, %d slot conflict(s)" %
                 (total, len(summary["businesses"]),
                  summary["total_conflicts"]))
    lines.append("")

    for b in BUSINESSES:
        rows = store.list_drafts(run_date=run_date, business=b["slug"])
        lines.append("## %s (%d drafts)" % (b["name"], len(rows)))
        if not rows:
            lines.append("_no drafts_")
            lines.append("")
            continue
        for r in rows:
            tags = " ".join(json.loads(r["hashtags"]))
            fmt = FORMAT_BY_NAME.get(r.get("format"), {}).get(
                "label", r.get("format") or "n/a")
            img = os.path.basename(r.get("image_path") or "")
            lines.append("### draft #%d - %s" % (r["id"], r["angle_theme"]))
            lines.append("- status: %s | slot: %s | format: %s" %
                         (r["status"], r["post_time"], fmt))
            lines.append("- tags: %s" % tags)
            lines.append("- image: %s" % img)
            lines.append("- reviewer: %s" % (r.get("reviewer_notes") or "-"))
            lines.append("")
            for cl in r["caption"].split("\n"):
                lines.append("  > %s" % cl)
            lines.append("")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(export_queue_markdown(store, run_date))

    os.makedirs(REPORT_DIR, exist_ok=True)
    out = os.path.join(REPORT_DIR, "PP-%s.md" % run_date)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote %s (%d drafts)" % (out, total))
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
