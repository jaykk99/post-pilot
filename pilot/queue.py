"""Draft queue management for Post Pilot.

Read + reschedule helpers over the draft store. This is planning tooling
only: it never approves, never publishes, and never touches credentials.

  - queue_summary(): per-business counts, formats, and post-time conflicts.
  - find_conflicts(): same business, same post_time, 2+ live drafts.
  - next_free_slot(): first POST_TIMES slot with no live draft for a business.
  - reschedule(): move one draft to another slot (validated).
  - export_queue_markdown(): human-readable queue preview for review.

A "live" draft is one that could still go out: status draft or approved.
Rejected and published drafts do not occupy a slot.
"""

import json

from .businesses import POST_TIMES
from .formats import FORMAT_BY_NAME

LIVE_STATUSES = ("draft", "approved")


def _live(rows):
    return [r for r in rows if r.get("status") in LIVE_STATUSES]


def queue_summary(store, run_date):
    """Per-business queue state for one run date."""
    from .businesses import BUSINESSES
    summary = {"run_date": run_date, "businesses": []}
    for b in BUSINESSES:
        rows = store.list_drafts(run_date=run_date, business=b["slug"])
        live = _live(rows)
        by_status = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        formats = [FORMAT_BY_NAME.get(r.get("format"), {}).get("label", "?")
                   for r in live if r.get("format")]
        summary["businesses"].append({
            "slug": b["slug"],
            "name": b["name"],
            "total": len(rows),
            "by_status": by_status,
            "live": len(live),
            "formats": formats,
            "slots": sorted({r["post_time"] for r in live}),
            "conflicts": find_conflicts(rows),
        })
    summary["total_conflicts"] = sum(len(b["conflicts"])
                                     for b in summary["businesses"])
    return summary


def find_conflicts(rows):
    """Return [(post_time, [draft_ids])] where a slot is double-booked."""
    by_time = {}
    for r in _live(rows):
        by_time.setdefault(r["post_time"], []).append(r["id"])
    return [(t, ids) for t, ids in sorted(by_time.items()) if len(ids) > 1]


def next_free_slot(store, biz_slug, run_date, exclude_draft_id=None):
    """First POST_TIMES slot with no live draft for this business today."""
    rows = store.list_drafts(run_date=run_date, business=biz_slug)
    taken = {r["post_time"] for r in _live(rows)
             if r["id"] != exclude_draft_id}
    for t in POST_TIMES:
        if t not in taken:
            return t
    return None


def reschedule(store, draft_id, new_time):
    """Move a draft to another posting slot. Returns the updated draft.

    Raises ValueError on bad slot, KeyError on unknown draft.
    """
    if new_time not in POST_TIMES:
        raise ValueError("slot %r not in POST_TIMES %s" % (new_time,
                                                           POST_TIMES))
    d = store.get_draft(draft_id)
    if not d:
        raise KeyError("no draft #%d" % draft_id)
    if d["status"] not in LIVE_STATUSES:
        raise ValueError("draft #%d is %s, only draft/approved move" %
                         (draft_id, d["status"]))
    # Warn (not fail) if the target slot is already taken by this business.
    rows = store.list_drafts(run_date=d["run_date"], business=d["business"])
    taken = [r["id"] for r in _live(rows)
             if r["post_time"] == new_time and r["id"] != draft_id]
    store._exec("UPDATE drafts SET post_time=? WHERE id=?",
                (new_time, draft_id))
    store._commit()
    out = store.get_draft(draft_id)
    out["slot_warning"] = ("slot taken by draft(s) %s" % taken) if taken else ""
    return out


def auto_resolve_conflicts(store, run_date):
    """Move conflicted drafts to free slots. Returns list of moves.

    Keeps the lowest draft id on each contested slot (first generated wins),
    moves the rest. Drafts with no free slot stay put and are reported.
    """
    from .businesses import BUSINESSES
    moves = []
    for b in BUSINESSES:
        rows = store.list_drafts(run_date=run_date, business=b["slug"])
        for slot, ids in find_conflicts(rows):
            for did in sorted(ids)[1:]:
                free = next_free_slot(store, b["slug"], run_date,
                                      exclude_draft_id=did)
                if free:
                    reschedule(store, did, free)
                    moves.append({"draft_id": did, "business": b["slug"],
                                  "from": slot, "to": free})
                else:
                    moves.append({"draft_id": did, "business": b["slug"],
                                  "from": slot, "to": None,
                                  "note": "no free slot"})
    return moves


def export_queue_markdown(store, run_date):
    """Markdown preview of the whole day's queue, for review before approval."""
    summary = queue_summary(store, run_date)
    lines = ["# Post Pilot queue - %s" % run_date, ""]
    for b in summary["businesses"]:
        lines.append("## %s" % b["name"])
        lines.append("live drafts: %d  slots: %s" %
                     (b["live"], ", ".join(b["slots"]) or "none"))
        if b["formats"]:
            lines.append("formats: %s" % ", ".join(b["formats"]))
        if b["by_status"]:
            lines.append("status: %s" %
                         ", ".join("%s=%d" % kv
                                    for kv in sorted(b["by_status"].items())))
        rows = store.list_drafts(run_date=run_date, business=b["slug"])
        for r in _live(rows):
            tags = " ".join(json.loads(r["hashtags"]))
            fmt = FORMAT_BY_NAME.get(r.get("format"), {}).get("label",
                                                              r.get("format"))
            first_line = r["caption"].split("\n")[0][:80]
            lines.append("- #%d [%s] %s | format: %s | theme: %s" %
                         (r["id"], r["post_time"], first_line, fmt,
                          r["angle_theme"]))
            lines.append("  tags: %s" % tags)
        for slot, ids in b["conflicts"]:
            lines.append("  CONFLICT: slot %s double-booked by drafts %s" %
                         (slot, ids))
        lines.append("")
    if summary["total_conflicts"]:
        lines.append("**%d slot conflict(s) need resolving before approval.**" %
                     summary["total_conflicts"])
    else:
        lines.append("No slot conflicts.")
    return "\n".join(lines) + "\n"
