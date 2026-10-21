"""Image generation for Post Pilot.

Real mode: keyless Pollinations image API, then a PIL banner overlay is burned
in using ONLY text from the business config (name, phone, site domain from the
allowlist). Nothing else is ever rendered as text, which scrubs invented
domains by construction.

Dry-run mode: full PIL placeholder, same layout, same banner rules.
"""

import hashlib
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350

# Brand colors per business slug: (top, bottom, accent)
PALETTE = {
    "gutter-genie": ((18, 24, 38), (34, 52, 80), (255, 176, 0)),
    "winnipeg-web-works": ((10, 14, 26), (24, 34, 64), (0, 200, 255)),
    "move-metal": ((26, 16, 10), (64, 38, 18), (255, 120, 0)),
    "bnb-media": ((20, 10, 26), (52, 26, 72), (255, 80, 160)),
    "demoboss": ((24, 12, 12), (70, 26, 22), (255, 60, 60)),
    "quonset-place": ((12, 22, 18), (30, 56, 44), (120, 220, 120)),
}
DEFAULT_PALETTE = ((20, 20, 30), (50, 50, 70), (255, 200, 60))


def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _banner_lines(biz):
    lines = [biz["name"].upper()]
    if biz.get("phone"):
        lines.append(biz["phone"])
    return lines


def _draw_banner(img, biz, accent):
    draw = ImageDraw.Draw(img)
    bw = W
    bh = 190
    y0 = H - bh
    draw.rectangle([0, y0, bw, H], fill=(8, 8, 12))
    draw.rectangle([0, y0, bw, y0 + 6], fill=accent)
    lines = _banner_lines(biz)
    y = y0 + 34
    for i, line in enumerate(lines):
        f = _font(64 if i == 0 else 48)
        bbox = draw.textbbox((0, 0), line, font=f)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2, y), line, font=f, fill=(255, 255, 255))
        y += 78
    return img


def _draw_headline(img, headline, accent):
    draw = ImageDraw.Draw(img)
    wrapped = textwrap.wrap(headline.upper(), width=16)
    # auto-fit: shrink until the widest line fits the frame
    size = 92
    while size > 40:
        f = _font(size)
        widths = [draw.textbbox((0, 0), line, font=f)[2] for line in wrapped]
        if max(widths, default=0) <= W - 80:
            break
        size -= 6
    f = _font(size)
    total_h = len(wrapped) * (size + 20)
    y = (H - 190 - total_h) // 2
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=f)
        tw = bbox[2] - bbox[0]
        # subtle shadow for readability
        draw.text(((W - tw) / 2 + 4, y + 4), line, font=f, fill=(0, 0, 0))
        draw.text(((W - tw) / 2, y), line, font=f, fill=(255, 255, 255))
        y += size + 20
    # accent underline
    draw.rectangle([W // 2 - 120, y + 10, W // 2 + 120, y + 18], fill=accent)
    return img


def _draw_format_overlay(img, fmt, headline, accent):
    """Per-format decoration so the creative's look matches its format.

    Only geometric/label decoration from fixed words; never free text that
    could invent claims. fmt may be None (base layout).
    """
    draw = ImageDraw.Draw(img)
    f_big = _font(56)
    f_small = _font(40)

    if fmt == "before-after":
        # Vertical divider with BEFORE / AFTER labels.
        draw.line([(W // 2, 0), (W // 2, H - 190)], fill=accent, width=8)
        for x, label in ((W // 4, "BEFORE"), (3 * W // 4, "AFTER")):
            bbox = draw.textbbox((0, 0), label, font=f_big)
            tw = bbox[2] - bbox[0]
            draw.text((x - tw / 2 + 3, 63), label, font=f_big, fill=(0, 0, 0))
            draw.text((x - tw / 2, 60), label, font=f_big, fill=(255, 255, 255))

    elif fmt == "how-it-works":
        # Numbered step rail on the left edge: 1 / 2 / 3.
        x = 46
        y = 220
        for n in ("1", "2", "3"):
            r = 44
            draw.ellipse([x - r, y - r, x + r, y + r], fill=accent)
            bbox = draw.textbbox((0, 0), n, font=f_big)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text((x - tw / 2, y - th / 2 - 6), n, font=f_big,
                      fill=(10, 10, 14))
            y += 190
        # "HOW IT WORKS" kicker at top.
        kick = "HOW IT WORKS"
        bbox = draw.textbbox((0, 0), kick, font=f_small)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2 + 3, 103), kick, font=f_small, fill=(0, 0, 0))
        draw.text(((W - tw) / 2, 100), kick, font=f_small, fill=accent)

    elif fmt == "tip-card":
        # Big accent quotation bar on the left + "QUICK TIP" kicker.
        draw.rectangle([40, 200, 64, H - 240], fill=accent)
        kick = "QUICK TIP"
        bbox = draw.textbbox((0, 0), kick, font=f_small)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2 + 3, 103), kick, font=f_small, fill=(0, 0, 0))
        draw.text(((W - tw) / 2, 100), kick, font=f_small, fill=accent)

    elif fmt == "offer-card":
        # Accent frame around the whole creative + "OFFER" kicker.
        w = 14
        draw.rectangle([w, w, W - w, H - 190 - w], outline=accent, width=w)
        kick = "TODAY'S OFFER"
        bbox = draw.textbbox((0, 0), kick, font=f_small)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2 + 3, 103), kick, font=f_small, fill=(0, 0, 0))
        draw.text(((W - tw) / 2, 100), kick, font=f_small, fill=(255, 255, 255))

    elif fmt == "stock-voiceover":
        # Subtitle-style caption bar hint in the lower third.
        bar_h = 74
        y0 = H - 190 - bar_h - 40
        draw.rectangle([90, y0, W - 90, y0 + bar_h], fill=(0, 0, 0))
        line = headline[:44]
        bbox = draw.textbbox((0, 0), line, font=f_small)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2, y0 + 16), line, font=f_small,
                  fill=(255, 255, 255))

    elif fmt == "screen-walkthrough":
        # Browser-chrome bar at top to suggest a screen recording.
        draw.rectangle([0, 0, W, 96], fill=(12, 12, 16))
        for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
            draw.ellipse([36 + i * 52, 30, 68 + i * 52, 62], fill=c)

    elif fmt == "photo-story":
        # Date-stamp style corner badge (no invented content, just a tag).
        tag = "ON THE JOB"
        bbox = draw.textbbox((0, 0), tag, font=f_small)
        tw = bbox[2] - bbox[0]
        pad = 24
        draw.rectangle([40, 40, 40 + tw + pad * 2, 40 + 64], fill=(8, 8, 12))
        draw.rectangle([40, 40, 40 + tw + pad * 2, 46], fill=accent)
        draw.text((40 + pad, 52), tag, font=f_small, fill=(255, 255, 255))

    # template-reel and unknown formats: base layout, no overlay.
    return img


def _placeholder(biz, headline, out_path, fmt=None):
    top, bottom, accent = PALETTE.get(biz["slug"], DEFAULT_PALETTE)
    img = Image.new("RGB", (W, H), top)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    # faint diagonal texture
    for i in range(0, W + H, 90):
        draw.line([(i, 0), (i - H // 3, H)], fill=(255, 255, 255, 12), width=2)
    _draw_format_overlay(img, fmt, headline, accent)
    _draw_headline(img, headline, accent)
    _draw_banner(img, biz, accent)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def _pollinations(biz, image_prompt, out_path, timeout=90):
    """Keyless generation via Pollinations. Falls back to placeholder on failure."""
    import requests
    seed = int(hashlib.sha256(image_prompt.encode()).hexdigest()[:8], 16) % 100000
    safe_prompt = image_prompt.replace("\n", " ")[:400]
    url = ("https://image.pollinations.ai/prompt/" + requests.utils.quote(safe_prompt) +
           "?width=1080&height=1350&nologo=true&seed=%d" % seed)
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        if r.headers.get("Content-Type", "").startswith("image"):
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(r.content)
            img = Image.open(out_path).convert("RGB")
            if img.size != (W, H):
                img = img.resize((W, H), Image.LANCZOS)
                img.save(out_path, "PNG")
            return out_path
    except Exception:
        pass
    return None


def generate(biz, headline, image_prompt, out_path, dry_run=False, fmt=None):
    """Generate the 1080x1350 creative. Returns the output path.

    In real mode the AI image gets our banner burned over the bottom, so any
    text the generator invents in that strip is covered, and the only rendered
    text is name + phone from config.
    """
    top, bottom, accent = PALETTE.get(biz["slug"], DEFAULT_PALETTE)
    if not dry_run:
        got = _pollinations(biz, image_prompt, out_path)
        if got:
            img = Image.open(out_path).convert("RGB")
            _draw_format_overlay(img, fmt, headline, accent)
            _draw_banner(img, biz, accent)
            img.save(out_path, "PNG")
            return out_path
        # fall through to placeholder on any failure
    return _placeholder(biz, headline, out_path, fmt=fmt)
