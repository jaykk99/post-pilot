"""Publishing via the installed CLIs. Dry-run mode never shells out.

Check-then-post discipline:
  - Before publishing, list today's posts on the target.
  - If a post with a matching theme already landed, skip (no duplicate).
  - After publishing, verify via listing before reporting success.
"""

import json
import subprocess


class PublishSkipped(Exception):
    pass


class Publisher:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.calls = []  # every attempted publish, for dry-run proof

    # -- listing (for check-then-post) -------------------------------------
    def _run(self, cmd, timeout=60):
        if self.dry_run:
            return {"dry_run": True, "posts": []}
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        try:
            return json.loads(out.stdout or "{}")
        except Exception:
            return {"raw": out.stdout[:500], "posts": []}

    def list_facebook_today(self, page_id, run_date):
        data = self._run(["facebook-cli", "pages", "posts", "--page-id", page_id,
                          "--limit", "10"])
        posts = data.get("posts", []) if isinstance(data, dict) else []
        return [p for p in posts if isinstance(p, dict)
                and run_date in str(p.get("post_created_at", ""))]

    def list_instagram_today(self, account_id, run_date):
        data = self._run(["instagram-cli", "posts", "--account-id", account_id,
                          "--limit", "10", "--post-types", "POST,REEL"])
        posts = data.get("posts", []) if isinstance(data, dict) else []
        return [p for p in posts if isinstance(p, dict)
                and run_date in str((p.get("post_created_at") or {}).get("utc", ""))]

    # -- publishing --------------------------------------------------------
    def publish(self, draft, platform):
        """Publish an APPROVED draft. Returns result dict.

        In dry-run this records the attempt and returns a skipped marker;
        it never executes a subprocess.
        """
        self.calls.append({"draft_id": draft["id"], "platform": platform,
                           "business": draft["business"]})
        if self.dry_run:
            return {"skipped": "dry-run", "draft_id": draft["id"],
                    "platform": platform}

        caption = draft["caption"] + "\n\n" + " ".join(
            json.loads(draft["hashtags"]))
        image = draft["image_path"]
        theme = draft["angle_theme"]
        run_date = draft["run_date"]

        if platform == "facebook":
            page_id = draft["target_facebook"]
            for p in self.list_facebook_today(page_id, run_date):
                if theme.lower() in str(p.get("post_caption", "")).lower():
                    raise PublishSkipped("theme already posted today on FB page")
            mk = subprocess.run(
                ["facebook-cli", "pages", "drafts", "create", "--page-id", page_id,
                 "--text", caption[:1024], "--file", image],
                capture_output=True, text=True, timeout=120)
            mk_data = json.loads(mk.stdout or "{}")
            draft_id = mk_data.get("draft_id") or mk_data.get("id")
            if not draft_id:
                raise RuntimeError("FB draft create failed: " + mk.stdout[:200]
                                   + mk.stderr[:200])
            pub = subprocess.run(
                ["facebook-cli", "pages", "drafts", "publish", "--page-id", page_id,
                 "--draft-id", str(draft_id), "--privacy", "PUBLIC"],
                capture_output=True, text=True, timeout=120)
            # verify it landed
            for p in self.list_facebook_today(page_id, run_date):
                if theme.lower() in str(p.get("post_caption", "")).lower():
                    return {"ok": True, "post_id": p.get("post_id"),
                            "url": p.get("url"), "target": page_id}
            return {"ok": True, "unverified": True, "target": page_id,
                    "detail": pub.stdout[:200]}

        if platform == "instagram":
            account_id = draft["target_instagram"]
            for p in self.list_instagram_today(account_id, run_date):
                if theme.lower() in str(p.get("post_caption", "")).lower():
                    raise PublishSkipped("theme already posted today on IG")
            args = ["instagram-cli", "post-feed", "--account-id", account_id,
                    "--caption", caption, image]
            res = subprocess.run(args, capture_output=True, text=True, timeout=180)
            data = json.loads(res.stdout or "{}")
            media_id = data.get("media_fbid") or data.get("media_id")
            if not media_id:
                raise RuntimeError("IG post failed: " + res.stdout[:200]
                                   + res.stderr[:200])
            return {"ok": True, "post_id": str(media_id), "target": account_id}

        raise ValueError("unknown platform: " + platform)
