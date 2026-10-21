"""SQLite persistence for Post Pilot. Stdlib only."""

import json
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business TEXT NOT NULL,
    run_date TEXT NOT NULL,
    angle_theme TEXT NOT NULL,
    caption TEXT NOT NULL,
    hashtags TEXT NOT NULL,
    post_time TEXT NOT NULL,
    image_path TEXT,
    target_facebook TEXT,
    target_instagram TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    format TEXT NOT NULL DEFAULT '',
    reviewer_notes TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS publishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    target TEXT NOT NULL,
    platform TEXT NOT NULL,
    post_id TEXT,
    url TEXT,
    published_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business TEXT NOT NULL,
    target TEXT NOT NULL,
    views INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    sampled_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS learnings (
    business TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_business_date ON drafts(business, run_date);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
"""


class Store:
    def __init__(self, db_path):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.db_path = db_path
        # check_same_thread=False + a lock: the dashboard server is threaded.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self.conn.executescript(SCHEMA)
            # Migration for DBs created before the format column existed.
            try:
                self.conn.execute(
                    "ALTER TABLE drafts ADD COLUMN format TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # column already there
            self.conn.commit()

    def _exec(self, sql, args=()):
        with self._lock:
            return self.conn.execute(sql, args)

    def _commit(self):
        with self._lock:
            self.conn.commit()

    def _now(self):
        return int(time.time())

    # drafts -----------------------------------------------------------
    def save_draft(self, business, run_date, angle_theme, caption, hashtags,
                   post_time, image_path, target_facebook, target_instagram,
                   reviewer_notes="", format=""):
        cur = self._exec(
            """INSERT INTO drafts (business, run_date, angle_theme, caption, hashtags,
               post_time, image_path, target_facebook, target_instagram, status,
               format, reviewer_notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (business, run_date, angle_theme, caption, json.dumps(hashtags),
             post_time, image_path, target_facebook, target_instagram,
             "draft", format, reviewer_notes, self._now()))
        self._commit()
        return cur.lastrowid

    def get_draft(self, draft_id):
        row = self._exec("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return dict(row) if row else None

    def list_drafts(self, run_date=None, business=None, status=None):
        q = "SELECT * FROM drafts WHERE 1=1"
        args = []
        if run_date:
            q += " AND run_date=?"; args.append(run_date)
        if business:
            q += " AND business=?"; args.append(business)
        if status:
            q += " AND status=?"; args.append(status)
        q += " ORDER BY business, id"
        return [dict(r) for r in self._exec(q, args).fetchall()]

    def set_status(self, draft_id, status, reviewer_notes=None):
        if reviewer_notes is None:
            self._exec("UPDATE drafts SET status=? WHERE id=?", (status, draft_id))
        else:
            self._exec("UPDATE drafts SET status=?, reviewer_notes=? WHERE id=?",
                              (status, draft_id, reviewer_notes))
        self._commit()

    def update_caption(self, draft_id, caption):
        self._exec("UPDATE drafts SET caption=? WHERE id=?", (caption, draft_id))
        self._commit()

    # publishes --------------------------------------------------------
    def record_publish(self, draft_id, target, platform, post_id=None, url=None):
        self._exec(
            "INSERT INTO publishes (draft_id, target, platform, post_id, url, published_at)"
            " VALUES (?,?,?,?,?,?)",
            (draft_id, target, platform, post_id, url, self._now()))
        self._commit()

    def published_today(self, business, run_date):
        rows = self._exec(
            """SELECT p.* FROM publishes p JOIN drafts d ON d.id = p.draft_id
               WHERE d.business=? AND d.run_date=?""", (business, run_date)).fetchall()
        return [dict(r) for r in rows]

    # metrics ----------------------------------------------------------
    def record_metrics(self, business, target, views, reach):
        self._exec(
            "INSERT INTO metrics (business, target, views, reach, sampled_at)"
            " VALUES (?,?,?,?,?)", (business, target, views, reach, self._now()))
        self._commit()

    def latest_metrics(self, business):
        rows = self._exec(
            """SELECT * FROM metrics WHERE business=?
               ORDER BY sampled_at DESC LIMIT 20""", (business,)).fetchall()
        return [dict(r) for r in rows]

    # learnings --------------------------------------------------------
    def get_learnings(self, business):
        row = self._exec("SELECT data FROM learnings WHERE business=?",
                                (business,)).fetchone()
        return json.loads(row["data"]) if row else {}

    def save_learnings(self, business, data):
        self._exec(
            "INSERT OR REPLACE INTO learnings (business, data, updated_at) VALUES (?,?,?)",
            (business, json.dumps(data), self._now()))
        self._commit()

    def close(self):
        self.conn.close()
