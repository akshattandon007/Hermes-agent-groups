#!/usr/bin/env python3
"""
make_image.py — generate a news-card Instagram image.

Pipeline:
  1. Ask an OpenRouter image model (default google/gemini-2.5-flash-image) for a
     RELEVANT background photo (no text) from --prompt.
  2. Decode the base64 the API returns, fit it to a 1080x1350 (4:5) card.
  3. Darken the lower portion with a gradient for legibility.
  4. Overlay, with Pillow, the news-card text:
       - handle/logo (top-left)
       - kicker (centered, letter-spaced, e.g. "ECONOMICS")
       - divider line
       - headline (heavy condensed font), with --accent-words in the brand color
  5. Save the finished card to --out.

Text is drawn by Pillow, never by the image model, so every post is crisp and
identical in style.

Usage:
  python3 make_image.py \
    --prompt "sleek modern AI datacenter glowing blue servers cinematic no text" \
    --kicker "ARTIFICIAL INTELLIGENCE" \
    --headline "OpenAI Launches Its Most Powerful Model Yet" \
    --accent-words "OpenAI,Powerful" \
    --handle "YOUR AI NEWS" \
    --out /data/profiles/creator/posts/post_1.png

Key is read from OPENROUTER_API_KEY in the environment, or --key.
"""
import argparse
import base64
import json
import os
import sys
import urllib.request

CARD_W, CARD_H = 1080, 1350          # 4:5, Instagram-friendly
BRAND = (74, 176, 255)               # accent blue (like the example)
WHITE = (255, 255, 255)
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def call_image_api(prompt, model, key, base_url):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    try:
        url = data["choices"][0]["message"]["images"][0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError):
        sys.exit(f"No image in API response: {json.dumps(data)[:500]}")
    if not url.startswith("data:"):
        # plain URL fallback
        with urllib.request.urlopen(url, timeout=120) as ir:
            return ir.read()
    b64 = url.split(",", 1)[1]
    return base64.b64decode(b64)


def load_font(names, size):
    from PIL import ImageFont
    # Try bundled fonts first (Anton for headline, DejaVu as fallback everywhere).
    candidates = []
    for n in names:
        candidates.append(os.path.join(FONT_DIR, n))
    candidates += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def fit_cover(img, w, h):
    """Resize+crop image to exactly wxh (cover)."""
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new = img.resize((int(src_w * scale) + 1, int(src_h * scale) + 1))
    nw, nh = new.size
    left = (nw - w) // 2
    top = (nh - h) // 2
    return new.crop((left, top, left + w, top + h))


def wrap_text(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def draw_headline(draw, lines, font, accent_set, x, y, line_h):
    """Draw wrapped headline; words in accent_set are colored BRAND."""
    for line in lines:
        cx = x
        for i, word in enumerate(line.split()):
            token = word + (" " if i < len(line.split()) - 1 else "")
            clean = word.strip(",.!?:;").upper()
            color = BRAND if clean in accent_set else WHITE
            draw.text((cx, y), token, font=font, fill=color)
            cx += draw.textlength(token, font=font)
        y += line_h
    return y


def main():
    from PIL import Image, ImageDraw

    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--headline", required=True)
    ap.add_argument("--kicker", default="")
    ap.add_argument("--accent-words", default="")
    ap.add_argument("--handle", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="google/gemini-2.5-flash-image")
    ap.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    ap.add_argument("--key", default=os.environ.get("OPENROUTER_API_KEY", ""))
    a = ap.parse_args()
    if not a.key:
        sys.exit("No API key. Set OPENROUTER_API_KEY or pass --key.")

    # 1. background
    raw = call_image_api(a.prompt, a.model, a.key, a.base_url)
    tmp = a.out + ".bg"
    with open(tmp, "wb") as f:
        f.write(raw)
    bg = Image.open(tmp).convert("RGB")
    bg = fit_cover(bg, CARD_W, CARD_H)

    # 2. bottom gradient for legibility
    grad = Image.new("L", (1, CARD_H), 0)
    for yy in range(CARD_H):
        # transparent up top, dark toward the bottom ~55% down
        t = max(0, (yy - CARD_H * 0.35) / (CARD_H * 0.65))
        grad.putpixel((0, yy), int(230 * t))
    grad = grad.resize((CARD_W, CARD_H))
    black = Image.new("RGB", (CARD_W, CARD_H), (5, 8, 12))
    bg = Image.composite(black, bg, grad)

    draw = ImageDraw.Draw(bg)
    margin = 70
    accent_set = {w.strip().upper() for w in a.accent_words.split(",") if w.strip()}

    # 3. handle / logo top-left
    if a.handle:
        hf = load_font(["Anton-Regular.ttf"], 34)
        draw.text((margin, 55), a.handle.upper(), font=hf, fill=WHITE)

    # 4. headline (bottom-anchored), kicker + divider above it
    head_font = load_font(["Anton-Regular.ttf"], 92)
    line_h = 96
    lines = wrap_text(draw, a.headline.upper(), head_font, CARD_W - 2 * margin)
    head_block_h = line_h * len(lines)
    head_y = CARD_H - margin - head_block_h

    if a.kicker:
        kf = load_font(["Anton-Regular.ttf"], 34)
        # letter-space the kicker manually
        spaced = " ".join(list(a.kicker.upper().replace(" ", "  ")))
        kx = margin
        ky = head_y - 96
        draw.text((kx, ky), a.kicker.upper(), font=kf, fill=WHITE)
        # divider line under kicker
        draw.line([(margin, ky + 52), (CARD_W - margin, ky + 52)], fill=WHITE, width=3)

    draw_headline(draw, lines, head_font, accent_set, margin, head_y, line_h)

    bg.save(a.out, "PNG")
    try:
        os.remove(tmp)
    except OSError:
        pass
    print(json.dumps({"out": a.out, "size": os.path.getsize(a.out)}))


if __name__ == "__main__":
    main()
