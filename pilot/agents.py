"""The 36 agents: 6 specialist roles x 6 businesses.

Roles:
  1. TrendScout  - what to post about today (web search, keyless)
  2. Copywriter  - caption in Jay's voice (short, direct, no em dashes)
  3. Designer    - 1080x1350 branded creative (see media_gen)
  4. HashtagSEO  - tags + posting-time recommendation
  5. Reviewer    - quality gate (no invented claims, no dup themes, brand-safe)
  6. Analyst     - metrics pull + learnings for tomorrow's briefs
"""

import hashlib
import os
import re
import textwrap

from . import media_gen
from .businesses import POST_TIMES

# ---------------------------------------------------------------------------
# 1. Trend Scout
# ---------------------------------------------------------------------------

SEARCH_QUERIES = {
    "gutter-genie": "gutter cleaning tips fall homeowners",
    "winnipeg-web-works": "small business website tips local SEO",
    "move-metal": "junk removal tips homeowners",
    "bnb-media": "Airbnb listing tips more bookings video",
    "demoboss": "home renovation demolition tips",
    "quonset-place": "quonset hut steel building uses",
}


class TrendScout:
    """Finds what to post about today. Keyless DDG search; curated bank fallback."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run

    def _web_angles(self, biz):
        if self.dry_run:
            return []
        import requests
        try:
            q = SEARCH_QUERIES.get(biz["slug"], biz["name"] + " tips")
            r = requests.get("https://html.duckduckgo.com/html/",
                             params={"q": q}, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
            titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', r.text,
                                re.DOTALL)[:5]
            clean = [re.sub(r"<[^>]+>", "", t).strip() for t in titles]
            return [c for c in clean if len(c) > 12][:3]
        except Exception:
            return []

    def scout(self, biz, run_date, learnings, n=2):
        """Return n angle dicts: {theme, hook, body}."""
        seed_src = biz["slug"] + run_date
        seed = int(hashlib.sha256(seed_src.encode()).hexdigest()[:8], 16)
        bank = list(biz["angles"])
        # Analyst learnings bias: prefer themes tagged as winners.
        winners = set((learnings.get("winning_themes") or []))
        if winners:
            bank = sorted(bank, key=lambda a: 0 if a["theme"] in winners else 1)
        web = self._web_angles(biz)
        picks = []
        used = set()
        # Rotate through the bank deterministically so themes vary day to day.
        order = sorted(range(len(bank)), key=lambda i: (seed + i * 7) % 997)
        for i in order:
            if len(picks) >= n:
                break
            a = bank[i]
            if a["theme"] in used:
                continue
            used.add(a["theme"])
            picks.append(dict(a))
        # Fold any web findings into the body of the first angle as a "seen online" note.
        if web and picks:
            picks[0]["body"] += " Seen online today: " + web[0][:120] + "."
        return picks


# ---------------------------------------------------------------------------
# 2. Copywriter
# ---------------------------------------------------------------------------

HOOK_STYLES = [
    "{hook}.",
    "Quick one: {hook}.",
    "Heads up: {hook}.",
]


class Copywriter:
    """Writes the caption in Jay's voice. Short, direct, local, clear CTA."""

    @staticmethod
    def sanitize(text):
        text = text.replace("\u2014", ", ").replace("\u2013", "-").replace("\u2011", "-")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def write(self, biz, angle, seed=0):
        style = HOOK_STYLES[seed % len(HOOK_STYLES)]
        hook = angle["hook"].rstrip(".")  # style adds the period
        hook = style.format(hook=hook).strip()
        caption = "%s\n\n%s\n\n%s" % (hook, angle["body"], biz["cta"])
        return self.sanitize(caption)

    def revise(self, biz, angle, caption, reasons, seed=1):
        """One rewrite pass addressing reviewer reasons."""
        body = angle["body"]
        # Strip anything the reviewer flagged: prices, superlatives, invented URLs.
        body = re.sub(r"\$[\d,]+(?:\.\d+)?", "a straight price", body)
        for word in ("guaranteed", "Guaranteed", "#1", "5-star", "five-star"):
            body = body.replace(word, "done right")
        body = re.sub(r"(https?://|www\.)\S+", "", body)
        new_angle = dict(angle, body=body.strip())
        return self.write(biz, new_angle, seed=seed)


# ---------------------------------------------------------------------------
# 3. Designer
# ---------------------------------------------------------------------------

class Designer:
    """Generates the 1080x1350 creative via media_gen."""

    def __init__(self, media_dir, dry_run=False):
        self.media_dir = media_dir
        self.dry_run = dry_run

    def design(self, biz, angle, run_date, idx):
        fname = "pp-%s-%s-%d.png" % (run_date, biz["slug"], idx)
        out_path = os.path.join(self.media_dir, fname)
        image_prompt = ("social media ad photo, %s, %s, %s, no text, no words, "
                        "no letters, no watermark" % (biz["name"], biz["what"], angle["theme"]))
        media_gen.generate(biz, angle["hook"], image_prompt, out_path,
                           dry_run=self.dry_run)
        return out_path


# ---------------------------------------------------------------------------
# 4. Hashtag / SEO
# ---------------------------------------------------------------------------

class HashtagSEO:
    """Picks 3-6 hashtags from the business bank and a posting time."""

    def pick(self, biz, angle, run_date, idx):
        seed = int(hashlib.sha256((biz["slug"] + run_date + str(idx)).encode())
                   .hexdigest()[:8], 16)
        bank = biz["hashtags"]
        # Always include the brand tag, rotate the rest.
        tags = [bank[0]]
        rest = bank[1:]
        order = sorted(range(len(rest)), key=lambda i: (seed + i * 5) % 991)
        for i in order:
            if len(tags) >= 5:
                break
            tags.append(rest[i])
        post_time = POST_TIMES[(seed + idx) % len(POST_TIMES)]
        return tags, post_time


# ---------------------------------------------------------------------------
# 5. Reviewer
# ---------------------------------------------------------------------------

PRICE_RE = re.compile(r"\$[\d,]+")
URL_RE = re.compile(r"(https?://|www\.)([A-Za-z0-9.-]+)")
SUPERLATIVE_RES = [
    re.compile(r"(?i)\bbest\b.{0,30}\b(winnipeg|manitoba)\b"),
    re.compile(r"#1"),
    re.compile(r"(?i)guaranteed"),
    re.compile(r"(?i)5-star|five-star"),
    re.compile(r"(?i)customers love|clients rave"),
    re.compile(r"(?i)\bnever\b.{0,20}\bbeaten\b"),
]
STOPWORDS = set("the a an and or of to in on for with is are was were be at by we our you your it its this that these those as from".split())


def _keywords(text):
    return set(w.lower() for w in re.findall(r"[a-zA-Z]{4,}", text)) - STOPWORDS


class Reviewer:
    """Quality gate. Returns (ok, reasons). Never invents, never duplicates."""

    def __init__(self, post_log_path=None):
        self.post_log_path = post_log_path or os.path.expanduser(
            "~/workspace/advertising/post-log.md")

    def _recent_themes(self, biz_slug, days=14):
        themes = []
        try:
            with open(self.post_log_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-400:]
        except FileNotFoundError:
            return themes
        for line in lines[-400:]:
            if "business: %s" % biz_slug not in line:
                continue
            m = re.search(r"theme:\s*(.+?)(?:\s*\||$)", line)
            if m:
                themes.append(m.group(1))
        return themes

    def review(self, biz, caption, hashtags, theme, image_path):
        reasons = []

        if "\u2014" in caption or "\u2013" in caption:
            reasons.append("em/en dash in caption (Jay's style: never)")
        if len(caption) > 2200:
            reasons.append("caption over 2200 chars")
        if not (3 <= len(hashtags) <= 6):
            reasons.append("hashtag count %d not in 3-6" % len(hashtags))
        if PRICE_RE.search(caption):
            reasons.append("price figure in caption (never invent prices)")
        for rx in SUPERLATIVE_RES:
            if rx.search(caption):
                reasons.append("unverifiable superlative/claim: %s" % rx.pattern[:40])
                break
        for m in URL_RE.finditer(caption):
            domain = m.group(2).lower().rstrip(".")
            allowed = [d.lower() for d in biz.get("allowed_domains", [])]
            if not any(domain == d or domain.endswith("." + d) for d in allowed):
                reasons.append("unapproved URL domain in caption: %s" % domain)
                break
        # Duplicate-theme check against recent post history.
        new_kw = _keywords(theme)
        for old in self._recent_themes(biz["slug"]):
            old_kw = _keywords(old)
            if not new_kw or not old_kw:
                continue
            overlap = len(new_kw & old_kw) / max(len(new_kw), len(old_kw))
            if overlap >= 0.5:
                reasons.append("theme too close to recent post: %s" % old[:70])
                break
        # Image sanity.
        try:
            from PIL import Image as PILImage
            with PILImage.open(image_path) as im:
                if im.size != (1080, 1350):
                    reasons.append("image not 1080x1350 (got %s)" % (im.size,))
        except Exception as e:
            reasons.append("image unreadable: %s" % e)

        return (len(reasons) == 0), reasons


# ---------------------------------------------------------------------------
# 6. Analyst
# ---------------------------------------------------------------------------

class Analyst:
    """Pulls reach metrics after posting and writes learnings for tomorrow."""

    def __init__(self, store, dry_run=False):
        self.store = store
        self.dry_run = dry_run

    def analyze(self, biz):
        """Returns a summary dict. In dry-run, records nothing and says so."""
        if self.dry_run:
            return {"business": biz["slug"], "dry_run": True,
                    "note": "metrics skipped in dry-run"}
        summary = {"business": biz["slug"], "targets": {}}
        # Best-effort metric pulls; failures are logged, never fatal.
        fb = biz["targets"].get("facebook")
        ig = biz["targets"].get("instagram")
        if fb:
            summary["targets"]["facebook"] = self._fb_metrics(fb)
        if ig:
            summary["targets"]["instagram"] = self._ig_metrics(ig)
        # Learnings: remember which themes got published recently.
        recent = self.store.list_drafts(business=biz["slug"], status="published")
        themes = [d["angle_theme"] for d in recent[-10:]]
        learn = self.store.get_learnings(biz["slug"])
        learn["recent_themes"] = themes
        self.store.save_learnings(biz["slug"], learn)
        return summary

    def _fb_metrics(self, page_id):
        import json as _json
        import subprocess
        try:
            out = subprocess.run(
                ["facebook-cli", "pages", "posts", "--page-id", page_id,
                 "--limit", "10"], capture_output=True, text=True, timeout=60)
            data = _json.loads(out.stdout or "{}")
            posts = data.get("posts", data if isinstance(data, list) else [])
            views = sum(p.get("views", 0) or 0 for p in posts if isinstance(p, dict))
            return {"recent_posts": len(posts), "views": views}
        except Exception as e:
            return {"error": str(e)[:120]}

    def _ig_metrics(self, account_id):
        import json as _json
        import subprocess
        try:
            out = subprocess.run(
                ["instagram-cli", "posts", "--account-id", account_id,
                 "--limit", "10", "--post-types", "POST,REEL"],
                capture_output=True, text=True, timeout=60)
            data = _json.loads(out.stdout or "{}")
            posts = data.get("posts", [])
            return {"recent_posts": len(posts)}
        except Exception as e:
            return {"error": str(e)[:120]}
