"""The page's elephant: an original cartoon mascot drawn as SVG, in any pose and expression.

Everything is drawn in a 600 x 800 box (feet at about y 700). A pose is a dict:
    {"face": "smug", "trunk": "down", "left": arm, "right": arm, "legs": "stand", "tilt": 0}
where an arm is (elbow, wrist, hand) with points in box units, or a preset name from ARMS.
"""
from __future__ import annotations

import math

INK = "#22263A"          # outline
SKIN = "#A9B6C8"
SKIN_SH = "#8D9BB0"
SKIN_HI = "#C9D3E0"
EAR_IN = "#F2B3C2"
EAR_IN_SH = "#E494A8"
BLUSH = "#F49AB0"
SUIT = "#1F2D52"
SUIT_SH = "#16203D"
SHIRT = "#FFFFFF"
TIE = "#F5B700"
TIE_SH = "#D49A00"
NAIL = "#F4EEDF"
PAW = SKIN               # hand colour
CUFF = True              # white shirt cuff at the wrist
OL = 6.5                 # outline width


def f(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def pts(points) -> str:
    return " ".join(f"{f(x)},{f(y)}" for x, y in points)


# ── geometry ────────────────────────────────────────────────
def bez(p0, p1, p2, p3, t):
    u = 1 - t
    x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
    dx = 3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0])
    dy = 3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1])
    return (x, y), (dx, dy)


def sample(segments, n=40):
    """Points and unit tangents along a chain of cubic segments."""
    out = []
    for i, seg in enumerate(segments):
        for k in range(n + (1 if i == len(segments) - 1 else 0)):
            p, d = bez(*seg, k / n)
            l = math.hypot(*d) or 1
            out.append((p, (d[0] / l, d[1] / l)))
    return out


def tube(segments, w0, w1, wtop=None, flare=0.2):
    """Left edge, right edge and samples of a tapered tube (narrower `wtop` at the very top, widest at `flare`)."""
    s = sample(segments)
    left, right = [], []
    for i, (p, d) in enumerate(s):
        t = i / (len(s) - 1)
        if wtop is not None and t < flare:
            k = t / flare
            w = (wtop + (w0 - wtop) * (1 - (1 - k) ** 2)) / 2
        else:
            w = (w0 + (w1 - w0) * (t - (flare if wtop is not None else 0)) / (1 - (flare if wtop is not None else 0))) / 2
        nx, ny = -d[1], d[0]
        left.append((p[0] + nx * w, p[1] + ny * w))
        right.append((p[0] - nx * w, p[1] - ny * w))
    return left, right, s


def path_poly(points, close=True) -> str:
    d = "M " + " L ".join(f"{f(x)} {f(y)}" for x, y in points)
    return d + (" Z" if close else "")


# ── parts ───────────────────────────────────────────────────
HEAD = ("M 300 104 C 392 104 458 166 458 250 C 458 330 398 378 300 380 "
        "C 202 378 142 330 142 250 C 142 166 208 104 300 104 Z")
EAR_L = ("M 200 168 C 140 118 54 138 48 228 C 42 312 84 378 150 372 "
         "C 180 370 198 348 198 320 Z")
EAR_L_IN = ("M 186 186 C 140 156 80 170 78 234 C 76 296 106 340 150 338 "
            "C 168 336 178 322 178 304 Z")
BODY = ("M 220 352 C 196 384 184 432 186 482 C 188 544 232 574 300 574 "
        "C 368 574 412 544 414 482 C 416 432 404 384 380 352 Z")


def mirror(d: str) -> str:
    """Mirror a path's x coordinates around x = 300 (absolute M/C/L/Q/Z only)."""
    out, tokens = [], d.replace(",", " ").split()
    i, axis = 0, 0
    for tok in tokens:
        if tok.isalpha():
            out.append(tok)
            axis = 0
            continue
        v = float(tok)
        out.append(f(600 - v) if axis == 0 else f(v))
        axis ^= 1
    return " ".join(out)


def shaded(d: str, base: str, shadow: str, uid: str, dx=-12, dy=-14, stroke=True, hi: str | None = None,
           hi_ellipse=None) -> str:
    """A shape with a cel-shaded crescent (bottom-right) and an outline."""
    s = [f'<clipPath id="{uid}"><path d="{d}"/></clipPath>',
         f'<g clip-path="url(#{uid})"><path d="{d}" fill="{shadow}"/>'
         f'<path d="{d}" fill="{base}" transform="translate({dx},{dy})"/>']
    if hi and hi_ellipse:
        cx, cy, rx, ry, rot = hi_ellipse
        s.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" transform="rotate({rot} {cx} {cy})" '
                 f'fill="{hi}" opacity=".55"/>')
    s.append("</g>")
    if stroke:
        s.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{OL}" stroke-linejoin="round"/>')
    return "".join(s)


# ── face ────────────────────────────────────────────────────
FACES = {
    #        lid(0 open..1 shut), pupil dx,dy, pupil r, brow, mouth, eye scale, extras
    "smug":    dict(lid=0.42, look=(4, 6), pr=14, brow="flat", mouth="smirk"),
    "happy":   dict(lid=0.0, look=(0, 2), pr=15, brow="up", mouth="smile"),
    "joy":     dict(lid=-1, look=(0, 0), pr=15, brow="up", mouth="open"),      # ^ ^ eyes
    "excited": dict(lid=0.0, look=(0, -2), pr=13, brow="high", mouth="open", scale=1.1),
    "shocked": dict(lid=0.0, look=(0, 0), pr=8, brow="high", mouth="o", scale=1.14, sweat=True),
    "worried": dict(lid=0.18, look=(-3, 4), pr=14, brow="sad", mouth="wavy", sweat=True),
    "sleepy":  dict(lid=0.62, look=(0, 8), pr=13, brow="droop", mouth="flat"),
    "think":   dict(lid=0.1, look=(9, -11), pr=13, brow="raise", mouth="hmm"),
    "wink":    dict(lid=0.0, look=(0, 2), pr=15, brow="up", mouth="smile", wink=True),
    "proud":   dict(lid=0.3, look=(0, 3), pr=14, brow="up", mouth="smile"),
    "sad":     dict(lid=0.3, look=(0, 9), pr=13, brow="sad", mouth="frown"),
}
EYES = [(246, 224), (354, 224)]


def eye(i: int, cx: float, cy: float, cfg: dict, uid: str) -> str:
    sc = cfg.get("scale", 1.0)
    rx, ry = 30 * sc, 37 * sc
    if cfg["lid"] == -1 or (cfg.get("wink") and i == 1):          # closed happy eye: ^
        return (f'<path d="M {f(cx-26)} {f(cy+8)} Q {f(cx)} {f(cy-26)} {f(cx+26)} {f(cy+8)}" fill="none" '
                f'stroke="{INK}" stroke-width="8" stroke-linecap="round"/>')
    dx, dy = cfg["look"]
    pr = cfg["pr"]
    s = [f'<clipPath id="{uid}e{i}"><ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}"/></clipPath>',
         f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#fff"/>',
         f'<g clip-path="url(#{uid}e{i})">',
         f'<ellipse cx="{f(cx+dx)}" cy="{f(cy+dy)}" rx="{f(pr)}" ry="{f(pr*1.18)}" fill="{INK}"/>',
         f'<circle cx="{f(cx+dx-pr*0.35)}" cy="{f(cy+dy-pr*0.45)}" r="{f(max(3, pr*0.33))}" fill="#fff"/>']
    lid = cfg["lid"]
    if lid > 0:
        y = cy - ry + 2 * ry * lid
        s.append(f'<rect x="{f(cx-rx-4)}" y="{f(cy-ry-6)}" width="{f(2*rx+8)}" height="{f(y-(cy-ry-6))}" fill="{SKIN}"/>')
        s.append(f'<path d="M {f(cx-rx-4)} {f(y+3)} Q {f(cx)} {f(y-5)} {f(cx+rx+4)} {f(y+3)}" fill="none" '
                 f'stroke="{INK}" stroke-width="5.5" stroke-linecap="round"/>')
    s.append("</g>")
    s.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="{INK}" stroke-width="5.5"/>')
    return "".join(s)


def brows(kind: str) -> str:
    (lx, ly), (rx, ry) = EYES
    shapes = {
        "flat":  [(-22, -50, 0, -54, 22, -50)],
        "up":    [(-22, -52, 0, -62, 22, -54)],
        "high":  [(-22, -62, 0, -76, 22, -64)],
        "sad":   [(-24, -70, 0, -64, 22, -50)],
        "droop": [(-22, -46, 0, -50, 22, -48)],
        "raise": [(-22, -56, 0, -66, 22, -58)],
    }[kind][0]
    out = []
    for side, (cx, cy) in ((-1, (lx, ly)), (1, (rx, ry))):
        x0, y0, x1, y1, x2, y2 = shapes
        if side == -1:                               # left brow mirrors the shape
            x0, x2 = -x2, -x0
            y0, y2 = y2, y0
            x1 = -x1
        if kind == "raise" and side == -1:
            y0, y1, y2 = y0 + 8, y1 + 8, y2 + 8
        out.append(f'<path d="M {f(cx+x0)} {f(cy+y0)} Q {f(cx+x1)} {f(cy+y1)} {f(cx+x2)} {f(cy+y2)}" fill="none" '
                   f'stroke="{INK}" stroke-width="8" stroke-linecap="round"/>')
    return "".join(out)


def mouth(kind: str) -> str:
    """Mouths sit under the trunk; the trunk is drawn over the middle."""
    if kind == "smile":
        return (f'<path d="M 238 318 Q 300 368 362 318" fill="none" stroke="{INK}" stroke-width="7" '
                'stroke-linecap="round"/>')
    if kind == "smirk":
        return (f'<path d="M 244 326 Q 300 356 358 316" fill="none" stroke="{INK}" stroke-width="7" '
                'stroke-linecap="round"/>')
    if kind == "flat":
        return f'<path d="M 250 334 L 350 334" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
    if kind == "frown":
        return (f'<path d="M 246 344 Q 300 316 354 344" fill="none" stroke="{INK}" stroke-width="7" '
                'stroke-linecap="round"/>')
    if kind == "wavy":
        return (f'<path d="M 244 336 Q 262 324 280 336 Q 300 348 320 336 Q 338 324 356 336" fill="none" '
                f'stroke="{INK}" stroke-width="7" stroke-linecap="round"/>')
    if kind == "hmm":
        return f'<path d="M 318 338 Q 340 330 362 336" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
    if kind == "open":
        return (f'<path d="M 236 312 Q 300 404 364 312 Q 300 330 236 312 Z" fill="#5A1F2E" stroke="{INK}" '
                f'stroke-width="6" stroke-linejoin="round"/>'
                f'<path d="M 270 352 Q 300 380 330 352 Q 300 340 270 352 Z" fill="#F07C93"/>')
    if kind == "o":
        return (f'<ellipse cx="300" cy="350" rx="24" ry="28" fill="#5A1F2E" stroke="{INK}" stroke-width="6"/>'
                f'<ellipse cx="300" cy="362" rx="12" ry="9" fill="#F07C93"/>')
    if kind == "talk1":                          # talking: half open, then open (the trunk stays put)
        return (f'<path d="M 230 318 Q 300 376 370 318 Q 300 338 230 318 Z" fill="#5A1F2E" stroke="{INK}" '
                f'stroke-width="6" stroke-linejoin="round"/>')
    if kind == "talk2":
        return (f'<path d="M 224 312 Q 300 414 376 312 Q 300 336 224 312 Z" fill="#5A1F2E" stroke="{INK}" '
                f'stroke-width="6" stroke-linejoin="round"/>'
                f'<path d="M 250 360 Q 300 396 350 360 Q 300 348 250 360 Z" fill="#F07C93"/>')
    return ""


TRUNKS = {
    # chains of cubic segments for the trunk's centre line, from between the eyes to the tip
    "down":  [((300, 254), (300, 290), (298, 330), (302, 362)), ((302, 362), (306, 396), (336, 408), (352, 388))],
    "curl":  [((300, 254), (300, 290), (294, 334), (296, 364)), ((296, 364), (298, 404), (346, 408), (348, 376))],
    "up":    [((300, 254), (300, 296), (352, 336), (412, 322)), ((412, 322), (462, 310), (486, 262), (474, 214))],
    "left":  [((300, 254), (300, 290), (294, 330), (286, 360)), ((286, 360), (276, 394), (248, 406), (230, 392))],
    "lift":  [((300, 254), (300, 290), (314, 326), (342, 336)), ((342, 336), (372, 346), (394, 330), (400, 306))],
}


def trunk(kind: str, uid: str) -> str:
    segs = TRUNKS[kind]
    left, right, s = tube(segs, 86, 42, wtop=58, flare=0.22)
    tip, tdir = s[-1]
    r = 21
    ang = math.degrees(math.atan2(tdir[1], tdir[0]))
    # tip cap: half circle beyond the last point
    cap = []
    for k in range(0, 13):
        a = math.radians(ang - 90 + 180 * k / 12)
        cap.append((tip[0] + r * math.cos(a), tip[1] + r * math.sin(a)))
    poly = left + cap[::-1][1:-1] + right[::-1]
    d = path_poly(poly)
    # shading: a band along the right edge
    k0 = len(s) // 6
    sh = [(x - (x - p[0]) * 0.45 * min(1, i / (2 * k0 + 1)), y - (y - p[1]) * 0.45 * min(1, i / (2 * k0 + 1)))
          for i, ((x, y), (p, _)) in enumerate(zip(right, s))]
    band = path_poly(right[k0:] + sh[k0:][::-1])
    out = [f'<clipPath id="{uid}t"><path d="{d}"/></clipPath>',
           f'<path d="{d}" fill="{SKIN}"/>',
           f'<g clip-path="url(#{uid}t)"><path d="{band}" fill="{SKIN_SH}"/></g>']
    # outline on the two sides and the tip, not across the base
    edge = left[3:] + cap[::-1][1:-1] + right[::-1][:-3]
    out.append(f'<path d="{path_poly(edge, close=False)}" fill="none" stroke="{INK}" stroke-width="{OL}" '
               'stroke-linejoin="round" stroke-linecap="round"/>')
    # tip end and wrinkles
    tx, ty = tip[0] + math.cos(math.radians(ang)) * 4, tip[1] + math.sin(math.radians(ang)) * 4
    out.append(f'<ellipse cx="{f(tx)}" cy="{f(ty)}" rx="10" ry="17" transform="rotate({f(ang)} {f(tx)} {f(ty)})" '
               f'fill="{SKIN_SH}" stroke="{INK}" stroke-width="4"/>')
    n = len(s)
    for frac in (0.40, 0.50, 0.60):
        i = int(n * frac)
        (lx, ly), (rx, ry) = left[i], right[i]
        mx, my = s[i][0]
        a = (lx + (rx - lx) * 0.22, ly + (ry - ly) * 0.22)
        b = (lx + (rx - lx) * 0.72, ly + (ry - ly) * 0.72)
        c = (mx + s[i][1][0] * 7, my + s[i][1][1] * 7)
        out.append(f'<path d="M {f(a[0])} {f(a[1])} Q {f(c[0])} {f(c[1])} {f(b[0])} {f(b[1])}" fill="none" '
                   f'stroke="{INK}" stroke-width="3.5" stroke-linecap="round" opacity=".8"/>')
    return "".join(out)


# ── hands and arms ──────────────────────────────────────────
def capsule(a, b, w, color) -> str:
    return (f'<path d="M {f(a[0])} {f(a[1])} L {f(b[0])} {f(b[1])}" stroke="{color}" stroke-width="{f(w)}" '
            'stroke-linecap="round"/>')


def blob(parts, color=None) -> str:
    """Merged silhouette with one outline: parts are ("c", cx, cy, r) circles, ("e", cx, cy, rx, ry) ellipses
    or ("l", ax, ay, bx, by, w) capsules."""
    color = color or PAW

    def draw(p, col, grow):
        if p[0] == "c":
            return f'<circle cx="{f(p[1])}" cy="{f(p[2])}" r="{f(p[3]+grow)}" fill="{col}"/>'
        if p[0] == "e":
            return f'<ellipse cx="{f(p[1])}" cy="{f(p[2])}" rx="{f(p[3]+grow)}" ry="{f(p[4]+grow)}" fill="{col}"/>'
        return capsule((p[1], p[2]), (p[3], p[4]), p[5] + 2 * grow, col)
    return "".join(draw(p, INK, OL * 0.8) for p in parts) + "".join(draw(p, color, 0) for p in parts)


def hand(kind: str) -> tuple[str, str]:
    """(svg, front svg drawn after props) in local coords: wrist at 0,0, hand pointing to +x, palm toward
    the viewer, thumb toward -y."""
    if kind == "open":
        parts = [("e", 24, 0, 25, 23), ("l", 36, -14, 54, -22, 15), ("l", 40, -2, 62, -2, 15),
                 ("l", 36, 11, 54, 18, 15), ("l", 14, -16, 6, -34, 15)]
        return blob(parts), ""
    if kind == "point":
        parts = [("c", 22, 0, 23), ("l", 30, -10, 70, -16, 15), ("l", 12, -14, 26, -24, 14)]
        crease = (f'<path d="M 30 4 Q 40 6 44 0 M 26 14 Q 36 16 42 10" fill="none" stroke="{INK}" '
                  'stroke-width="3" stroke-linecap="round"/>')
        return blob(parts) + crease, ""
    if kind == "fist":
        parts = [("c", 22, 0, 24), ("l", 14, -16, 30, -22, 15)]
        crease = (f'<path d="M 36 -8 Q 44 -6 44 -2 M 38 4 Q 46 6 44 10 M 34 14 Q 40 18 38 20" fill="none" '
                  f'stroke="{INK}" stroke-width="3" stroke-linecap="round"/>')
        return blob(parts) + crease, ""
    if kind == "hold":                          # fingers wrap in front of a held prop
        back = blob([("c", 22, 0, 23)])
        front = blob([("l", 30, -14, 40, -14, 16), ("l", 32, 0, 42, 0, 16), ("l", 30, 14, 40, 14, 16)])
        return back, front
    raise ValueError(kind)


def thumbs_up() -> str:
    """Upright thumbs-up (screen coords, wrist at 0,0 below the fist)."""
    parts = [("e", 0, -26, 25, 22), ("l", -6, -44, -6, -74, 17)]
    crease = (f'<path d="M 4 -36 L 20 -36 M 4 -24 L 20 -24 M 4 -12 L 18 -12" fill="none" stroke="{INK}" '
              'stroke-width="3" stroke-linecap="round"/>')
    return blob(parts) + crease


SHOULDERS = {"left": (222, 384), "right": (378, 384)}

# arm presets: (elbow, wrist, hand) for the right arm (viewer's right); the left mirrors them
ARMS = {
    "down":     ((418, 452), (424, 518), "open"),
    "hip":      ((452, 432), (410, 482), "fist"),
    "point_up": ((448, 366), (470, 290), "point"),
    "point_side": ((452, 382), (520, 360), "point"),
    "wave":     ((456, 362), (486, 284), "open"),
    "thumb":    ((452, 428), (470, 372), "thumb"),
    "chin":     ((436, 470), (352, 366), "fist"),
    "shrug":    ((440, 444), (500, 404), "open"),
    "hold_up":  ((452, 376), (478, 300), "hold"),
    "hold_out": ((446, 430), (500, 420), "hold"),
    "cheer":    ((476, 352), (528, 276), "fist"),
    "present":  ((448, 440), (510, 452), "open"),
}


def arm(side: str, spec, props: dict) -> tuple[str, str]:
    """(arm svg, front svg) for one arm. `props` maps side -> svg drawn in the hand (local coords)."""
    if isinstance(spec, str):
        spec = ARMS[spec]
    elbow, wrist, kind = spec
    if side == "left":
        elbow, wrist = (600 - elbow[0], elbow[1]), (600 - wrist[0], wrist[1])
    sx, sy = SHOULDERS[side]
    w = 40
    d = f"M {sx} {sy} Q {f(elbow[0])} {f(elbow[1])} {f(wrist[0])} {f(wrist[1])}"
    ang = math.degrees(math.atan2(wrist[1] - elbow[1], wrist[0] - elbow[0]))
    # cuff: a short white band just before the wrist
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    c0 = (wrist[0] - ux * 14, wrist[1] - uy * 14)
    sleeve = (f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{f(w+2*OL)}" stroke-linecap="round"/>'
              f'<path d="{d}" fill="none" stroke="{SUIT}" stroke-width="{w}" stroke-linecap="round"/>')
    if CUFF:
        sleeve += capsule(c0, wrist, w - 2, INK) + capsule(c0, (wrist[0] - ux * 2, wrist[1] - uy * 2), w - 12, SHIRT)
    if kind == "thumb":
        return sleeve + f'<g transform="translate({f(wrist[0])} {f(wrist[1])})">{thumbs_up() if side == "right" else "<g transform=\"scale(-1 1)\">" + thumbs_up() + "</g>"}</g>', ""
    back, front = hand(kind)
    flip = side == "left" and not (90 < abs(ang) <= 180)
    # palm toward the viewer with the thumb up: mirror the hand when it points to the right on the left side etc.
    sy_ = -1 if (side == "left") else 1
    if 90 < abs(ang) <= 180:
        sy_ = -sy_
    tf = f"translate({f(wrist[0])} {f(wrist[1])}) rotate({f(ang)}) scale(1 {sy_})"
    prop = props.get(side, "")
    held = f'<g transform="translate({f(wrist[0])} {f(wrist[1])})">{prop}</g>' if prop else ""
    return sleeve + f'<g transform="{tf}">{back}</g>' + held, (f'<g transform="{tf}">{front}</g>' if front else "")


# ── legs ────────────────────────────────────────────────────
def foot(cx, cy, rot=0) -> str:
    s = [f'<g transform="rotate({rot} {cx} {cy})">',
         f'<ellipse cx="{cx}" cy="{cy}" rx="48" ry="27" fill="{SKIN}" stroke="{INK}" stroke-width="{OL}"/>',
         f'<path d="M {cx-44} {cy+4} Q {cx} {cy+30} {cx+44} {cy+4}" fill="none" stroke="{SKIN_SH}" stroke-width="6"/>']
    for dx in (-24, 0, 24):
        s.append(f'<ellipse cx="{cx+dx}" cy="{cy+12}" rx="10" ry="8" fill="{NAIL}" stroke="{INK}" stroke-width="3.5"/>')
    s.append("</g>")
    return "".join(s)


def legs(kind: str) -> str:
    if kind == "stand":
        lines = [((258, 540), (256, 650)), ((342, 540), (344, 650))]
        feet = [(250, 672, 0), (350, 672, 0)]
    elif kind == "jump":
        lines = [((262, 540), (226, 628)), ((338, 540), (374, 628))]
        feet = [(212, 648, -18), (388, 648, 18)]
    elif kind == "sit":
        lines = [((262, 540), (262, 600)), ((338, 540), (338, 600))]
        feet = [(256, 622, 0), (344, 622, 0)]
    elif kind == "walk":
        lines = [((262, 540), (236, 646)), ((338, 540), (360, 640))]
        feet = [(228, 668, -8), (370, 662, 10)]
    else:
        raise ValueError(kind)
    s = []
    for a, b in lines:
        s.append(capsule(a, b, 66 + 2 * OL, INK))
    for a, b in lines:
        s.append(capsule(a, b, 66, SUIT_SH))
    for cx, cy, rot in feet:
        s.append(foot(cx, cy, rot))
    return "".join(s)


# ── the whole character ─────────────────────────────────────
def body(uid: str) -> str:
    s = [shaded(BODY, SUIT, SUIT_SH, uid + "b", dx=-16, dy=-10)]
    # shirt V, tie, lapels, buttons
    s.append(f'<path d="M 262 356 L 300 446 L 338 356 Z" fill="{SHIRT}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>')
    s.append(f'<path d="M 288 372 L 312 372 L 308 390 L 292 390 Z" fill="{TIE}" stroke="{INK}" stroke-width="4.5" stroke-linejoin="round"/>')
    s.append(f'<path d="M 292 390 L 308 390 L 316 452 L 300 470 L 284 452 Z" fill="{TIE}" stroke="{INK}" stroke-width="4.5" stroke-linejoin="round"/>')
    s.append(f'<path d="M 300 394 L 306 452 L 300 462 Z" fill="{TIE_SH}"/>')
    s.append(f'<path d="M 256 360 L 282 440 L 266 446 M 344 360 L 318 440 L 334 446" fill="none" stroke="{INK}" '
             'stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round"/>')
    s.append(f'<path d="M 300 470 L 300 570" stroke="{INK}" stroke-width="4"/>')
    for y in (500, 532):
        s.append(f'<circle cx="312" cy="{y}" r="7" fill="{TIE}" stroke="{INK}" stroke-width="3.5"/>')
    # breast pocket square
    s.append(f'<path d="M 350 420 L 378 416 L 380 426 L 352 430 Z" fill="#fff" stroke="{INK}" stroke-width="3.5"/>')
    return "".join(s)


def ears(uid: str, flap: float = 0) -> str:
    s = []
    for d_ear, d_in, side in ((EAR_L, EAR_L_IN, "l"), (mirror(EAR_L), mirror(EAR_L_IN), "r")):
        rot = -flap if side == "l" else flap
        cx = 196 if side == "l" else 404
        s.append(f'<g transform="rotate({rot} {cx} 250)">')
        s.append(shaded(d_ear, SKIN, SKIN_SH, f"{uid}ear{side}", dx=10 if side == "l" else -10, dy=-12))
        s.append(shaded(d_in, EAR_IN, EAR_IN_SH, f"{uid}in{side}", dx=8 if side == "l" else -8, dy=-8, stroke=False))
        s.append("</g>")
    return "".join(s)


def head(face: str, trunk_kind: str, uid: str, blink: bool = False, talk: int = 0) -> str:
    cfg = dict(FACES[face])
    if talk:
        cfg["mouth"] = "talk1" if talk == 1 else "talk2"
    if blink and cfg["lid"] >= 0:
        cfg["lid"] = 0.93
        cfg["wink"] = False
    s = []
    s.append(shaded(HEAD, SKIN, SKIN_SH, uid + "h", dx=-10, dy=-16, hi=SKIN_HI, hi_ellipse=(232, 150, 52, 26, -24)))
    # hair tuft
    s.append(f'<path d="M 292 108 C 286 86 292 70 304 64 M 302 106 C 302 88 312 78 324 76 M 284 110 C 272 96 270 84 274 74" '
             f'fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>')
    # cheeks
    s.append(f'<ellipse cx="196" cy="300" rx="26" ry="15" fill="{BLUSH}" opacity=".6"/>'
             f'<ellipse cx="404" cy="300" rx="26" ry="15" fill="{BLUSH}" opacity=".6"/>')
    s.append(mouth(cfg["mouth"]))
    for i, (cx, cy) in enumerate(EYES):
        s.append(eye(i, cx, cy, cfg, uid))
    s.append(brows(cfg["brow"]))
    s.append(trunk(trunk_kind, uid))
    if cfg.get("sweat"):
        s.append(f'<path d="M 436 170 C 424 192 426 208 438 210 C 450 208 452 192 436 170 Z" fill="#8FD3F4" '
                 f'stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>')
    return "".join(s)


DEFAULT_TRUNK = {"open": "up", "o": "lift"}


def character(pose: dict, uid: str = "g", props: dict | None = None) -> str:
    """SVG group (600 x 800 box) for one pose."""
    props = props or {}
    face = pose.get("face", "smug")
    trunk_kind = pose.get("trunk") or DEFAULT_TRUNK.get(FACES[face]["mouth"], "down")
    la, lf = arm("left", pose.get("left", "down"), props)
    ra, rf = arm("right", pose.get("right", "down"), props)
    front_arms = pose.get("front", ())          # arms drawn over the head (e.g. hand on chin)
    s = [ears(uid, pose.get("flap", 0)), legs(pose.get("legs", "stand")), body(uid)]
    if "left" not in front_arms:
        s += [la, lf]
    if "right" not in front_arms:
        s += [ra, rf]
    s.append(head(face, trunk_kind, uid, bool(pose.get("blink")), int(pose.get("talk", 0))))
    if "left" in front_arms:
        s += [la, lf]
    if "right" in front_arms:
        s += [ra, rf]
    tilt = pose.get("tilt", 0)
    lift = pose.get("lift", 0)
    return f'<g transform="translate(0 {-lift}) rotate({tilt} 300 690)">' + "".join(s) + "</g>"


POSES = {
    "explain":  {"face": "smug", "left": "hip", "right": "point_up"},
    "happy":    {"face": "happy", "left": "down", "right": "wave"},
    "joy":      {"face": "joy", "left": "cheer", "right": "cheer", "legs": "jump", "lift": 40},
    "think":    {"face": "think", "left": "hip", "right": "chin", "front": ("right",)},
    "shocked":  {"face": "shocked", "left": "shrug", "right": "shrug", "tilt": -3},
    "worried":  {"face": "worried", "left": "down", "right": "down"},
    "shrug":    {"face": "worried", "left": "shrug", "right": "shrug"},
    "thumbs":   {"face": "proud", "left": "hip", "right": "thumb"},
    "wink":     {"face": "wink", "left": "hip", "right": "thumb"},
    "present":  {"face": "happy", "left": "down", "right": "present"},
    "sleepy":   {"face": "sleepy", "left": "down", "right": "down", "legs": "sit"},
    "hold":     {"face": "happy", "left": "hip", "right": "hold_up"},
    "excited":  {"face": "excited", "left": "cheer", "right": "point_side"},
}


def svg(pose: dict | str, props: dict | None = None, uid: str = "g", w: int = 600, h: int = 800) -> str:
    if isinstance(pose, str):
        pose = POSES[pose]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800" width="{w}" height="{h}">'
            + character(pose, uid, props) + "</svg>")
