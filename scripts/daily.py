"""Real daily run: generate today's drafts (all 6 businesses).

Drafts only. Nothing publishes without Jay's approval in the dashboard.
Run:  python3 scripts/daily.py
Then open the dashboard (python3 app.py) and approve.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from pilot.pipeline import Pipeline  # noqa: E402
from pilot.store import Store  # noqa: E402

DATA_DIR = os.path.join(BASE_DIR, "data")


def main():
    import datetime
    run_date = datetime.date.today().isoformat()
    store = Store(os.path.join(DATA_DIR, "pilot.db"))
    pipe = Pipeline(store, os.path.join(DATA_DIR, "media"), dry_run=False)
    reports = pipe.run_daily(run_date)
    for r in reports:
        print("[%s] drafts=%d rejected=%d errors=%d" % (
            r["business"], len(r["drafts"]), len(r["rejected"]), len(r["errors"])))
        for d in r["drafts"]:
            print("   #%d %s" % (d["id"], d["theme"]))
    store.close()


if __name__ == "__main__":
    main()
