# Post Pilot

Social posting system for Jay's 6 businesses. **36 specialist agents** (6 roles x 6 businesses) turn a daily brief into reviewed, ready-to-approve drafts. Nothing publishes without Jay's tap.

## The 36 agents

Per business, every day:

| # | Agent | Job |
|---|-------|-----|
| 1 | Trend Scout | Picks what to post about today (keyless web search + curated angle bank + analyst learnings) |
| 2 | Copywriter | Writes the caption in Jay's voice: short, direct, Winnipeg flavor, clear CTA, no em dashes |
| 3 | Designer | Generates the 1080x1350 branded creative (keyless Pollinations in real mode, PIL placeholder in dry-run). Burns in a banner with ONLY name + phone from config, so invented domains are scrubbed by construction |
| 4 | Hashtag/SEO | 3-6 hashtags from the business bank + suggested posting time |
| 5 | Reviewer | Quality gate: rejects invented prices, superlatives, unapproved URL domains, em dashes, and themes too close to recent posts (checks the post log). One revise-and-retry, then rejected |
| 6 | Analyst | Pulls view/reach metrics after posting and feeds learnings back into tomorrow's briefs |

Pipeline: `scout -> (copywriter + designer in parallel) -> hashtag -> reviewer gate -> draft queue -> Jay approves in dashboard -> publish via CLIs -> analyst logs metrics`.

## Businesses

Gutter Genie, Winnipeg Web Works, Move & Metal, Bnb Media, DemoBoss, Quonset Place.
Facts per business live in `pilot/businesses.py` (sourced from the advertising brand-facts file). Publish targets with connected accounts: GG/WWW/M&M/Quonset Facebook pages, @winnipegwebworks Instagram. Businesses with no connected account still get drafts; the dashboard marks those targets as skipped.

## Setup

Stdlib-only Python (http.server + sqlite3). Optional: Pillow and requests (preinstalled on most images; `pip install Pillow requests` if missing).

```bash
# 1. Generate today's drafts (no publishing, ever, from this step)
python3 scripts/daily.py

# 2. Start the dashboard (default port 8099)
python3 app.py
# open http://localhost:8099 on your phone

# Optional access code gate (recommended if exposed):
POST_PILOT_CODE=your-code python3 app.py
```

## Approval flow (the core rule)

1. Drafts land in the dashboard as **draft**.
2. Jay taps **Approve** (or edits, which re-runs the reviewer), **Reject**, or leaves it.
3. Only approved drafts show enabled **Publish to FB / IG** buttons.
4. Publishing uses check-then-post: it lists today's posts first and skips if the theme already landed, then verifies after publishing.
5. Every publish is appended to the shared advertising post log.

## Dry-run (proof it works without posting anything)

```bash
python3 scripts/dry_run.py
```

Runs all 6 businesses x 2 posts through the reviewer gate with mocked subprocess (any publish attempt raises), verifies every image is 1080x1350, self-tests the reviewer against a bad caption, and smoke-tests the dashboard API. Expected: 12 drafts, 0 publish calls.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

47 tests, stdlib only, zero network, zero publishing. Covers the reviewer gate, copywriter sanitize/revise, scout determinism, format rotation rules, store roundtrip + schema migration, per-format creative rendering for every business, the publisher dry-run subprocess-proof, queue management, and a full end-to-end pipeline run.

## Config validation

```bash
python3 scripts/validate_config.py
```

Lints `pilot/businesses.py` before a run: unique slugs, phone/email/domain/time syntax, hashtag banks (4-10, brand tag first), no em dashes or invented prices in any text, unique angle themes, valid per-angle formats, and a media palette for every business.

## Format rotation

Every draft gets a post format from `pilot/formats.py` (before/after composite, how-it-works explainer, stock+voiceover, screen walkthrough, photo/story, tip card, offer card, template reel). The rules, enforced by the reviewer gate:

- Never the same format two days in a row per business.
- No duplicate format within one day's drafts for a business.
- Template reel max 1x per business per week.

The Designer varies the creative layout per format (before/after divider, explainer step rail, tip kicker, offer frame, etc.). Formats are stored on each draft, shown in the dashboard, and logged to the advertising post log on publish.

## Queue management

```bash
python3 scripts/report.py [YYYY-MM-DD]   # writes data/reports/PP-<date>.md
```

Dashboard API: `GET /api/queue` (queue state + slot conflicts), `POST /api/queue/move/<draft_id>` (reschedule a draft's posting slot), `POST /api/queue/resolve` (auto-move conflicted drafts to free slots). Planning only: none of these approve or publish anything.

## Deploy

Not yet deployed. To put it on Render (free tier):

1. New Web Service from this repo, build: nothing, start: `python3 app.py`.
2. Set env `PORT` (Render provides it), `POST_PILOT_CODE` to something private.
3. Add a persistent disk mounted at `/opt/render/project/src/data` (SQLite + images live in `data/`), or drafts reset on each deploy.
4. Schedule `python3 scripts/daily.py` via a Render cron job (or any scheduler) each morning, then open the dashboard to approve.

## Keyless by design

- Images: Pollinations (no key). Search: DuckDuckGo HTML (no key). State: local SQLite. Publishing: the already-connected `instagram-cli` / `facebook-cli` on the worker machine. No new API keys anywhere.
