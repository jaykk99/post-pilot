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
    wrapped = textwrap.wrap(headline.upper(), width=18)
    f = _font(92)
    total_h = len(wrapped) * 112
    y = (H - 190 - total_h) // 2
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=f)
        tw = bbox[2] - bbox[0]
        # subtle shadow for readability
        draw.text(((W - tw) / 2 + 4, y + 4), line, font=f, fill=(0, 0, 0))
        draw.text(((W - tw) / 2, y), line, font=f, fill=(255, 255, 255))
        y += 112
    # accent underline
    draw.rectangle([W // 2 - 120, y + 10, W // 2 + 120, y + 18], fill=accent)
    return img


def _placeholder(biz, headline, out_path):
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


def generate(biz, headline, image_prompt, out_path, dry_run=False):
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
            _draw_banner(img, biz, accent)
            img.save(out_path, "PNG")
            return out_path
        # fall through to placeholder on any failure
    return _placeholder(biz, headline, out_path)
