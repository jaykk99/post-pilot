"""Post-format rotation for Post Pilot.

The owner's standing rule: the FORMAT must rotate, never repeat the same
format two days in a row for one business, and the template reel may run at
most once per week per business. This module owns that rule:

  - FORMATS: the catalog of known formats.
  - assign_formats(): deterministically pick a format per angle, honoring
    the no-repeat-yesterday rule, the weekly template-reel cap, and
    no-duplicate-format within one day's run.
  - prior_formats(): read what a business already used, from the draft store.

Everything here is planning metadata. It never publishes anything.
"""

import datetime
import hashlib
import re

# ---------------------------------------------------------------------------
# Format catalog
# ---------------------------------------------------------------------------

FORMATS = [
    {
        "name": "before-after",
        "label": "Before/After Composite",
        "desc": "Real side-by-side before/after photos (Gutter Genie vault "
                "picks, owner-approved only).",
    },
    {
        "name": "how-it-works",
        "label": "How-It-Works Explainer",
        "desc": "Faceless animated-style explainer: the service broken into "
                "3-4 numbered steps.",
    },
    {
        "name": "stock-voiceover",
        "label": "Stock Footage + Voiceover",
        "desc": "Stock footage edit with a voiceover hook and burned-in "
                "captions.",
    },
    {
        "name": "screen-walkthrough",
        "label": "Screen Walkthrough",
        "desc": "Real screen recording walkthrough (audit teardowns, quote "
                "tool, listing pages).",
    },
    {
        "name": "photo-story",
        "label": "Photo / Story Post",
        "desc": "A single real photo from the job with a short story "
                "caption.",
    },
    {
        "name": "tip-card",
        "label": "Tip Card",
        "desc": "One practical tip as a branded card. Quick value, no pitch.",
    },
    {
        "name": "offer-card",
        "label": "Offer Card",
        "desc": "Branded card naming a concrete offer (free quote, free "
                "inspection, free call). Facts only, no invented prices.",
    },
    {
        "name": "template-reel",
        "label": "Template Reel",
        "desc": "Branded AI-background template reel. Max 1x per business "
                "per week.",
        "weekly_cap": 1,
    },
]

FORMAT_BY_NAME = {f["name"]: f for f in FORMATS}
FORMAT_NAMES = [f["name"] for f in FORMATS]

# Formats that need real owner-supplied assets before they may be used.
NEEDS_REAL_ASSETS = {"before-after", "photo-story"}

# Weekly caps beyond the template-reel rule.
WEEKLY_CAPS = {f["name"]: f.get("weekly_cap") for f in FORMATS
               if f.get("weekly_cap")}

STATUSES_THAT_COUNT = ("draft", "approved", "published")


def _seed(*parts):
    src = "|".join(str(p) for p in parts)
    return int(hashlib.sha256(src.encode()).hexdigest()[:8], 16)


def _iso_days_ago(run_date, days):
    d = datetime.date.fromisoformat(run_date) - datetime.timedelta(days=days)
    return d.isoformat()


def prior_formats(store, biz_slug, run_date, days=8):
    """Formats a business already used on recent run dates.

    Returns a dict {run_date: [format names]} built from the draft store,
    including in-progress (draft) rows so the rule holds even before anything
    is published. statuses: draft/approved/published all count.
    """
    usage = {}
    for ago in range(days):
        day = _iso_days_ago(run_date, ago)
        rows = store.list_drafts(run_date=day, business=biz_slug)
        fmts = [r.get("format") for r in rows
                if r.get("format") and r.get("status") in STATUSES_THAT_COUNT]
        if fmts:
            usage[day] = fmts
    return usage


def week_counts(store, biz_slug, run_date, days=7):
    """How many times each format was used in the trailing 7 days."""
    usage = prior_formats(store, biz_slug, run_date, days=days)
    counts = {}
    for fmts in usage.values():
        for f in fmts:
            counts[f] = counts.get(f, 0) + 1
    return counts


def eligible_formats(store, biz_slug, run_date, already_picked=()):
    """Formats that may be used for the next draft of this business today.

    Excludes: yesterday's formats, formats already picked today, and any
    format that has hit its weekly cap. Falls back to the full pool if
    everything is excluded (rule violation is better logged than crashing
    the run).
    """
    usage = prior_formats(store, biz_slug, run_date)
    yesterday = set(usage.get(_iso_days_ago(run_date, 1), []))
    today = set(usage.get(run_date, [])) | set(already_picked)
    counts = week_counts(store, biz_slug, run_date)

    eligible = []
    for name in FORMAT_NAMES:
        if name in yesterday:
            continue
        if name in today:
            continue
        cap = WEEKLY_CAPS.get(name)
        if cap is not None and counts.get(name, 0) >= cap:
            continue
        eligible.append(name)
    return eligible or list(FORMAT_NAMES)


def assign_formats(store, biz_slug, run_date, n):
    """Deterministically assign n formats honoring the rotation rules.

    Deterministic (seeded on slug+date) so a re-run of the same day picks
    the same formats, and so the dashboard preview matches the generator.
    """
    picked = []
    for i in range(n):
        pool = eligible_formats(store, biz_slug, run_date,
                                already_picked=picked)
        # Deterministic rotation through the pool.
        start = _seed("format", biz_slug, run_date, i) % len(pool)
        picked.append(pool[start])
    return picked


def check_rotation(store, biz_slug, run_date, fmt):
    """Return a list of rotation violations for fmt, or []."""
    usage = prior_formats(store, biz_slug, run_date)
    violations = []
    yesterday = set(usage.get(_iso_days_ago(run_date, 1), []))
    if fmt in yesterday:
        violations.append("format '%s' was used yesterday (rotation rule)"
                          % fmt)
    today = set(usage.get(run_date, []))
    if fmt in today:
        violations.append("format '%s' already used today" % fmt)
    counts = week_counts(store, biz_slug, run_date)
    cap = WEEKLY_CAPS.get(fmt)
    if cap is not None and counts.get(fmt, 0) >= cap:
        violations.append("format '%s' hit weekly cap of %d" % (fmt, cap))
    return violations


# -- post-log helpers (shared advertising log) ------------------------------

LOG_FORMAT_RE = re.compile(r"\|\s*format:\s*([a-z][a-z0-9-]*)")


def formats_from_post_log(post_log_path, biz_slug, days=14):
    """Fallback usage history parsed from the shared advertising post log.

    Used when the local draft store has no history (fresh DB). Returns
    {date_str: [format names]}.
    """
    usage = {}
    try:
        with open(post_log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-600:]
    except FileNotFoundError:
        return usage
    for line in lines:
        if "business: %s" % biz_slug not in line:
            continue
        m_date = re.match(r"-\s*(\d{4}-\d{2}-\d{2})", line)
        m_fmt = LOG_FORMAT_RE.search(line)
        if m_date and m_fmt and m_fmt.group(1) in FORMAT_BY_NAME:
            usage.setdefault(m_date.group(1), []).append(m_fmt.group(1))
    return usage
