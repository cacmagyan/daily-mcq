"""QT puzzle reel (CA Foundation Quantitative Aptitude), in the "trap" format:

hook (the obvious answer) -> "that is the trap" -> the question card builds up -> options appear ->
pause countdown -> the right option turns green -> step cards while a simple scene acts out each step ->
the shortcut card -> "your turn" with a follow-up question.

One voice reads every line; the spoken word shows big near the bottom (the current word in yellow),
cards sit at the top and a scene in the middle. Everything is drawn with Pillow frame by frame and piped
to ffmpeg, so it runs on a plain GitHub runner.

Script (dict, usually from qtpuzzle.write):
  theme: green | purple | navy | teal | maroon
  badge: {"tag": "ASKED IN", "text": "CA FOUNDATION JUNE 2024 · QT Q41"}
  question: text with **bold** key phrases;  options: [4 strings];  answer: index 0-3
  scene: the first scene state (see SCENES below)
  lines: [{"say": "...", "card": {...}, "scene": {...}}]   card kinds:
     hook {small, big} · trap {small, big, sub} · question {options: true} · pause · reveal
     step {title, rows} · shortcut {title, rows} · your_turn {rows}
  A line's "scene" replaces keys of the current scene (the change animates).
"""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import ROOT

W, H, FPS = 1080, 1920, 30
SR = 24000
FONTS = ROOT / "assets" / "fonts"
LEAD, GAP, TAIL = 0.3, 0.18, 1.6
COUNTDOWN = 3.2                       # silent seconds after the "pause" line
ANIM = 0.55                           # seconds a scene change takes

THEMES = {
    "green":  ((24, 92, 46), (66, 140, 58)),
    "purple": ((30, 22, 54), (66, 50, 104)),
    "navy":   ((14, 26, 56), (38, 62, 112)),
    "teal":   ((10, 60, 66), (28, 110, 112)),
    "maroon": ((62, 18, 28), (118, 42, 52)),
}
YEL, ORANGE, WHITE = (255, 200, 61), (247, 160, 50), (255, 255, 255)
CREAM, INK, SOFT = (252, 248, 236), (30, 34, 44), (110, 112, 120)
GREEN_OK, RED_BAD = (76, 196, 120), (238, 98, 88)
DARK_CARD = (24, 30, 30, 232)
PALETTE = [(220, 70, 60), (60, 120, 220), (60, 170, 90), (240, 170, 40), (150, 90, 200), (60, 190, 200)]


class QTError(RuntimeError):
    pass


_FCACHE: dict = {}


def font(name: str, size: int):
    key = (name, size)
    if key not in _FCACHE:
        files = {"xb": "Poppins-ExtraBold.ttf", "b": "Poppins-Bold.ttf", "sb": "Poppins-SemiBold.ttf",
                 "ib": "Inter-Bold.otf", "im": "Inter-Medium.otf", "isb": "Inter-SemiBold.otf"}
        _FCACHE[key] = ImageFont.truetype(str(FONTS / files[name]), size)
    return _FCACHE[key]


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def lerp(a, b, k):
    return a + (b - a) * k


# ── rich text: **bold** phrases get a highlighter mark ──────
def _runs(text: str) -> list[tuple[str, bool]]:
    out = []
    for i, part in enumerate(re.split(r"\*\*", text)):
        for j, w in enumerate(part.split()):
            if j == 0 and out and not part[:1].isspace() and re.fullmatch(r"[,.;:!?)]+\S*", w):
                out[-1] = (out[-1][0] + w, out[-1][1])
                continue
            out.append((w, i % 2 == 1))
    return out


def rich_lines(text: str, width: int, size: int, bold_font="ib", plain_font="im"):
    """[(line [(word, bold, x)], ...)] wrapped to width."""
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines, cur, x = [], [], 0
    space = d.textlength(" ", font=font(plain_font, size))
    for w, b in _runs(text):
        f = font(bold_font if b else plain_font, size)
        wl = d.textlength(w, font=f)
        if cur and x + wl > width:
            lines.append(cur)
            cur, x = [], 0
        cur.append((w, b, x))
        x += wl + space
    if cur:
        lines.append(cur)
    return lines


def draw_rich(d: ImageDraw.ImageDraw, text, x0, y0, width, size, color, mark=(255, 214, 102),
              bold_color=None, line_h=1.32, bold_font="ib", plain_font="im") -> int:
    y = y0
    for line in rich_lines(text, width, size, bold_font, plain_font):
        for w, b, x in line:
            f = font(bold_font if b else plain_font, size)
            if b and mark:
                wl = d.textlength(w, font=f)
                d.rectangle((x0 + x - 2, y + size * 0.62, x0 + x + wl + 2, y + size * 1.08), fill=mark)
            d.text((x0 + x, y), w, font=f, fill=(bold_color or color) if b else color)
        y += int(size * line_h)
    return y


# ── static layers ───────────────────────────────────────────
def background(theme: str) -> Image.Image:
    top, bottom = THEMES.get(theme, THEMES["green"])
    g = Image.new("RGB", (1, H))
    for y in range(H):
        k = y / H
        mid = 1 - abs(k - 0.45) * 2
        c = tuple(int(lerp(top[i], bottom[i], max(0, mid)) ) for i in range(3))
        g.putpixel((0, y), c)
    bg = g.resize((W, H))
    vign = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vign).ellipse((-W * 0.3, -H * 0.1, W * 1.3, H * 1.1), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(160))
    dark = Image.new("RGB", (W, H), tuple(int(c * 0.55) for c in top))
    return Image.composite(bg, dark, vign)


def chrome(badge: dict, handle: str) -> Image.Image:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    tag, text = (badge.get("tag") or "").upper(), badge.get("text") or ""
    x, y = 36, 40
    if tag:
        tw = d.textlength(tag, font=font("ib", 22))
        d.rounded_rectangle((x, y, x + tw + 24, y + 40), 8, fill=ORANGE)
        d.text((x + 12, y + 8), tag, font=font("ib", 22), fill=INK)
        x += tw + 36
    tw = d.textlength(text, font=font("ib", 26))
    d.rounded_rectangle((x - 8, y - 2, x + tw + 16, y + 42), 10, fill=(0, 0, 0, 120))
    d.text((x + 4, y + 6), text, font=font("ib", 26), fill=WHITE)
    if handle:
        f = font("isb", 24)
        hw = d.textlength(handle, font=f)
        d.rounded_rectangle((W - hw - 64, H - 92, W - 28, H - 48), 22, fill=(0, 0, 0, 110))
        d.text((W - hw - 46, H - 84), handle, font=f, fill=(235, 235, 235))
    return im


# ── cards (top) ─────────────────────────────────────────────
CARD_X, CARD_Y, CARD_W = 40, 108, W - 80


def _card_box(h, fill, radius=22):
    im = Image.new("RGBA", (W, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, h + 40), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((CARD_X + 6, 14, CARD_X + CARD_W + 6, h + 14), radius, fill=(0, 0, 0, 90))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    ImageDraw.Draw(im).rounded_rectangle((CARD_X, 4, CARD_X + CARD_W, h + 4), radius, fill=fill)
    return im


def card_small(small: str, big: str, sub: str = "", bad=False) -> Image.Image:
    """Hook / trap card: small caps line, a big line, an optional red 'that is the trap'."""
    fb = font("xb", 72)
    d0 = ImageDraw.Draw(Image.new("L", (1, 1)))
    big_w = d0.textlength(big, font=fb)
    size = 72 if big_w < CARD_W - 120 else max(44, int(72 * (CARD_W - 120) / big_w))
    h = 120 + size + (50 if sub else 0)
    w = min(CARD_W, int(d0.textlength(big, font=font("xb", size))) + 140)
    im = Image.new("RGBA", (W, h + 40), (0, 0, 0, 0))
    x0 = (W - w) // 2
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x0, 4, x0 + w, h + 4), 22, fill=DARK_CARD, outline=(255, 255, 255, 50), width=2)
    d.text((W // 2, 30), small.upper(), font=font("ib", 24), fill=(205, 210, 205), anchor="mt")
    col = (255, 150, 140) if bad else WHITE
    d.text((W // 2, 70), big, font=font("xb", size), fill=col, anchor="mt")
    if sub:
        d.text((W // 2, 82 + size), sub, font=font("isb", 26), fill=(230, 230, 230), anchor="mt")
    return im


def card_question(q: str, options: list[str], shown: int, reveal: int | None, header: str) -> Image.Image:
    inner = CARD_W - 64
    d0 = ImageDraw.Draw(Image.new("L", (1, 1)))
    qh = len(rich_lines(q, inner, 40)) * int(40 * 1.32)
    rows = 2 if shown > 2 or reveal is not None else (1 if shown else 0)
    h = 30 + 34 + qh + 18 + rows * 78 + 24
    im = _card_box(h, CREAM)
    d = ImageDraw.Draw(im)
    x0, y = CARD_X + 32, 30
    d.text((x0, y), header.upper(), font=font("ib", 20), fill=SOFT)
    d.line((x0, y + 30, CARD_X + CARD_W - 32, y + 30), fill=(220, 214, 196), width=2)
    y = draw_rich(d, q, x0, y + 44, inner, 40, INK)
    y += 14
    cw = (inner - 20) // 2
    for i, opt in enumerate(options):
        if i >= shown and reveal is None:
            continue
        cx = x0 + (i % 2) * (cw + 20)
        cy = y + (i // 2) * 78
        fill, tcol = (240, 236, 222), INK
        if reveal is not None:
            if i == reveal:
                fill, tcol = GREEN_OK, WHITE
            else:
                tcol = (170, 168, 160)
        d.rounded_rectangle((cx, cy, cx + cw, cy + 64), 12, fill=fill)
        label = f"({'abcd'[i]}) {opt}" + ("  ✓" if reveal == i else "")
        f = font("ib", 34)
        while d.textlength(label, font=f) > cw - 30 and f.size > 22:
            f = font("ib", f.size - 2)
        d.text((cx + 18, cy + 32), label, font=f, fill=tcol, anchor="lm")
    return im


def card_rows(title: str, rows: list[str], dark=True, footer: str = "") -> Image.Image:
    inner = CARD_W - 64
    size = 42
    hs = [len(rich_lines(r, inner, size, "xb", "ib")) * int(size * 1.3) for r in rows]
    h = 34 + 30 + 16 + sum(hs) + len(rows) * 10 + (56 if footer else 0) + 26
    h = max(h, 150)
    im = _card_box(h, DARK_CARD if dark else CREAM)
    d = ImageDraw.Draw(im)
    x0, y = CARD_X + 32, 34
    d.text((x0, y), title.upper(), font=font("ib", 22), fill=YEL if dark else ORANGE)
    if not dark:
        d.line((x0, y + 32, CARD_X + CARD_W - 32, y + 32), fill=(220, 214, 196), width=2)
    y += 46
    for i, r in enumerate(rows):
        last = i == len(rows) - 1
        col = WHITE if dark else INK
        bc = (YEL if dark else (196, 110, 20)) if last and len(rows) > 1 else None
        y = draw_rich(d, r, x0, y, inner, size, col, mark=None, bold_color=bc or (YEL if dark else (196, 110, 20)),
                      line_h=1.3, bold_font="xb", plain_font="ib") + 10
    if footer:
        d.text((x0, y + 4), footer, font=font("ib", 34), fill=YEL if dark else ORANGE)
    return im


# ── scenes (middle) ─────────────────────────────────────────
SCENE_Y0, SCENE_Y1 = 660, 1250


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3])


def _icon(d, kind, cx, base, s, color, lit=False):
    """A simple object standing on `base`: bell, pole, tree, coin, person, box, dot."""
    c = color
    if kind == "bell":
        d.line((cx, base, cx, base - s * 1.1), fill=(40, 40, 46), width=max(3, int(s * 0.08)))
        d.ellipse((cx - s * 0.45, base + 2, cx + s * 0.45, base + s * 0.16), fill=(18, 18, 22))
        top = base - s * 1.1
        d.polygon([(cx, top - s * 0.75), (cx - s * 0.42, top), (cx + s * 0.42, top)],
                  fill=(255, 214, 90) if lit else (214, 168, 52))
        d.ellipse((cx - s * 0.44, top - s * 0.08, cx + s * 0.44, top + s * 0.1), fill=(170, 128, 30))
    elif kind == "tree":
        d.rectangle((cx - s * 0.08, base - s * 0.5, cx + s * 0.08, base), fill=(110, 72, 40))
        d.ellipse((cx - s * 0.4, base - s * 1.3, cx + s * 0.4, base - s * 0.4), fill=_shade(c, 0.9) if lit else (52, 150, 70))
    elif kind == "pole":
        d.rectangle((cx - s * 0.07, base - s * 1.3, cx + s * 0.07, base), fill=(235, 235, 240) if lit else (190, 190, 200))
        d.ellipse((cx - s * 0.16, base - s * 1.42, cx + s * 0.16, base - s * 1.18), fill=YEL if lit else (210, 70, 60))
    elif kind == "coin":
        d.ellipse((cx - s * 0.42, base - s * 0.84, cx + s * 0.42, base), fill=(250, 200, 70), outline=(170, 120, 20), width=4)
    elif kind == "person":
        d.ellipse((cx - s * 0.22, base - s * 1.3, cx + s * 0.22, base - s * 0.86), fill=(240, 200, 160))
        d.rounded_rectangle((cx - s * 0.32, base - s * 0.86, cx + s * 0.32, base), int(s * 0.18), fill=c)
    elif kind == "box":
        d.rounded_rectangle((cx - s * 0.4, base - s * 0.8, cx + s * 0.4, base), 10, fill=c)
    else:
        d.ellipse((cx - s * 0.25, base - s * 0.5, cx + s * 0.25, base), fill=c)


def _pill(d, cx, cy, text, fill=(255, 255, 255), color=INK, size=26, anchor="mm"):
    f = font("ib", size)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((cx - tw / 2 - 14, cy - size * 0.75, cx + tw / 2 + 14, cy + size * 0.75), int(size * 0.75), fill=fill)
    d.text((cx, cy), text, font=f, fill=color, anchor=anchor)


def scene_row(d, s, k_prev, prev):
    """A row of counted items with gap boxes between them: clocks striking, trees, poles, terms of a series."""
    n = int(s.get("n", 4))
    pn = int(prev.get("n", n)) if prev else n
    nshow = lerp(pn, n, k_prev)
    kind = s.get("item", "dot")
    lit = s.get("lit")                         # int index lit, or "all"
    span = W - 240
    count = max(n, pn, 1)
    step = span / max(count - 1, 1) if count > 1 else 0
    s_size = max(26, min(140, step * 0.62)) if count > 1 else 140
    base = SCENE_Y0 + 300
    d.polygon([(0, base + 40), (W, base + 10), (W, base + 220), (0, base + 260)], fill=(0, 0, 0, 50))
    x_at = lambda i: 120 + i * step if count > 1 else W / 2
    for i in range(count):
        a = max(0.0, min(1.0, nshow - i))
        if a <= 0:
            continue
        cx = x_at(i)
        b = base + (1 - ease(a)) * 40
        on = lit == "all" or lit == i or (isinstance(lit, list) and i in lit)
        _icon(d, kind, cx, b, s_size, PALETTE[i % len(PALETTE)], on)
        if s.get("numbers", True):
            top = b - s_size * 2.1
            f = font("ib", int(max(18, min(30, s_size * 0.38))))
            r = max(16, s_size * 0.26)
            d.ellipse((cx - r, top - r, cx + r, top + r), fill=CREAM)
            d.text((cx, top), str(i + 1), font=f, fill=INK, anchor="mm")
    gaps = s.get("gaps")                        # list of labels, one per gap (n-1)
    if gaps:
        gw = step * 0.74
        for i in range(min(len(gaps), count - 1)):
            a = max(0.0, min(1.0, nshow - i - 1))
            if a <= 0:
                continue
            cx = (x_at(i) + x_at(i + 1)) / 2
            y = base + 30
            h = max(40, min(86, gw * 0.9))
            d.rounded_rectangle((cx - gw / 2, y, cx + gw / 2, y + h), 8, fill=(52, 180, 170), outline=(20, 90, 84), width=3)
            lab = str(gaps[i])
            f = font("ib", int(max(16, min(30, gw * 0.3))))
            d.text((cx, y + h / 2), lab, font=f, fill=(12, 40, 38), anchor="mm")
    if s.get("note"):
        _pill(d, W / 2, base + 170, s["note"], size=32)


def scene_track(d, s, k, prev):
    """A race track: runners at distances, a finish line, gap labels."""
    L = float(s.get("length", 100))
    y0, y1 = SCENE_Y0 + 60, SCENE_Y0 + 420
    d.polygon([(0, y0 + 60), (W, y0 - 20), (W, y1 - 40), (0, y1 + 40)], fill=(196, 74, 56))
    for i in range(1, 4):
        t = i / 4
        d.line((0, lerp(y0 + 60, y1 + 40, t), W, lerp(y0 - 20, y1 - 40, t)), fill=(240, 220, 210), width=3)
    pos_all = [float(r.get("pos", 0)) for r in s.get("runners", [])] or [0.0]
    v0 = float(s.get("view_from", max(0.0, min(pos_all) - 0.3 * L) if min(pos_all) > 0.4 * L else 0.0))
    x_of = lambda m: 80 + (W - 220) * (m - v0) / ((L - v0) or 1)
    fx = x_of(L)
    d.line((fx, y0 - 30, fx - 40, y1 + 10), fill=(255, 236, 160), width=10)
    _pill(d, fx - 30, y1 + 50, f"FINISH · {s.get('unit_label', str(int(L)) + ' m')}", fill=YEL, size=24)
    runners = s.get("runners", [])
    pr = {r["name"]: r for r in (prev or {}).get("runners", [])}
    for j, r in enumerate(runners):
        p0 = pr.get(r["name"], r).get("pos", 0)
        pos = lerp(float(p0), float(r.get("pos", 0)), k)
        lane = (j + 0.5) / max(len(runners), 1)
        x = x_of(pos) - lane * 40
        y = lerp(y0 + 40, y1 + 10, lane)
        col = PALETTE[j % len(PALETTE)]
        d.ellipse((x - 34, y - 12, x + 34, y + 12), fill=(0, 0, 0, 70))
        d.rounded_rectangle((x - 22, y - 92, x + 22, y), 18, fill=col)
        d.ellipse((x - 20, y - 132, x + 20, y - 92), fill=(240, 205, 165))
        _pill(d, x, y - 160, r["name"], fill=CREAM, size=24)
        if r.get("label"):
            _pill(d, x, y + 34, r["label"], fill=(30, 30, 30), color=WHITE, size=22)
    if s.get("note"):
        _pill(d, W / 2, y1 + 110, s["note"], size=32)


def scene_bars(d, s, k, prev):
    """Bars made of stacked, labelled segments (principal + interest, frequencies, index numbers)."""
    bars = s.get("bars", [])
    pb = {b["label"]: b for b in (prev or {}).get("bars", [])}
    mx = float(s.get("max") or max([sum(g["v"] for g in b["segments"]) for b in bars] + [1]))
    n = max(len(bars), 1)
    bw = min(220, (W - 160) / n * 0.62)
    base, top = SCENE_Y1 - 40, SCENE_Y0 + 20
    d.line((60, base, W - 60, base), fill=(255, 255, 255, 160), width=4)
    for i, b in enumerate(bars):
        cx = 80 + (W - 160) * (i + 0.5) / n
        y = base
        old = pb.get(b["label"])
        oldsegs = old["segments"] if old else []
        for j, g in enumerate(b["segments"]):
            v0 = oldsegs[j]["v"] if j < len(oldsegs) else 0
            v = lerp(float(v0), float(g["v"]), k)
            hpx = (base - top) * v / mx
            if hpx < 1:
                continue
            col = tuple(g["color"]) if isinstance(g.get("color"), list) else PALETTE[[1, 3, 2, 0, 4][j % 5]]
            d.rounded_rectangle((cx - bw / 2, y - hpx, cx + bw / 2, y), 8, fill=col, outline=_shade(col, 0.6), width=3)
            if g.get("label") and hpx > 40:
                f = font("ib", 28 if hpx > 60 else 22)
                d.text((cx, y - hpx / 2), str(g["label"]), font=f, fill=WHITE, anchor="mm")
            y -= hpx
        d.text((cx, base + 34), b["label"], font=font("ib", 30), fill=WHITE, anchor="mm")
        if b.get("top"):
            _pill(d, cx, y - 36, b["top"], size=26)
    if s.get("note"):
        _pill(d, W / 2, SCENE_Y1 + 70, s["note"], size=32)


def scene_line(d, s, k, prev):
    """A number line with marked points and jumps (series, ratios, inequalities)."""
    a, b = float(s.get("from", 0)), float(s.get("to", 10))
    y = (SCENE_Y0 + SCENE_Y1) / 2
    x_of = lambda v: 90 + (W - 180) * (v - a) / ((b - a) or 1)
    d.line((60, y, W - 60, y), fill=WHITE, width=6)
    step = float(s.get("tick", max(1.0, (b - a) / 10)))
    v = a
    while v <= b + 1e-9:
        x = x_of(v)
        d.line((x, y - 16, x, y + 16), fill=WHITE, width=4)
        d.text((x, y + 44), (str(int(v)) if float(v).is_integer() else f"{v:g}"), font=font("ib", 26), fill=(230, 230, 230), anchor="mm")
        v += step
    for j, jp in enumerate(s.get("jumps", [])):
        x0, x1 = x_of(float(jp["from"])), x_of(float(jp["to"]))
        kk = 1.0 if j < len(s.get("jumps", [])) - 1 or not prev or len(prev.get("jumps", [])) > j else k
        xe = lerp(x0, x1, kk)
        hgt = 90
        pts = [(lerp(x0, xe, t / 20), y - 10 - math.sin(math.pi * t / 20 * (kk if kk else 1)) * hgt) for t in range(21)]
        d.line(pts, fill=YEL, width=6)
        if jp.get("label") and kk > 0.6:
            _pill(d, (x0 + x1) / 2, y - hgt - 40, jp["label"], fill=YEL, size=24)
    for p in s.get("points", []):
        x = x_of(float(p["at"]))
        col = GREEN_OK if p.get("good") else (RED_BAD if p.get("bad") else ORANGE)
        d.ellipse((x - 18, y - 18, x + 18, y + 18), fill=col, outline=WHITE, width=4)
        if p.get("label"):
            _pill(d, x, y + 100, p["label"], size=26)
    if s.get("note"):
        _pill(d, W / 2, SCENE_Y1 - 10, s["note"], size=32)


def scene_board(d, s, k, prev):
    """A chalk-board line or two of working (the fallback for algebra, logs, calculus)."""
    lines = s.get("lines", [])
    y = SCENE_Y0 + 80
    d.rounded_rectangle((70, SCENE_Y0, W - 70, SCENE_Y1 - 20), 26, fill=(16, 30, 26, 150), outline=(255, 255, 255, 60), width=3)
    n_prev = len((prev or {}).get("lines", []))
    for i, ln in enumerate(lines):
        a = 1.0 if i < n_prev else k
        f = font("xb", 64 if len(ln) < 18 else 50 if len(ln) < 26 else 40)
        col = YEL if i == len(lines) - 1 else WHITE
        col = tuple(int(lerp(40, c, a)) for c in col)
        d.text((W / 2, y + (1 - a) * 20), ln, font=f, fill=col, anchor="mt")
        y += f.size + 40


def draw_counters(d, s, k, prev):
    """Big number tiles that count up ("FROM THE TOP 9"), above the scene."""
    tiles = s.get("counters") or []
    if not tiles:
        return
    old = {c["label"]: c for c in (prev or {}).get("counters", [])}
    tw, th, gap = 300, 150, 30
    x = (W - (len(tiles) * tw + (len(tiles) - 1) * gap)) / 2
    y = SCENE_Y0 - 10
    for i, c in enumerate(tiles):
        v0 = old.get(c["label"], {}).get("value", 0)
        val = c.get("value", 0)
        try:
            shown = round(lerp(float(v0), float(val), k)) if float(val).is_integer() else lerp(float(v0), float(val), k)
            shown = f"{shown:g}" if isinstance(shown, float) else str(shown)
        except (TypeError, ValueError):
            shown = str(val)
        col = PALETTE[[1, 2, 3, 0][i % 4]]
        d.rounded_rectangle((x, y, x + tw, y + th), 18, fill=(20, 26, 30, 235), outline=(*col, 255), width=4)
        d.text((x + 22, y + 18), c["label"].upper(), font=font("ib", 20), fill=(200, 205, 210))
        d.text((x + 22, y + 46), shown, font=font("xb", 80), fill=_shade(col, 1.25))
        x += tw + gap


SCENES = {"row": scene_row, "track": scene_track, "bars": scene_bars, "line": scene_line, "board": scene_board}


def draw_scene(state: dict, prev: dict | None, k: float) -> Image.Image:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fn = SCENES.get(state.get("type", "board"), scene_board)
    if prev and prev.get("type") != state.get("type"):
        prev = None
    d = ImageDraw.Draw(im, "RGBA")
    if state.get("counters") and state.get("type") in ("bars", "board", "line", "track"):
        sub = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fn(ImageDraw.Draw(sub, "RGBA"), state, ease(k), prev)
        sub = sub.crop((0, 0, W, H - 170))
        im.alpha_composite(sub, (0, 170))
    else:
        fn(d, state, ease(k), prev)
    draw_counters(d, state, ease(k), prev)
    return im


# ── captions (bottom) ───────────────────────────────────────
CAP_Y = 1430


def caption(words: list[str], current: int) -> Image.Image:
    im = Image.new("RGBA", (W, 260), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font("xb", 76)
    text = " ".join(words)
    while d.textlength(text, font=f) > W - 120 and f.size > 44:
        f = font("xb", f.size - 4)
    x = (W - d.textlength(text, font=f)) / 2
    for i, w in enumerate(words):
        col = YEL if i == current and re.search(r"[\d₹%]", w) else WHITE
        if i > current:
            col = (255, 255, 255, 110)
        d.text((x, 90), w, font=f, fill=col, stroke_width=6, stroke_fill=(0, 0, 0, 170))
        x += d.textlength(w + " ", font=f)
    return im


def phrases(words: list[tuple[str, float, float]], size: int = 3):
    """Group caption words into short phrases (cut at punctuation)."""
    out, cur = [], []
    for w, a, b in words:
        cur.append((w, a, b))
        if len(cur) >= size or re.search(r"[,.!?:;]$", w):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


# ── timeline ────────────────────────────────────────────────
def _clean(w: str) -> str:
    return re.sub(r"^[\"“(]+|[\"”),.:;]+$", "", w)


def estimate_words(say: str, dur: float):
    ws = say.split()
    weights = [max(2, len(re.sub(r"\W", "", w))) + (4 if re.search(r"[,.!?:;]$", w) else 0) for w in ws]
    tot, t, out = sum(weights) or 1, 0.0, []
    for w, k in zip(ws, weights):
        dd = dur * k / tot
        out.append((w, t, t + dd))
        t += dd
    return out


def build(script: dict, voice_lines: list[tuple[object, float, list]]):
    """Timeline: for each line its start, duration, words; pauses get a silent countdown after them."""
    t = LEAD
    events = []
    for ln, (audio, dur, words) in zip(script["lines"], voice_lines):
        events.append({"line": ln, "start": t, "dur": dur, "words": words, "audio": audio})
        t += dur + GAP
        if (ln.get("card") or {}).get("kind") == "pause":
            events[-1]["countdown"] = (t, t + COUNTDOWN)
            t += COUNTDOWN
    return events, t + TAIL


def _card_for(ev, t, script, state):
    c = ev["line"].get("card") or {}
    kind = c.get("kind")
    hdr = script.get("header") or (script.get("badge") or {}).get("text", "")
    if kind == "hook":
        return ("hook", c.get("small", ""), c.get("big", "")), lambda: card_small(c.get("small", ""), c.get("big", ""))
    if kind == "trap":
        return ("trap", c.get("big")), lambda: card_small(c.get("small", ""), c.get("big", ""), c.get("sub", "that is the trap"), bad=True)
    if kind in ("question", "pause", "reveal"):
        if kind == "question" and c.get("options"):
            frac = (t - ev["start"]) / max(ev["dur"], 0.1)
            state["shown"] = max(state.get("shown", 0), min(4, int(frac * 4.4) + (1 if frac > 0.02 else 0)))
        if kind in ("pause",):
            state["shown"] = 4
        rev = script["answer"] if kind == "reveal" else None
        if rev is not None:
            state["shown"] = 4
        shown = state.get("shown", 0)
        key = ("q", shown, rev)
        return key, lambda: card_question(script["question"], script["options"], shown, rev, hdr)
    if kind in ("step", "shortcut", "your_turn"):
        rows = c.get("rows", [])
        frac = (t - ev["start"]) / max(ev["dur"], 0.1)
        nrow = len(rows) if c.get("all") else max(1, min(len(rows), int(frac * len(rows) * 1.15) + 1))
        title = c.get("title") or {"shortcut": "THE SHORTCUT", "your_turn": "YOUR TURN"}.get(kind, "")
        footer = "Comment your answer below" if kind == "your_turn" and nrow == len(rows) else ""
        key = (kind, title, tuple(rows[:nrow]), footer)
        return key, lambda: card_rows(title, rows[:nrow], dark=(kind != "shortcut"), footer=footer)
    return None, None


def render(script: dict, out: Path, cover: Path | None = None, voice: str = "am_michael", speed: float = 1.08,
           handle: str = "", silent: bool = False) -> dict:
    """Make the reel. silent=True skips the voice (timing estimated) for quick previews."""
    import numpy as np

    from .cartoon_video import spoken_text, tokens, word_times
    from .video import ffmpeg_path

    vl = []
    v = None
    if not silent:
        from .kokoro import Voice
        v = Voice()
    for ln in script["lines"]:
        say = ln["say"]
        if silent:
            n = len(say.split())
            dur = max(1.2, n / 2.7 + 0.25)
            vl.append((None, dur, estimate_words(re.sub(r"\{([^|}]+)\|[^}]+\}", r"\1", say), dur)))
            continue
        audio = v.synth(spoken_text(say), voice, speed)
        words = word_times(say, audio)
        vl.append((audio, len(audio) / SR, words))
    events, total = build(script, vl)

    # sound: voice + soft bed + ticks + pops + ding
    n = int((total + 0.5) * SR)
    track = np.zeros(n, np.float32)
    tt = np.arange(n) / SR
    bed = 0.018 * (np.sin(2 * np.pi * 110 * tt) + 0.6 * np.sin(2 * np.pi * 164.8 * tt)) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.25 * tt))
    track += bed.astype(np.float32)

    def add(sig, at):
        s = int(at * SR)
        seg = sig[: max(0, n - s)]
        track[s:s + len(seg)] += seg

    def tone(f, d, amp, decay=8.0):
        x = np.arange(int(d * SR)) / SR
        return (amp * np.sin(2 * np.pi * f * x) * np.exp(-x * decay)).astype(np.float32)

    for ev in events:
        if ev["audio"] is not None:
            add(np.asarray(ev["audio"], np.float32) * 0.95, ev["start"])
        kind = (ev["line"].get("card") or {}).get("kind")
        add(tone(660, 0.12, 0.12, 30), ev["start"])
        if kind == "reveal":
            add(tone(880, 0.6, 0.25, 5) + tone(1320, 0.6, 0.12, 6), ev["start"])
        if kind == "trap":
            add(tone(220, 0.4, 0.3, 6), ev["start"])
        if ev.get("countdown"):
            a, b = ev["countdown"]
            for i in range(3):
                add(tone(1000, 0.08, 0.2, 40), a + i * (b - a) / 3)
    track /= max(1.0, float(np.abs(track).max()) / 0.95)

    work = Path(tempfile.mkdtemp(prefix="qt_"))
    wav = work / "sound.wav"
    import wave
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(track, -1, 1) * 32767).astype("<i2").tobytes())

    bg = background(script.get("theme", "green")).convert("RGBA")
    bg.alpha_composite(chrome(script.get("badge") or {}, handle))
    base_rgb = bg

    # scene states per event (cumulative)
    states, cur = [], dict(script.get("scene") or {"type": "board", "lines": []})
    for ev in events:
        prev = dict(cur)
        if ev["line"].get("scene"):
            upd = ev["line"]["scene"]
            cur = dict(upd) if upd.get("type") and upd.get("type") != cur.get("type") else {**cur, **upd}
        states.append((prev, dict(cur)))

    cmd = [ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    card_cache: dict = {}
    scene_cache: dict = {}
    cap_cache: dict = {}
    qstate: dict = {}
    nframes = int(total * FPS)
    cover_frame = None
    cover_ms = None
    try:
        for fi in range(nframes):
            t = fi / FPS
            idx = 0
            for i, ev in enumerate(events):
                if ev["start"] <= t + 1e-6:
                    idx = i
            ev = events[idx]
            frame = base_rgb.copy()
            # scene
            prev, st = states[idx]
            k = min(1.0, max(0.0, (t - ev["start"]) / ANIM))
            skey = (idx, round(k, 2) if k < 1 else 1)
            if skey not in scene_cache:
                if len(scene_cache) > 40:
                    scene_cache.clear()
                scene_cache[skey] = draw_scene(st, prev, k)
            frame.alpha_composite(scene_cache[skey])
            # countdown dims the scene
            cd = ev.get("countdown")
            # card
            key, make = _card_for(ev, t, script, qstate)
            if key is not None:
                if key not in card_cache:
                    card_cache[key] = make()
                cim = card_cache[key]
                pop = ease(min(1.0, (t - ev["start"]) / 0.25)) if (ev["line"].get("card") or {}).get("kind") in ("hook", "trap", "step", "shortcut", "your_turn") and (idx == 0 or (events[idx - 1]["line"].get("card") or {}).get("title") != (ev["line"].get("card") or {}).get("title") or (events[idx - 1]["line"].get("card") or {}).get("kind") != (ev["line"].get("card") or {}).get("kind")) else 1.0
                frame.alpha_composite(cim, (0, int(CARD_Y - 4 - (1 - pop) * 30)))
            if cd and t >= cd[0]:
                dim = Image.new("RGBA", (W, H), (0, 0, 0, 120))
                frame.alpha_composite(dim)
                if key is not None:
                    frame.alpha_composite(card_cache[key], (0, CARD_Y - 4))
                left = cd[1] - t
                num = max(1, math.ceil(left / (COUNTDOWN / 3)))
                d = ImageDraw.Draw(frame)
                cx, cy = W // 2, 1180
                d.ellipse((cx - 80, cy - 80, cx + 80, cy + 80), fill=(20, 20, 20), outline=YEL, width=8)
                d.text((cx, cy), str(num), font=font("xb", 90), fill=WHITE, anchor="mm")
                d.text((cx, cy + 150), "Pause and pick your option", font=font("xb", 50), fill=WHITE, anchor="mm",
                       stroke_width=5, stroke_fill=(0, 0, 0))
            else:
                # caption
                words = ev["words"]
                lt = t - ev["start"]
                if words and lt <= ev["dur"] + 0.15:
                    for ph in phrases(words):
                        if ph[0][1] - 0.05 <= lt <= ph[-1][2] + 0.25 or (ph is phrases(words)[-1] and lt > ph[-1][2]):
                            cur_i = max(0, sum(1 for w in ph if w[1] <= lt) - 1)
                            ws = [_clean(w[0]) for w in ph]
                            ck = (tuple(ws), cur_i)
                            if ck not in cap_cache:
                                if len(cap_cache) > 60:
                                    cap_cache.clear()
                                cap_cache[ck] = caption(ws, cur_i)
                            frame.alpha_composite(cap_cache[ck], (0, CAP_Y - 90))
                            break
            if cover is not None and cover_frame is None and (ev["line"].get("card") or {}).get("kind") == "trap" and t > ev["start"] + 0.6:
                cover_frame = frame.convert("RGB")
                cover_ms = int(t * 1000)
            proc.stdin.write(frame.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise QTError("ffmpeg failed")
    if cover is not None and cover_frame is not None:
        cover_frame.save(cover, quality=90)
    return {"seconds": round(total, 1), "lines": len(events), "cover_ms": cover_ms}
