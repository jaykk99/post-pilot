"""Validate pilot/businesses.py + media palettes before a run.

Catches the mistakes that slip into configs: invented prices, em dashes
(the owner's style forbids them), bad domains, empty publish targets,
hashtag banks that break the reviewer, and palettes missing a business.

Run:  python3 scripts/validate_config.py
Exit: 0 = clean, 1 = problems found.
"""

import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from pilot import formats as formats_mod  # noqa: E402
from pilot import media_gen  # noqa: E402
from pilot.businesses import BUSINESSES, POST_TIMES  # noqa: E402

errors = []
warnings = []

PHONE_RE = re.compile(r"^\d{3}-\d{3}-\d{4}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DOMAIN_RE = re.compile(r"^(?!-)[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
PRICE_RE = re.compile(r"\$[\d,]+")
TAG_RE = re.compile(r"^#[A-Za-z0-9_]+$")
REQUIRED_KEYS = {"slug", "name", "tagline", "what", "area", "services",
                 "selling_points", "cta", "phone", "email", "site",
                 "allowed_domains", "targets", "hashtags", "angles"}


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def check_text(biz, field, text, label):
    if "\u2014" in text or "\u2013" in text:
        err("%s: %s contains an em/en dash (owner style: never)" %
            (biz, label))
    if PRICE_RE.search(text):
        err("%s: %s contains a price figure (never invent prices)" %
            (biz, label))


def main():
    slugs = [b["slug"] for b in BUSINESSES]
    if len(slugs) != len(set(slugs)):
        err("duplicate business slugs")
    if len(BUSINESSES) != 6:
        warn("expected 6 businesses, found %d" % len(BUSINESSES))

    for b in BUSINESSES:
        slug = b.get("slug", "?")
        missing = REQUIRED_KEYS - set(b.keys())
        if missing:
            err("%s: missing keys %s" % (slug, sorted(missing)))
        if not re.match(r"^[a-z0-9-]+$", slug):
            err("%s: slug must be lowercase-dash" % slug)

        for label, key in (("tagline", "tagline"), ("what", "what"),
                           ("cta", "cta"), ("area", "area")):
            check_text(slug, key, b.get(key) or "", label)
        for i, s in enumerate(b.get("services", [])):
            check_text(slug, "services[%d]" % i, s, "service")
        for i, s in enumerate(b.get("selling_points", [])):
            check_text(slug, "selling_points[%d]" % i, s, "selling point")

        phone = b.get("phone")
        if phone is not None and not PHONE_RE.match(phone):
            err("%s: phone %r not NNN-NNN-NNNN" % (slug, phone))
        email = b.get("email")
        if email and not EMAIL_RE.match(email):
            err("%s: email %r looks invalid" % (slug, email))
        site = b.get("site")
        if site and not site.startswith("https://"):
            err("%s: site %r should be https://" % (slug, site))
        for d in b.get("allowed_domains", []):
            if not DOMAIN_RE.match(d):
                err("%s: allowed domain %r looks invalid" % (slug, d))

        targets = b.get("targets", {})
        for plat in ("facebook", "instagram"):
            tid = targets.get(plat)
            if tid == "":
                err("%s: %s target is empty string (use None)" % (slug, plat))
            if tid is not None and not re.match(r"^[A-Za-z0-9_]+$", str(tid)):
                err("%s: %s target %r looks invalid" % (slug, plat, tid))

        tags = b.get("hashtags", [])
        if not (4 <= len(tags) <= 10):
            err("%s: %d hashtags, need 4-10" % (slug, len(tags)))
        for t in tags:
            if not TAG_RE.match(t):
                err("%s: hashtag %r malformed" % (slug, t))
        brand = tags[0] if tags else ""
        name_letters = re.sub(r"[^a-z]", "", b.get("name", "").lower())
        tag_letters = re.sub(r"[^a-z]", "", brand.lower())
        looks_brand = any(
            name_letters[i:i + 5] in tag_letters
            for i in range(max(0, len(name_letters) - 4)))
        if brand and not looks_brand:
            warn("%s: first hashtag %r does not look like the brand tag" %
                 (slug, brand))

        angles = b.get("angles", [])
        if len(angles) < 6:
            warn("%s: only %d angles (rotation wants 6+)" % (slug, len(angles)))
        themes = [a.get("theme") for a in angles]
        if len(themes) != len(set(themes)):
            err("%s: duplicate angle themes" % slug)
        for i, a in enumerate(angles):
            for key in ("theme", "hook", "body"):
                if not a.get(key):
                    err("%s: angle %d missing %r" % (slug, i, key))
            check_text(slug, "angles[%d].hook" % i, a.get("hook", ""),
                       "angle hook")
            check_text(slug, "angles[%d].body" % i, a.get("body", ""),
                       "angle body")
            check_text(slug, "angles[%d].theme" % i, a.get("theme", ""),
                       "angle theme")
            if a.get("format") and a["format"] not in formats_mod.FORMAT_BY_NAME:
                err("%s: angle %d unknown format %r" %
                    (slug, i, a["format"]))

        if slug not in media_gen.PALETTE:
            err("%s: no palette entry in media_gen.PALETTE" % slug)

    for t in POST_TIMES:
        if not TIME_RE.match(t):
            err("POST_TIMES: %r not HH:MM" % t)
    if len(set(POST_TIMES)) != len(POST_TIMES):
        err("POST_TIMES has duplicates")

    if errors:
        print("CONFIG INVALID: %d error(s)" % len(errors))
        for e in errors:
            print("  ERROR: %s" % e)
    if warnings:
        print("warnings: %d" % len(warnings))
        for w in warnings:
            print("  warn: %s" % w)
    if not errors and not warnings:
        print("CONFIG OK: %d businesses, all checks passed" % len(BUSINESSES))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
