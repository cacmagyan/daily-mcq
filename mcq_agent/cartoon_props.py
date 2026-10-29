"""Cartoon props for explainer scenes, in the mascot's style (thick outline, flat colours, one shade).

Each function returns an SVG group drawn around its own origin (0, 0 = centre unless noted).
"""
from __future__ import annotations

import math
from html import escape

from .elephant import INK, OL, TIE as YELLOW, blob, f

RED = "#E5484D"
RED_SH = "#B9343A"
GREEN = "#2FA85A"
BLUE = "#4AA3E0"
BLUE_SH = "#2F7DBA"
CREAM = "#FFF8E8"
WOOD = "#C98A4B"
WOOD_SH = "#9C6531"
METAL = "#C8CED8"
NAVY = "#1F2D52"
FONT = "Poppins, sans-serif"
HAND = "'Patrick Hand', 'Poppins', sans-serif"


def rich(s: str) -> str:
    """Escape text; 'x^n' writes n as a superscript."""
    parts = s.split("^")
    out = escape(parts[0])
    for p in parts[1:]:
        sup, rest = p[:1], p[1:]
        out += (f'<tspan dy="-0.45em" font-size="62%">{escape(sup)}</tspan>'
                f'<tspan dy="0.45em">{escape(rest)}</tspan>' if rest else
                f'<tspan dy="-0.45em" font-size="62%">{escape(sup)}</tspan>')
    return out


def text(x, y, s, size, color=INK, weight=800, anchor="middle", font=FONT, rotate=0, extra="") -> str:
    rot = f' transform="rotate({rotate} {f(x)} {f(y)})"' if rotate else ""
    return (f'<text x="{f(x)}" y="{f(y)}" font-family="{font}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}" text-anchor="{anchor}" dominant-baseline="central"{rot} {extra}>{rich(s)}</text>')


def ticket(top="ADMIT ONE", price="₹300", w=300, h=150, color=YELLOW) -> str:
    n = 18
    x0, y0, x1, y1 = -w / 2, -h / 2, w / 2, h / 2
    d = (f"M {x0} {y0} L {x1} {y0} L {x1} {-n} A {n} {n} 0 0 0 {x1} {n} L {x1} {y1} L {x0} {y1} "
         f"L {x0} {n} A {n} {n} 0 0 0 {x0} {-n} Z")
    perf = x1 - 70
    return (f'<g><path d="{d}" fill="{color}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>'
            f'<path d="M {x0+12} {y1-14} L {x1-12} {y1-14}" stroke="#D49A00" stroke-width="8" opacity=".6"/>'
            f'<path d="M {perf} {y0+12} L {perf} {y1-12}" stroke="{INK}" stroke-width="4" stroke-dasharray="10 9"/>'
            + text((x0 + perf) / 2, -26, top, 26, weight=700)
            + text((x0 + perf) / 2, 22, price, 50, weight=800)
            + text((perf + x1) / 2, 0, "★", 36, weight=700) + "</g>")


def popcorn(w=150, h=170) -> str:
    top, bot = w / 2, w * 0.36
    s = [f'<g>']
    puffs = [(-48, -96, 30), (-14, -112, 32), (22, -104, 31), (52, -86, 27), (-30, -74, 26), (8, -80, 28), (40, -70, 22),
             (-58, -70, 22)]
    s.append(blob([("c", x, y, r) for x, y, r in puffs], CREAM))
    for x, y, r in puffs[:4]:
        s.append(f'<path d="M {x-r*0.4} {y+r*0.1} q {r*0.3} {-r*0.3} {r*0.6} 0" fill="none" stroke="#E8C77A" stroke-width="5" stroke-linecap="round"/>')
    d = f"M {-top} -66 L {top} -66 L {bot} {h-66} L {-bot} {h-66} Z"
    s.append(f'<clipPath id="pc"><path d="{d}"/></clipPath><path d="{d}" fill="#fff"/>')
    s.append('<g clip-path="url(#pc)">' + "".join(
        f'<path d="M {x} -70 L {x*0.72} {h-60} L {x*0.72+30} {h-60} L {x+38} -70 Z" fill="{RED}"/>' for x in (-90, -30, 30)) + "</g>")
    s.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(f'<rect x="{-top-6}" y="-78" width="{2*top+12}" height="22" rx="8" fill="{RED}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append("</g>")
    return "".join(s)


def seat(w=470, h=560) -> str:
    """Cinema seat seen from the front: drawn behind a sitting character (origin = seat centre)."""
    s = ['<g>']
    s.append(f'<rect x="{-w/2+40}" y="{-h/2}" width="{w-80}" height="{h*0.78}" rx="70" fill="{RED}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2+70}" y="{-h/2+30}" width="{w-140}" height="{h*0.62}" rx="50" fill="{RED_SH}" opacity=".45"/>')
    s.append(f'<rect x="{-w/2+20}" y="{h*0.18}" width="{w-40}" height="{h*0.24}" rx="40" fill="{RED}" stroke="{INK}" stroke-width="{OL}"/>')
    for side in (-1, 1):
        x = side * (w / 2 - 30)
        s.append(f'<rect x="{x-34}" y="{-h*0.02}" width="68" height="{h*0.42}" rx="26" fill="{RED_SH}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append("</g>")
    return "".join(s)


def armrests(w=470, h=560) -> str:
    s = []
    for side in (-1, 1):
        x = side * (w / 2 - 30)
        s.append(f'<rect x="{x-38}" y="{h*0.0}" width="76" height="34" rx="16" fill="#3B3F4E" stroke="{INK}" stroke-width="{OL}"/>')
    return "<g>" + "".join(s) + "</g>"


def cloud_path(w, h) -> list:
    bumps = []
    n = 9
    for i in range(n):
        a = 2 * math.pi * i / n
        bumps.append(("c", math.cos(a) * w * 0.38, math.sin(a) * h * 0.30, min(w, h) * 0.26))
    bumps.append(("e", 0, 0, w * 0.40, h * 0.34))
    return bumps


def bubble(label="?", w=330, h=230, tail=(-1, 1), size=None, color=INK, thought=True) -> str:
    """Thought bubble with a short label; the small circles trail toward `tail` (x, y direction)."""
    tx, ty = tail
    s = ['<g>']
    if thought:
        for i, r in enumerate((26, 17, 11)):
            cx = tx * (w * 0.36 + 40 + i * 40)
            cy = ty * (h * 0.36 + 30 + i * 36)
            s.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{r}" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>')
        s.append(blob(cloud_path(w, h), "#fff"))
    size = size or (110 if len(label) <= 2 else 74 if len(label) <= 5 else 56)
    s.append(text(0, 4, label, size, color=color, weight=800))
    s.append("</g>")
    return "".join(s)


def trap(w=360) -> str:
    """Mouse trap with a ticket as bait (origin = base centre)."""
    s = ['<g>']
    s.append(f'<path d="M {-w/2} 0 L {w/2} 0 L {w/2-30} 52 L {-w/2+30} 52 Z" fill="{WOOD_SH}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(f'<path d="M {-w/2} 0 L {w/2} 0 L {w/2-40} -46 L {-w/2+40} -46 Z" fill="{WOOD}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(f'<path d="M {-w/2+70} -24 Q 0 -150 {w/2-70} -24" fill="none" stroke="{INK}" stroke-width="{12+2*OL}" stroke-linecap="round"/>'
             f'<path d="M {-w/2+70} -24 Q 0 -150 {w/2-70} -24" fill="none" stroke="{METAL}" stroke-width="12" stroke-linecap="round"/>')
    s.append(f'<circle cx="{-w/2+70}" cy="-24" r="16" fill="{METAL}" stroke="{INK}" stroke-width="5"/>'
             f'<circle cx="{w/2-70}" cy="-24" r="16" fill="{METAL}" stroke="{INK}" stroke-width="5"/>')
    s.append(f'<g transform="translate(20 -36) rotate(-8) scale(.5)">{ticket()}</g>')
    s.append("</g>")
    return "".join(s)


def coin(r=110, label="₹300") -> str:
    return (f'<g><circle r="{r}" fill="#E0A100" stroke="{INK}" stroke-width="{OL}"/>'
            f'<circle r="{r*0.8}" fill="{YELLOW}" stroke="#C48C00" stroke-width="6"/>'
            f'<path d="M {-r*0.5} {-r*0.45} A {r*0.62} {r*0.62} 0 0 1 {r*0.2} {-r*0.62}" fill="none" stroke="#FFE38A" stroke-width="10" stroke-linecap="round"/>'
            + text(0, 6, label, int(r * 0.48), color="#6B4A00", weight=800) + "</g>")


def water(w=900, h=620) -> str:
    """Water seen from the side: wavy surface at y=0 (origin = surface centre)."""
    x0, x1 = -w / 2, w / 2
    waves = " ".join(f"Q {f(x0 + (i + 0.5) * w / 8)} {(-22 if i % 2 else 22)} {f(x0 + (i + 1) * w / 8)} 0" for i in range(8))
    d = f"M {x0} 0 {waves} L {x1} {h} L {x0} {h} Z"
    return (f'<g><defs><linearGradient id="wg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7EC8F0"/>'
            f'<stop offset="1" stop-color="#2F7DBA"/></linearGradient></defs>'
            f'<path d="{d}" fill="url(#wg)" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>'
            f'<path d="M {x0+60} 70 q 50 -18 100 0 M {x1-240} 120 q 50 -18 100 0 M {x0+200} 260 q 50 -18 100 0" '
            f'fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity=".55"/></g>')


def bubbles(n=5, spread=120, seed=3) -> str:
    out = []
    for i in range(n):
        x = math.sin(i * 2.3 + seed) * spread * 0.4
        y = -i * 60
        r = 10 + (i * 7) % 14
        out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{r}" fill="#DFF3FF" stroke="{INK}" stroke-width="4" opacity=".9"/>')
    return "<g>" + "".join(out) + "</g>"


def stamp_x(size=330) -> str:
    a = size / 2
    return (f'<g><path d="M {-a} {-a} L {a} {a} M {a} {-a} L {-a} {a}" stroke="{INK}" stroke-width="{58+2*OL}" stroke-linecap="round"/>'
            f'<path d="M {-a} {-a} L {a} {a} M {a} {-a} L {-a} {a}" stroke="{RED}" stroke-width="58" stroke-linecap="round"/></g>')


def stamp_check(size=200) -> str:
    a = size / 2
    d = f"M {-a} {0} L {-a*0.25} {a*0.7} L {a} {-a*0.8}"
    return (f'<g><path d="{d}" fill="none" stroke="{INK}" stroke-width="{46+2*OL}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="{GREEN}" stroke-width="46" stroke-linecap="round" stroke-linejoin="round"/></g>')


def icon(kind: str, r=70) -> str:
    if kind == "clock_sleepy":
        return (f'<g><circle r="{r}" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>'
                f'<path d="M 0 0 L 0 {-r*0.6} M 0 0 L {r*0.45} {r*0.2}" stroke="{INK}" stroke-width="8" stroke-linecap="round"/>'
                + text(r * 0.9, -r * 0.9, "z", 44, color=BLUE_SH) + text(r * 1.25, -r * 1.35, "z", 34, color=BLUE_SH) + "</g>")
    if kind == "door":
        return (f'<g><rect x="{-r*0.62}" y="{-r}" width="{r*1.24}" height="{r*2}" rx="10" fill="{GREEN}" stroke="{INK}" stroke-width="{OL}"/>'
                f'<circle cx="{r*0.35}" cy="6" r="9" fill="{YELLOW}" stroke="{INK}" stroke-width="4"/>'
                f'<path d="M {-r*1.3} 0 L {-r*0.2} 0 M {-r*0.55} -26 L {-r*0.2} 0 L {-r*0.55} 26" fill="none" stroke="{INK}" stroke-width="{12+2*4}" stroke-linecap="round" stroke-linejoin="round" transform="translate({r*1.65} 0)"/>'
                f'<path d="M {-r*1.3} 0 L {-r*0.2} 0 M {-r*0.55} -26 L {-r*0.2} 0 L {-r*0.55} 26" fill="none" stroke="#fff" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" transform="translate({r*1.65} 0)"/></g>')
    if kind == "money":
        return f'<g transform="scale({r/62})">{money(170, 92, "₹")}</g>'
    if kind == "calendar":
        return calendar("+1 yr", r)
    return more_icon(kind, r)


def card(title, sub, ikon, color, w=380, h=470) -> str:
    s = ['<g>']
    s.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="34" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<path d="M {-w/2} {-h/2+34} A 34 34 0 0 1 {-w/2+34} {-h/2} L {w/2-34} {-h/2} A 34 34 0 0 1 {w/2} {-h/2+34} '
             f'L {w/2} {-h/2+100} L {-w/2} {-h/2+100} Z" fill="{color}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(text(0, -h / 2 + 52, title, 54, color="#fff", weight=800))
    s.append(f'<g transform="translate(0 {-h/2+215})">{icon(ikon)}</g>')
    for i, line in enumerate(sub):
        s.append(text(0, h / 2 - 108 + i * 52, line, 40, weight=700))
    s.append("</g>")
    return "".join(s)


def confetti(w=900, h=700, n=26, seed=1) -> str:
    cols = [YELLOW, RED, GREEN, BLUE, "#9B6BDE"]
    out = []
    for i in range(n):
        x = (math.sin(i * 12.9898 + seed) * 43758.5453) % 1
        y = (math.sin(i * 78.233 + seed) * 12345.678) % 1
        x, y = (x - 0.5) * w, (y - 0.5) * h
        rot = (i * 47) % 180
        out.append(f'<rect x="{f(x-9)}" y="{f(y-16)}" width="18" height="32" rx="4" fill="{cols[i % len(cols)]}" '
                   f'stroke="{INK}" stroke-width="3" transform="rotate({rot} {f(x)} {f(y)})"/>')
    return "<g>" + "".join(out) + "</g>"


def paper(lines, title="COSTING EXAM", w=430, h=540) -> str:
    """Exam answer sheet (origin = centre). lines: [(text, colour)]."""
    s = ['<g>']
    s.append(f'<rect x="{-w/2+12}" y="{-h/2+12}" width="{w}" height="{h}" rx="16" fill="#E9E1CF" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="16" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<path d="M {-w/2+50} {-h/2} L {-w/2+50} {h/2}" stroke="#F0A0A8" stroke-width="4"/>')
    for i in range(7):
        y = -h / 2 + 130 + i * 58
        s.append(f'<path d="M {-w/2+20} {y} L {w/2-20} {y}" stroke="#BFD6EE" stroke-width="3"/>')
    s.append(text(0, -h / 2 + 64, title, 38, color=RED, weight=800))
    for i, (t, col) in enumerate(lines):
        s.append(text(-w / 2 + 70, -h / 2 + 108 + i * 58, t, 40, color=col, weight=400, anchor="start", font=HAND))
    s.append("</g>")
    return "".join(s)


def gear(r=60, teeth=10, color=METAL) -> str:
    pts = []
    for i in range(teeth * 2):
        a = math.pi * i / teeth
        rr = r if i % 2 == 0 else r * 0.8
        for da in (-0.13, 0.13):
            pts.append((math.cos(a + da) * rr, math.sin(a + da) * rr))
    d = "M " + " L ".join(f"{f(x)} {f(y)}" for x, y in pts) + " Z"
    return (f'<g><path d="{d}" fill="{color}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
            f'<circle r="{r*0.32}" fill="#8A93A3" stroke="{INK}" stroke-width="5"/></g>')


def machine(w=520, h=420) -> str:
    """Factory machine (origin = bottom centre)."""
    s = ['<g>']
    s.append(f'<rect x="{-w/2}" y="{-h}" width="{w}" height="{h-40}" rx="26" fill="#5B8DD6" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2+12}" y="{-h+12}" width="{w-24}" height="40" rx="14" fill="#7FA9E6"/>')
    s.append(f'<rect x="{-w/2+40}" y="{-h+80}" width="200" height="150" rx="16" fill="#DDE6F2" stroke="{INK}" stroke-width="5"/>')
    for i, c in enumerate((RED, YELLOW, GREEN)):
        s.append(f'<circle cx="{-w/2+80+i*60}" cy="{-h+275}" r="18" fill="{c}" stroke="{INK}" stroke-width="5"/>')
    s.append(f'<path d="M {-w/2+70} {-h+190} L {-w/2+110} {-h+140} L {-w/2+150} {-h+170} L {-w/2+210} {-h+110}" fill="none" stroke="{GREEN}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>')
    s.append(f'<g transform="translate({w/2-120} {-h+150})">{gear(70)}</g>')
    s.append(f'<g transform="translate({w/2-60} {-h+260}) rotate(15)">{gear(44, 8, YELLOW)}</g>')
    s.append(f'<rect x="{-w/2-20}" y="-52" width="{w+40}" height="52" rx="18" fill="#3B3F4E" stroke="{INK}" stroke-width="{OL}"/>')
    for x in range(-w // 2 + 20, w // 2, 70):
        s.append(f'<circle cx="{x}" cy="-26" r="13" fill="{METAL}" stroke="{INK}" stroke-width="4"/>')
    s.append("</g>")
    return "".join(s)


def tag(lines, w=300, h=170, strike=True) -> str:
    """Price tag on a string (origin = string top)."""
    s = ['<g>']
    s.append(f'<path d="M 0 0 L 0 50" stroke="{INK}" stroke-width="5"/>')
    d = f"M 0 50 L {w/2} 90 L {w/2} {90+h} L {-w/2} {90+h} L {-w/2} 90 Z"
    s.append(f'<path d="{d}" fill="{CREAM}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(f'<circle cx="0" cy="76" r="9" fill="#fff" stroke="{INK}" stroke-width="4"/>')
    for i, t in enumerate(lines):
        s.append(text(0, 128 + i * 58, t, 46 if i == 0 else 34, weight=800 if i == 0 else 600))
    if strike:
        s.append(f'<path d="M {-w/2+20} {150+h*0.2} L {w/2-20} {100+h*0.2}" stroke="{RED}" stroke-width="12" stroke-linecap="round"/>')
    s.append("</g>")
    return "".join(s)


def label(t, color=RED, size=64, rot=-8, pad=26) -> str:
    """Rubber-stamp style word in a rounded box."""
    w = len(t) * size * 0.66 + 2 * pad
    h = size + 2 * pad * 0.7
    return (f'<g transform="rotate({rot})"><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="16" fill="#fff" '
            f'stroke="{color}" stroke-width="10"/>' + text(0, 4, t, size, color=color, weight=800) + "</g>")


def board(title, lines, w=600, h=470) -> str:
    """Whiteboard on an easel (origin = board centre)."""
    s = ['<g>']
    for x0, x1 in ((-w * 0.3, -w * 0.42), (w * 0.3, w * 0.42)):
        s.append(f'<path d="M {x0} 0 L {x1} {h*0.95}" stroke="{INK}" stroke-width="{22+2*OL}" stroke-linecap="round"/>'
                 f'<path d="M {x0} 0 L {x1} {h*0.95}" stroke="{WOOD}" stroke-width="22" stroke-linecap="round"/>')
    s.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="22" fill="{WOOD}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2+20}" y="{-h/2+20}" width="{w-40}" height="{h-40}" rx="12" fill="#fff" stroke="{INK}" stroke-width="4"/>')
    s.append(text(0, -h / 2 + 82, title, 50, color=NAVY, weight=800))
    s.append(f'<path d="M {-w/2+60} {-h/2+124} L {w/2-60} {-h/2+124}" stroke="{YELLOW}" stroke-width="8" stroke-linecap="round"/>')
    for i, t in enumerate(lines):
        y = -h / 2 + 186 + i * 82
        s.append(f'<g transform="translate({-w/2+74} {y}) scale(.22)">{stamp_check(200)}</g>')
        s.append(text(-w / 2 + 112, y + 2, t, int(min(44, (w - 150) / max(1, len(t) * 0.6))), weight=700, anchor="start"))
    s.append("</g>")
    return "".join(s)


def money(w=230, h=120, label="₹") -> str:
    return (f'<g><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="12" fill="#8BCF8E" stroke="{INK}" stroke-width="{OL}"/>'
            f'<rect x="{-w/2+14}" y="{-h/2+14}" width="{w-28}" height="{h-28}" rx="8" fill="none" stroke="#3F8F4A" stroke-width="4"/>'
            f'<circle r="{h*0.3}" fill="#B7E4B8" stroke="#3F8F4A" stroke-width="4"/>' + text(0, 3, label, int(h * 0.42), color="#2C6B35") + "</g>")


# ── more props (second demo) ────────────────────────────────
def speech(label, w=None, h=150, tail="left", size=58) -> str:
    """Speech bubble; the tail points down-left or down-right toward the speaker."""
    w = w or max(260, int(len(label) * size * 0.6 + 90))
    tx = -w * 0.28 if tail == "left" else w * 0.28
    d_tail = f"M {tx-34} {h/2-6} L {tx-60 if tail == 'left' else tx+60} {h/2+70} L {tx+34} {h/2-6} Z"
    return (f'<g><path d="{d_tail}" fill="{INK}" stroke="{INK}" stroke-width="{2*OL}" stroke-linejoin="round"/>'
            f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="{h/2}" fill="{INK}" stroke="{INK}" stroke-width="{2*OL}"/>'
            f'<path d="{d_tail}" fill="#fff"/><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="{h/2}" fill="#fff"/>'
            + text(0, 2, label, size) + "</g>")


def bank(w=420, h=440, sign="10%") -> str:
    """Bank building (origin = bottom centre)."""
    s = ['<g>']
    s.append(f'<path d="M {-w/2-10} {-h*0.66} L 0 {-h} L {w/2+10} {-h*0.66} Z" fill="#E9EEF5" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(text(0, -h * 0.76, "BANK", 50, color=NAVY))
    s.append(f'<rect x="{-w/2}" y="{-h*0.66}" width="{w}" height="34" fill="#C9D3E0" stroke="{INK}" stroke-width="{OL}"/>')
    cols = 4
    for i in range(cols):
        x = -w / 2 + 40 + i * (w - 80) / (cols - 1)
        s.append(f'<rect x="{x-24}" y="{-h*0.66+34}" width="48" height="{h*0.66-34-50}" fill="#F4F6FA" stroke="{INK}" stroke-width="5"/>')
        s.append(f'<path d="M {x-8} {-h*0.66+50} L {x-8} {-60} M {x+8} {-h*0.66+50} L {x+8} {-60}" stroke="#C9D3E0" stroke-width="5"/>')
    s.append(f'<rect x="{-w/2-30}" y="-50" width="{w+60}" height="50" rx="6" fill="#C9D3E0" stroke="{INK}" stroke-width="{OL}"/>')
    if sign:
        s.append(f'<g transform="translate({w/2-10} {-h*0.86}) rotate(10)"><circle r="62" fill="{GREEN}" stroke="{INK}" stroke-width="{OL}"/>'
                 + text(0, 2, sign, 44, color="#fff") + "</g>")
    s.append("</g>")
    return "".join(s)


def arrow(length=180, color=GREEN) -> str:
    a = length / 2
    d = f"M {-a} 0 L {a-40} 0 M {a-70} -38 L {a-20} 0 L {a-70} 38"
    return (f'<g><path d="{d}" fill="none" stroke="{INK}" stroke-width="{30+2*OL}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/></g>')


def badge(label, color=GREEN, size=48) -> str:
    w = len(label) * size * 0.62 + 50
    h = size + 34
    return (f'<g><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="{h/2}" fill="{color}" stroke="{INK}" stroke-width="{OL}"/>'
            + text(0, 2, label, size, color="#fff") + "</g>")


def plant(scale_coins=True) -> str:
    """Money plant: a pot with a stem and rupee coins for leaves (origin = pot bottom centre)."""
    s = ['<g>']
    stem = "M 0 -230 C -20 -320 30 -380 0 -470 C -20 -530 10 -580 0 -620"
    s.append(f'<path d="{stem}" fill="none" stroke="{INK}" stroke-width="{18+2*OL}" stroke-linecap="round"/>'
             f'<path d="{stem}" fill="none" stroke="#3E9B4F" stroke-width="18" stroke-linecap="round"/>')
    leaves = [(-1, -320, -20), (1, -390, 20), (-1, -460, -25), (1, -530, 18), (-1, -585, -10)]
    for side, y, rot in leaves:
        x = side * 70
        s.append(f'<path d="M 0 {y} Q {x*0.5} {y-50} {x*1.3} {y-20} Q {x*0.6} {y+20} 0 {y} Z" fill="#5BBF63" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>')
    for x, y, r in ((-120, -400, 46), (118, -470, 46), (-96, -560, 40), (6, -660, 50)):
        s.append(f'<g transform="translate({x} {y})">{coin(r, "₹")}</g>')
    s.append(f'<path d="M -150 -240 L 150 -240 L 115 0 L -115 0 Z" fill="#D9774A" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(f'<rect x="-170" y="-275" width="340" height="56" rx="12" fill="#E8915F" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<path d="M 60 -200 L 40 -30" stroke="#B85E34" stroke-width="12" stroke-linecap="round" opacity=".6"/>')
    s.append("</g>")
    return "".join(s)


def sign(lines, w=440, color=NAVY) -> str:
    """Wooden sign on a post (origin = top of the post)."""
    h = 70 + 74 * len(lines)
    s = ['<g>']
    s.append(f'<path d="M 0 {h-20} L 0 {h+330}" stroke="{INK}" stroke-width="{30+2*OL}" stroke-linecap="round"/>'
             f'<path d="M 0 {h-20} L 0 {h+330}" stroke="{WOOD_SH}" stroke-width="30" stroke-linecap="round"/>')
    s.append(f'<rect x="{-w/2}" y="0" width="{w}" height="{h}" rx="22" fill="{WOOD}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2+16}" y="16" width="{w-32}" height="{h-32}" rx="14" fill="{CREAM}" stroke="{INK}" stroke-width="4"/>')
    size = int(min(54, (w - 70) / max(1, max(len(t) for t in lines) * 0.66))) if lines else 54
    for i, t in enumerate(lines):
        s.append(text(0, 70 + i * 74, t, size, color=color))
    s.append("</g>")
    return "".join(s)


def board_formula(title, formula, notes=(), w=600, h=470) -> str:
    """Whiteboard on an easel with one big formula (origin = board centre)."""
    s = ['<g>']
    for x0, x1 in ((-w * 0.3, -w * 0.42), (w * 0.3, w * 0.42)):
        s.append(f'<path d="M {x0} 0 L {x1} {h*0.95}" stroke="{INK}" stroke-width="{22+2*OL}" stroke-linecap="round"/>'
                 f'<path d="M {x0} 0 L {x1} {h*0.95}" stroke="{WOOD}" stroke-width="22" stroke-linecap="round"/>')
    s.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="22" fill="{WOOD}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2+20}" y="{-h/2+20}" width="{w-40}" height="{h-40}" rx="12" fill="#fff" stroke="{INK}" stroke-width="4"/>')
    s.append(text(0, -h / 2 + 78, title, 44, color=RED))
    size = min(78, int((w - 80) / max(1, len(formula)) * 1.75))
    s.append(f'<rect x="{-w/2+50}" y="{-h/2+140}" width="{w-100}" height="{size+50}" rx="16" fill="#FFF4C7"/>')
    s.append(text(0, -h / 2 + 165 + size / 2, formula, size, color=NAVY))
    for i, t in enumerate(notes):
        s.append(text(0, -h / 2 + 300 + i * 56, t, 38, weight=600, font=HAND))
    s.append("</g>")
    return "".join(s)


def scale(left, right, left_sub="", right_sub="", w=760) -> str:
    """Balance scale, level, with a label on each pan (origin = base centre)."""
    s = ['<g>']
    s.append(f'<path d="M -120 0 L 120 0 L 80 -50 L -80 -50 Z" fill="{WOOD}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(f'<path d="M 0 -50 L 0 -470" stroke="{INK}" stroke-width="{26+2*OL}" stroke-linecap="round"/>'
             f'<path d="M 0 -50 L 0 -470" stroke="{YELLOW}" stroke-width="26" stroke-linecap="round"/>')
    s.append(f'<path d="M {-w/2+60} -460 L {w/2-60} -460" stroke="{INK}" stroke-width="{22+2*OL}" stroke-linecap="round"/>'
             f'<path d="M {-w/2+60} -460 L {w/2-60} -460" stroke="{YELLOW}" stroke-width="22" stroke-linecap="round"/>')
    s.append(f'<circle cx="0" cy="-470" r="26" fill="{YELLOW}" stroke="{INK}" stroke-width="{OL}"/>')
    for side, lab, sub in ((-1, left, left_sub), (1, right, right_sub)):
        x = side * (w / 2 - 60)
        s.append(f'<path d="M {x} -460 L {x-110} -250 M {x} -460 L {x+110} -250" stroke="{INK}" stroke-width="5"/>')
        s.append(f'<path d="M {x-150} -250 L {x+150} -250 Q {x+120} -180 {x} -180 Q {x-120} -180 {x-150} -250 Z" fill="{METAL}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
        s.append(f'<g transform="translate({x} -340)">{badge(lab, NAVY if side < 0 else GREEN, 46)}</g>')
        if sub:
            s.append(text(x, -130, sub, 42, weight=700))
    s.append(f'<g transform="translate(0 -300)">' + f'<circle r="44" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>' + text(0, 2, "=", 64) + "</g>")
    s.append("</g>")
    return "".join(s)


def calendar(label="+1 yr", r=70) -> str:
    w, h = r * 1.8, r * 1.8
    return (f'<g><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="16" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>'
            f'<path d="M {-w/2} {-h/2+16} A 16 16 0 0 1 {-w/2+16} {-h/2} L {w/2-16} {-h/2} A 16 16 0 0 1 {w/2} {-h/2+16} L {w/2} {-h/2+38} L {-w/2} {-h/2+38} Z" fill="{RED}" stroke="{INK}" stroke-width="{OL}"/>'
            f'<path d="M {-w/4} {-h/2-14} L {-w/4} {-h/2+12} M {w/4} {-h/2-14} L {w/4} {-h/2+12}" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>'
            + text(0, 20, label, 38) + "</g>")


def formula_pill(formula, size=56) -> str:
    w = len(formula.replace("^", "")) * size * 0.58 + 80
    h = size + 50
    return (f'<g><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="{h/2}" fill="{NAVY}" stroke="{INK}" stroke-width="{OL}"/>'
            + text(0, 4, formula, size, color="#fff") + "</g>")


# ── money and time props ────────────────────────────────────
NOTE = "#8BCF8E"
NOTE_SH = "#5FAE66"


def cash(label="₹1,000", w=300, h=150, layers=4) -> str:
    """A bundle of notes with a paper band (origin = centre of the top note)."""
    s = ['<g>']
    for i in range(layers - 1, 0, -1):
        s.append(f'<rect x="{-w/2 + i*6}" y="{-h/2 + i*14}" width="{w}" height="{h}" rx="12" fill="{NOTE_SH}" '
                 f'stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="12" fill="{NOTE}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2+14}" y="{-h/2+14}" width="{w-28}" height="{h-28}" rx="8" fill="none" stroke="#3F8F4A" stroke-width="4"/>')
    s.append(f'<circle cx="{-w/2+48}" cy="0" r="22" fill="#B7E4B8" stroke="#3F8F4A" stroke-width="4"/>'
             f'<circle cx="{w/2-48}" cy="0" r="22" fill="#B7E4B8" stroke="#3F8F4A" stroke-width="4"/>')
    bw = max(150, len(label) * 30 + 40)
    s.append(f'<rect x="{-bw/2}" y="{-h/2-6}" width="{bw}" height="{h+12}" rx="8" fill="{YELLOW}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(text(0, 2, label, 48, weight=800))
    s.append("</g>")
    return "".join(s)


def calendar_page(top="NEXT YEAR", big="2027", sub="", w=300, h=320) -> str:
    s = ['<g>']
    s.append(f'<rect x="{-w/2+10}" y="{-h/2+10}" width="{w}" height="{h}" rx="22" fill="#E9E1CF" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="22" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<path d="M {-w/2} {-h/2+22} A 22 22 0 0 1 {-w/2+22} {-h/2} L {w/2-22} {-h/2} A 22 22 0 0 1 {w/2} {-h/2+22} '
             f'L {w/2} {-h/2+90} L {-w/2} {-h/2+90} Z" fill="{RED}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    for x in (-w * 0.25, w * 0.25):
        s.append(f'<rect x="{x-10}" y="{-h/2-26}" width="20" height="48" rx="10" fill="{METAL}" stroke="{INK}" stroke-width="5"/>')
    s.append(text(0, -h / 2 + 50, top, 40, color="#fff", weight=800))
    s.append(text(0, 30 if not sub else 4, big, 92 if len(big) <= 5 else 70, weight=800))
    if sub:
        s.append(text(0, h / 2 - 50, sub, 42, color=GREEN, weight=800))
    s.append("</g>")
    return "".join(s)


def curved_arrow(label="", length=300, color=YELLOW, flip=False, bend=-60) -> str:
    """Thick curved arrow from left to right (or right to left), label above (origin = middle)."""
    a = length / 2
    k = -1 if flip else 1
    x0, x1 = -a * k, a * k
    d = f"M {x0} 20 Q 0 {bend} {x1 - 40*k} 20"
    head = f"M {x1 - 70*k} -16 L {x1} 26 L {x1 - 78*k} 58 Z"
    return (f'<g><path d="{d}" fill="none" stroke="{INK}" stroke-width="{34+2*OL}" stroke-linecap="round"/>'
            f'<path d="{head}" fill="{INK}" stroke="{INK}" stroke-width="{2*OL}" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="34" stroke-linecap="round"/>'
            f'<path d="{head}" fill="{color}"/>'
            + (text(0, bend - 40, label, 58, weight=800) if label else "") + "</g>")


def money_plant(label="10%", w=260) -> str:
    """Money plant: coins growing from a pot (origin = pot bottom centre)."""
    s = ['<g>']
    s.append(f'<path d="M 0 -150 C -10 -260 10 -340 0 -430" fill="none" stroke="{INK}" stroke-width="{16+2*OL}" stroke-linecap="round"/>'
             f'<path d="M 0 -150 C -10 -260 10 -340 0 -430" fill="none" stroke="#3E9B4F" stroke-width="16" stroke-linecap="round"/>')
    for (x, y, rot) in ((-70, -300, -30), (70, -360, 30), (-60, -420, -20)):
        s.append(f'<g transform="translate({x} {y}) rotate({rot})"><ellipse rx="62" ry="28" fill="#5DBB63" stroke="{INK}" stroke-width="{OL}"/>'
                 f'<path d="M -50 0 L 50 0" stroke="#3E9B4F" stroke-width="5"/></g>')
    for (x, y) in ((-120, -230), (120, -280), (90, -470), (-110, -380)):
        s.append(f'<g transform="translate({x} {y}) scale(.36)">{coin(110, "₹")}</g>')
    s.append(f'<path d="M {-w/2} -160 L {w/2} -160 L {w/2-34} 0 L {-w/2+34} 0 Z" fill="#D9774A" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(f'<rect x="{-w/2-14}" y="-186" width="{w+28}" height="44" rx="12" fill="#E8895B" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(text(0, -76, label, 64, color="#fff", weight=800))
    s.append("</g>")
    return "".join(s)


def balance(left_svg, right_svg, left_label="TODAY", right_label="LATER", tilt=-12) -> str:
    """Balance scale tipped toward the left pan (origin = base bottom centre)."""
    s = ['<g>']
    s.append(f'<path d="M -130 0 L 130 0 L 90 -40 L -90 -40 Z" fill="{WOOD}" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    s.append(f'<rect x="-16" y="-470" width="32" height="440" rx="12" fill="{METAL}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<circle cx="0" cy="-470" r="26" fill="{YELLOW}" stroke="{INK}" stroke-width="{OL}"/>')
    t = math.radians(tilt)
    L = 330
    lx, ly = -L * math.cos(t), -470 - L * math.sin(t) * -1
    rx, ry = L * math.cos(t), -470 + L * math.sin(t) * -1
    lx, ly = -L * math.cos(t), -470 + L * math.sin(t)
    rx, ry = L * math.cos(t), -470 - L * math.sin(t)
    s.append(f'<path d="M {f(lx)} {f(ly)} L {f(rx)} {f(ry)}" stroke="{INK}" stroke-width="{24+2*OL}" stroke-linecap="round"/>'
             f'<path d="M {f(lx)} {f(ly)} L {f(rx)} {f(ry)}" stroke="{WOOD}" stroke-width="24" stroke-linecap="round"/>')
    for (px, py, item, lab) in ((lx, ly, left_svg, left_label), (rx, ry, right_svg, right_label)):
        s.append(f'<path d="M {f(px)} {f(py)} L {f(px-110)} {f(py+170)} M {f(px)} {f(py)} L {f(px+110)} {f(py+170)}" '
                 f'stroke="{INK}" stroke-width="5"/>')
        s.append(f'<path d="M {f(px-150)} {f(py+170)} Q {f(px)} {f(py+260)} {f(px+150)} {f(py+170)} Z" fill="{METAL}" '
                 f'stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
        s.append(f'<g transform="translate({f(px)} {f(py+110)}) scale(.56)">{item}</g>')
        s.append(text(px, py + 290, lab, 46, weight=800))
    s.append("</g>")
    return "".join(s)


def clock_money(r=170) -> str:
    s = [f'<g><circle r="{r}" fill="#fff" stroke="{INK}" stroke-width="{OL+2}"/>',
         f'<circle r="{r-18}" fill="none" stroke="{YELLOW}" stroke-width="10"/>']
    for i in range(12):
        a = math.radians(i * 30)
        s.append(f'<path d="M {f(math.sin(a)*(r-40))} {f(-math.cos(a)*(r-40))} L {f(math.sin(a)*(r-58))} {f(-math.cos(a)*(r-58))}" '
                 f'stroke="{INK}" stroke-width="7" stroke-linecap="round"/>')
    s.append(text(0, 8, "₹", int(r * 0.9), color=GREEN, weight=800))
    s.append(f'<path d="M 0 0 L 0 {-r*0.62} M 0 0 L {r*0.46} {r*0.18}" stroke="{INK}" stroke-width="12" stroke-linecap="round"/>'
             f'<circle r="12" fill="{INK}"/></g>')
    return "".join(s)


def formula_board(title, formula_svg, sub, w=880, h=430) -> str:
    s = ['<g>']
    s.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="26" fill="{NAVY}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2+20}" y="{-h/2+20}" width="{w-40}" height="{h-40}" rx="16" fill="#26375F" stroke="#3B4E7E" stroke-width="4"/>')
    s.append(text(0, -h / 2 + 76, title, 46, color=YELLOW, weight=800))
    s.append(f'<g transform="translate(0 6)">{formula_svg}</g>')
    s.append(text(0, h / 2 - 66, sub, 38, color="#DDE6F7", weight=600))
    s.append("</g>")
    return "".join(s)


def calculator(top="1,100 ÷ 1.1", big="1,000", w=440, h=620) -> str:
    s = ['<g>']
    s.append(f'<rect x="{-w/2+10}" y="{-h/2+12}" width="{w}" height="{h}" rx="40" fill="#3B3F4E" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="40" fill="#5A6074" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(f'<rect x="{-w/2+34}" y="{-h/2+40}" width="{w-68}" height="190" rx="18" fill="#CFE8C8" stroke="{INK}" stroke-width="{OL}"/>')
    ts = int(min(40, 320 / max(1, len(top.replace("^", "")) * 0.55)))
    bs = int(min(92, 320 / max(1, len(big) * 0.6)))
    s.append(text(w / 2 - 60, -h / 2 + 92, top, ts, color="#3B5B3A", weight=600, anchor="end"))
    s.append(text(w / 2 - 60, -h / 2 + 170, big, bs, color="#1E321E", weight=800, anchor="end"))
    keys = ["7", "8", "9", "÷", "4", "5", "6", "×", "1", "2", "3", "="]
    for i, k in enumerate(keys):
        cx = -w / 2 + 75 + (i % 4) * 97
        cy = -h / 2 + 300 + (i // 4) * 98
        col = YELLOW if k in "÷×=" else "#E9ECF2"
        s.append(f'<rect x="{cx-38}" y="{cy-36}" width="76" height="72" rx="16" fill="{col}" stroke="{INK}" stroke-width="5"/>')
        s.append(text(cx, cy + 2, k, 38, weight=800))
    s.append("</g>")
    return "".join(s)


def timeline(w=900) -> str:
    """Year 0, 1, 2 on a line; coins at years 1 and 2 brought back to year 0 (origin = line middle)."""
    s = ['<g>']
    s.append(f'<path d="M {-w/2} 0 L {w/2} 0" stroke="{INK}" stroke-width="{14+2*OL}" stroke-linecap="round"/>'
             f'<path d="M {-w/2} 0 L {w/2} 0" stroke="{NAVY}" stroke-width="14" stroke-linecap="round"/>')
    xs = (-w / 2 + 70, 0, w / 2 - 70)
    for x, lab in zip(xs, ("Today", "Year 1", "Year 2")):
        s.append(f'<circle cx="{x}" cy="0" r="22" fill="{YELLOW}" stroke="{INK}" stroke-width="{OL}"/>')
        s.append(text(x, 70, lab, 42, weight=800))
    for x in xs[1:]:
        s.append(f'<g transform="translate({x} -120) scale(.5)">{coin(110, "₹")}</g>')
    for x, bend in ((xs[1], -300), (xs[2], -420)):
        d = f"M {x-40} -190 Q {(x + xs[0]) / 2} {bend} {xs[0]+30} -80"
        s.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{14+8}" stroke-linecap="round" stroke-dasharray="1 34"/>'
                 f'<path d="{d}" fill="none" stroke="{GREEN}" stroke-width="14" stroke-linecap="round" stroke-dasharray="1 34"/>')
    s.append(f'<path d="M {xs[0]+6} -118 L {xs[0]+34} -64 L {xs[0]+62} -112" fill="none" stroke="{INK}" stroke-width="{12+8}" stroke-linecap="round" stroke-linejoin="round"/>'
             f'<path d="M {xs[0]+6} -118 L {xs[0]+34} -64 L {xs[0]+62} -112" fill="none" stroke="{GREEN}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>')
    s.append("</g>")
    return "".join(s)


# ── exam mistakes ───────────────────────────────────────────
def mistake_row(t, note="", ok=False, w=860, h=170) -> str:
    """One answer row: red with a cross (wrong, struck through) or green with a tick (origin = centre)."""
    fill = "#E3F5E9" if ok else "#FDE7E8"
    edge = GREEN if ok else RED
    size = int(min(64, (w - 220) / max(1, len(t) * 0.62)))
    s = [f'<g><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="30" fill="{fill}" stroke="{INK}" stroke-width="{OL}"/>',
         f'<rect x="{-w/2}" y="{-h/2}" width="22" height="{h}" rx="11" fill="{edge}"/>']
    ix = -w / 2 + 90
    s.append(f'<circle cx="{ix}" cy="0" r="52" fill="{edge}" stroke="{INK}" stroke-width="{OL}"/>')
    if ok:
        s.append(f'<path d="M {ix-24} 2 L {ix-6} 22 L {ix+26} -20" fill="none" stroke="#fff" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        s.append(f'<path d="M {ix-20} -20 L {ix+20} 20 M {ix+20} -20 L {ix-20} 20" stroke="#fff" stroke-width="14" stroke-linecap="round"/>')
    ty = -18 if note else 0
    s.append(text(-w / 2 + 170, ty, t, size, color=INK, weight=800, anchor="start"))
    if not ok:
        tw = len(t) * size * 0.56
        s.append(f'<path d="M {-w/2+162} {ty+4} L {-w/2+172+tw} {ty-2}" stroke="{RED}" stroke-width="9" stroke-linecap="round"/>')
    if note:
        s.append(text(-w / 2 + 172, 44, note, 34, color="#4A4F63", weight=600, anchor="start"))
    s.append("</g>")
    return "".join(s)


def coin_stack(n=5, rx=70, label="") -> str:
    """Stack of n coins (origin = bottom centre), with a label above."""
    s = ['<g>']
    for i in range(n):
        y = -18 - i * 30
        s.append(f'<path d="M {-rx} {y} L {-rx} {y-14} A {rx} 22 0 0 1 {rx} {y-14} L {rx} {y} A {rx} 22 0 0 1 {-rx} {y} Z" '
                 f'fill="#E0A100" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>')
        s.append(f'<ellipse cx="0" cy="{y-14}" rx="{rx}" ry="22" fill="{YELLOW}" stroke="{INK}" stroke-width="5"/>')
    top = -18 - (n - 1) * 30 - 14
    s.append(f'<ellipse cx="0" cy="{top}" rx="{rx*0.55}" ry="11" fill="none" stroke="#FFE38A" stroke-width="5"/>')
    if label:
        s.append(text(0, top - 70, label, 44, weight=800))
    s.append("</g>")
    return "".join(s)


def coin_bars(labels, values, counts, w=900) -> str:
    """Coin stacks growing left to right, value above and label below each (origin = baseline centre)."""
    n = len(labels)
    s = ['<g>', f'<path d="M {-w/2} 0 L {w/2} 0" stroke="{INK}" stroke-width="8" stroke-linecap="round"/>']
    for i, (lab, val, c) in enumerate(zip(labels, values, counts)):
        x = -w / 2 + w / n * (i + 0.5)
        s.append(f'<g transform="translate({f(x)} 0)">{coin_stack(c, 70, val)}</g>')
        s.append(text(x, 52, lab, 44, weight=800, color=NAVY))
    s.append("</g>")
    return "".join(s)



# ── more icons, tiles and the true/false card (explainer templates) ─────────
ICONS = ("money", "calendar", "clock", "door", "doc", "check", "cross", "chart_up", "chart_down", "scale",
         "factory", "bank", "people", "bulb")


def more_icon(kind: str, r=70) -> str:
    o = f'stroke="{INK}" stroke-width="{OL}"'
    if kind == "clock":
        return (f'<g><circle r="{r}" fill="#fff" {o}/>'
                f'<path d="M 0 0 L 0 {-r*0.6} M 0 0 L {r*0.45} {r*0.2}" stroke="{INK}" stroke-width="8" stroke-linecap="round"/></g>')
    if kind == "doc":
        return (f'<g><path d="M {-r*0.7} {-r} L {r*0.35} {-r} L {r*0.7} {-r*0.65} L {r*0.7} {r} L {-r*0.7} {r} Z" fill="#fff" {o} stroke-linejoin="round"/>'
                + "".join(f'<path d="M {-r*0.42} {y} L {r*0.42} {y}" stroke="#9AA4B8" stroke-width="7" stroke-linecap="round"/>'
                          for y in (-r * 0.35, 0, r * 0.35)) + "</g>")
    if kind == "check":
        return f'<g><circle r="{r}" fill="{GREEN}" {o}/><g transform="scale({r/110})" >' \
               f'<path d="M -45 0 L -12 34 L 48 -34" fill="none" stroke="#fff" stroke-width="22" stroke-linecap="round" stroke-linejoin="round"/></g></g>'
    if kind == "cross":
        return f'<g><circle r="{r}" fill="{RED}" {o}/><g transform="scale({r/110})">' \
               f'<path d="M -36 -36 L 36 36 M 36 -36 L -36 36" stroke="#fff" stroke-width="22" stroke-linecap="round"/></g></g>'
    if kind in ("chart_up", "chart_down"):
        up = kind == "chart_up"
        pts = "-50,30 -15,0 10,15 50,-35" if up else "-50,-35 -15,0 10,-15 50,30"
        col = GREEN if up else RED
        return (f'<g transform="scale({r/70})"><rect x="-70" y="-60" width="140" height="120" rx="14" fill="#fff" {o}/>'
                f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/></g>')
    if kind == "scale":
        return (f'<g transform="scale({r/70})"><path d="M 0 -55 L 0 50 M -40 55 L 40 55 M -60 -40 L 60 -40" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>'
                f'<path d="M -78 0 L -42 0 Q -60 22 -78 0 Z M 42 0 L 78 0 Q 60 22 42 0 Z" fill="{YELLOW}" {o} stroke-linejoin="round"/>'
                f'<path d="M -60 -40 L -78 0 M -60 -40 L -42 0 M 60 -40 L 42 0 M 60 -40 L 78 0" stroke="{INK}" stroke-width="4"/></g>')
    if kind == "factory":
        return (f'<g transform="scale({r/70})"><path d="M -65 55 L -65 -5 L -25 -30 L -25 -5 L 15 -30 L 15 -5 L 65 -30 L 65 55 Z" fill="#9DB7E0" {o} stroke-linejoin="round"/>'
                f'<rect x="35" y="-70" width="20" height="45" fill="#C8CED8" {o}/></g>')
    if kind == "bank":
        return f'<g transform="translate(0 {r}) scale({r/240})">{bank(420, 440, "")}</g>'
    if kind == "people":
        return (f'<g transform="scale({r/70})">' + "".join(
            f'<g transform="translate({x} 0)"><circle cy="-22" r="20" fill="#F6D2B5" {o}/>'
            f'<path d="M -30 50 Q -30 6 0 6 Q 30 6 30 50 Z" fill="{c}" {o}/></g>' for x, c in ((-36, BLUE), (36, YELLOW))) + "</g>")
    if kind == "bulb":
        return (f'<g transform="scale({r/70})"><path d="M 0 -60 C -40 -60 -52 -24 -40 2 C -32 18 -22 22 -22 40 L 22 40 C 22 22 32 18 40 2 C 52 -24 40 -60 0 -60 Z" fill="#FFF1A8" {o}/>'
                f'<rect x="-20" y="42" width="40" height="20" rx="6" fill="#C8CED8" {o}/></g>')
    raise ValueError(f"unknown icon {kind}")


def wrap(t: str, width: int) -> list[str]:
    words, lines, cur = t.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def tile(big: str, note: str = "", color=NAVY, w=330, h=230) -> str:
    """A card with one big value and a small note under it (origin = centre)."""
    size = int(min(84, (w - 50) / max(1, len(big) * 0.62)))
    s = [f'<g><rect x="{-w/2+8}" y="{-h/2+10}" width="{w}" height="{h}" rx="28" fill="#E9E1CF" stroke="{INK}" stroke-width="{OL}"/>',
         f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="28" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>',
         f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="26" rx="13" fill="{color}"/>',
         text(0, -6 if note else 8, big, size, color=color, weight=800)]
    if note:
        s.append(text(0, h / 2 - 46, note, 34, weight=600, color="#4A4F63"))
    s.append("</g>")
    return "".join(s)


def statement(t: str, w=900, title="TRUE OR FALSE?") -> str:
    """A statement card for true/false traps (origin = centre)."""
    lines = wrap(t, 26)[:4]
    h = 150 + 70 * len(lines)
    s = [f'<g><rect x="{-w/2+10}" y="{-h/2+12}" width="{w}" height="{h}" rx="34" fill="#E9E1CF" stroke="{INK}" stroke-width="{OL}"/>',
         f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="34" fill="#fff" stroke="{INK}" stroke-width="{OL}"/>',
         text(0, -h / 2 + 56, title, 40, color=BLUE_SH, weight=800)]
    for i, line in enumerate(lines):
        s.append(text(0, -h / 2 + 128 + i * 70, line, 54, weight=700))
    s.append("</g>")
    return "".join(s)
