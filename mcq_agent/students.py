"""The two students of the story explainers: original cartoon characters drawn as SVG in the elephant's
style (dark outline, cel shading, big eyes), seen from the waist up in a 600 x 800 box.

    character(who, pose, uid, talk=0, blink=False)   the student facing us; talk 0/1/2 = mouth shut/half/open
    back_view(who, uid)                               the same student seen from behind (over-the-shoulder shots)

A pose is {"face", "left", "right", "tilt", "look", "front"} like the elephant's; POSES has ready ones.
"""

from __future__ import annotations

import math

from .elephant import INK, OL, blob, capsule, f, shaded

CAST = {
    "girl": {"skin": "#C98C65", "skin_sh": "#AB6F4E", "hair": "#2B2030", "hair_sh": "#191219", "hair_hi": "#4B3B52",
             "top": "#E8576B", "top_sh": "#C4405A", "trim": "#F5B700", "hair_style": "braid", "glasses": False},
    "boy": {"skin": "#B4774E", "skin_sh": "#93593A", "hair": "#211C27", "hair_sh": "#120F16", "hair_hi": "#433A4D",
            "top": "#3F7FD9", "top_sh": "#2C61B3", "trim": "#FFFFFF", "hair_style": "short", "glasses": True},
}
NAMES = tuple(CAST)

HEAD = ("M 300 116 C 382 116 436 176 436 258 C 436 346 378 410 300 410 "
        "C 222 410 164 346 164 258 C 164 176 218 116 300 116 Z")
TORSO = ("M 300 438 C 232 438 172 450 132 478 C 100 502 88 546 84 600 L 70 820 L 530 820 L 516 600 "
         "C 512 546 500 502 468 478 C 428 450 368 438 300 438 Z")
EYES = [(252, 274), (348, 274)]
SHOULDERS = {"left": (176, 500), "right": (424, 500)}

FACES = {
    #          lid, pupil look, pupil r, brows, mouth
    "smile":    dict(lid=0.0, look=(0, 2), pr=12, brow="up", mouth="smile"),
    "happy":    dict(lid=0.0, look=(0, 2), pr=12, brow="up", mouth="grin"),
    "joy":      dict(lid=-1, look=(0, 0), pr=12, brow="up", mouth="grin"),
    "excited":  dict(lid=0.0, look=(0, -2), pr=11, brow="high", mouth="grin", scale=1.08),
    "shocked":  dict(lid=0.0, look=(0, 0), pr=7, brow="high", mouth="o", scale=1.12),
    "worried":  dict(lid=0.15, look=(-2, 4), pr=12, brow="sad", mouth="wavy", sweat=True),
    "confused": dict(lid=0.0, look=(6, -4), pr=12, brow="raise", mouth="hmm"),
    "think":    dict(lid=0.1, look=(8, -10), pr=11, brow="raise", mouth="hmm"),
    "doubt":    dict(lid=0.35, look=(-6, 2), pr=12, brow="flat", mouth="flat"),
    "aha":      dict(lid=0.0, look=(0, -6), pr=11, brow="high", mouth="grin", scale=1.06),
    "listen":   dict(lid=0.05, look=(0, 2), pr=12, brow="up", mouth="smile"),
}


# ── face ────────────────────────────────────────────────────
def eye(i, cx, cy, cfg, uid, c, look=None) -> str:
    sc = cfg.get("scale", 1.0)
    rx, ry = 23 * sc, 29 * sc
    if cfg["lid"] == -1:
        return (f'<path d="M {f(cx-20)} {f(cy+6)} Q {f(cx)} {f(cy-20)} {f(cx+20)} {f(cy+6)}" fill="none" '
                f'stroke="{INK}" stroke-width="7" stroke-linecap="round"/>')
    if cfg["lid"] >= 0.9:                       # blink: a closed eye is one curved line
        return (f'<path d="M {f(cx-rx)} {f(cy+2)} Q {f(cx)} {f(cy+16)} {f(cx+rx)} {f(cy+2)}" fill="none" '
                f'stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
                f'<path d="M {f(cx + (-1 if i == 0 else 1) * rx)} {f(cy+2)} l {(-1 if i == 0 else 1) * 10} -6" '
                f'stroke="{INK}" stroke-width="5" stroke-linecap="round"/>')
    dx, dy = look or cfg["look"]
    pr = cfg["pr"]
    s = [f'<clipPath id="{uid}e{i}"><ellipse cx="{cx}" cy="{cy}" rx="{f(rx)}" ry="{f(ry)}"/></clipPath>',
         f'<ellipse cx="{cx}" cy="{cy}" rx="{f(rx)}" ry="{f(ry)}" fill="#fff"/>',
         f'<g clip-path="url(#{uid}e{i})">',
         f'<ellipse cx="{f(cx+dx)}" cy="{f(cy+dy)}" rx="{f(pr)}" ry="{f(pr*1.18)}" fill="{INK}"/>',
         f'<circle cx="{f(cx+dx-pr*0.35)}" cy="{f(cy+dy-pr*0.45)}" r="{f(max(2.5, pr*0.34))}" fill="#fff"/>']
    lid = cfg["lid"]
    if lid > 0:
        y = cy - ry + 2 * ry * lid
        s.append(f'<rect x="{f(cx-rx-4)}" y="{f(cy-ry-6)}" width="{f(2*rx+8)}" height="{f(y-(cy-ry-6))}" fill="{c["skin"]}"/>')
        s.append(f'<path d="M {f(cx-rx-4)} {f(y+3)} Q {f(cx)} {f(y-4)} {f(cx+rx+4)} {f(y+3)}" fill="none" '
                 f'stroke="{INK}" stroke-width="5" stroke-linecap="round"/>')
    s.append("</g>")
    s.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{f(rx)}" ry="{f(ry)}" fill="none" stroke="{INK}" stroke-width="5"/>')
    # lashes on the outer corners
    s.append(f'<path d="M {f(cx + (-1 if i == 0 else 1) * (rx - 4))} {f(cy - ry + 8)} l {(-1 if i == 0 else 1) * 12} -8" '
             f'stroke="{INK}" stroke-width="5" stroke-linecap="round"/>')
    return "".join(s)


def brows(kind, color) -> str:
    shapes = {
        "flat":  (-20, -46, 0, -50, 20, -46),
        "up":    (-20, -48, 0, -58, 20, -50),
        "high":  (-20, -58, 0, -72, 20, -60),
        "sad":   (-22, -64, 0, -58, 20, -46),
        "raise": (-20, -52, 0, -62, 20, -54),
    }[kind]
    out = []
    for side, (cx, cy) in ((-1, EYES[0]), (1, EYES[1])):
        x0, y0, x1, y1, x2, y2 = shapes
        if side == -1:
            x0, x2, y0, y2, x1 = -x2, -x0, y2, y0, -x1
        if kind == "raise" and side == -1:
            y0, y1, y2 = y0 + 10, y1 + 10, y2 + 10
        out.append(f'<path d="M {f(cx+x0)} {f(cy+y0)} Q {f(cx+x1)} {f(cy+y1)} {f(cx+x2)} {f(cy+y2)}" fill="none" '
                   f'stroke="{color}" stroke-width="11" stroke-linecap="round"/>')
    return "".join(out)


DARK, TONGUE = "#5A1F2E", "#F07C93"


def mouth(kind: str) -> str:
    if kind == "smile":
        return f'<path d="M 266 344 Q 300 372 334 344" fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
    if kind == "grin":
        return (f'<path d="M 258 338 Q 300 398 342 338 Q 300 350 258 338 Z" fill="{DARK}" stroke="{INK}" '
                f'stroke-width="5.5" stroke-linejoin="round"/>'
                f'<path d="M 266 343 Q 300 352 334 343 L 330 351 Q 300 358 270 351 Z" fill="#fff"/>'
                f'<path d="M 280 372 Q 300 386 320 372 Q 300 364 280 372 Z" fill="{TONGUE}"/>')
    if kind == "o":
        return (f'<ellipse cx="300" cy="356" rx="17" ry="21" fill="{DARK}" stroke="{INK}" stroke-width="5.5"/>'
                f'<ellipse cx="300" cy="366" rx="9" ry="6" fill="{TONGUE}"/>')
    if kind == "flat":
        return f'<path d="M 274 352 L 326 352" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
    if kind == "wavy":
        return (f'<path d="M 266 354 Q 278 344 290 354 Q 300 362 310 354 Q 322 344 334 354" fill="none" '
                f'stroke="{INK}" stroke-width="6" stroke-linecap="round"/>')
    if kind == "hmm":
        return f'<path d="M 284 354 Q 308 344 330 350" fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
    if kind == "talk1":
        return (f'<path d="M 270 344 Q 300 372 330 344 Q 300 350 270 344 Z" fill="{DARK}" stroke="{INK}" '
                f'stroke-width="5.5" stroke-linejoin="round"/>')
    if kind == "talk2":
        return (f'<path d="M 264 340 Q 300 396 336 340 Q 300 348 264 340 Z" fill="{DARK}" stroke="{INK}" '
                f'stroke-width="5.5" stroke-linejoin="round"/>'
                f'<path d="M 282 372 Q 300 386 318 372 Q 300 364 282 372 Z" fill="{TONGUE}"/>')
    return ""


# ── hair ────────────────────────────────────────────────────
GIRL_BACK = ("M 300 92 C 406 92 464 164 462 262 C 460 340 472 410 456 462 C 444 494 404 500 382 486 "
             "L 218 486 C 196 500 156 494 144 462 C 128 410 140 340 138 262 C 136 164 194 92 300 92 Z")
GIRL_FRONT = ("M 150 290 C 136 170 208 96 300 96 C 392 96 464 170 450 290 C 446 236 428 200 396 178 "
              "C 362 156 322 152 300 130 C 278 152 238 156 204 178 C 172 200 154 236 150 290 Z")
BOY_BACK = ("M 300 86 C 412 86 462 160 452 262 L 440 262 L 160 262 L 148 262 C 138 160 188 86 300 86 Z")
BOY_FRONT = ("M 156 272 C 140 168 204 88 302 86 C 402 84 462 160 446 272 C 440 232 428 206 408 190 "
             "C 400 210 384 218 364 216 C 372 200 372 184 364 170 C 342 194 304 204 266 198 "
             "C 284 186 292 172 294 158 C 266 184 228 196 196 196 C 176 214 162 240 156 272 Z")


def hair_back(c, uid) -> str:
    d = GIRL_BACK if c["hair_style"] == "braid" else BOY_BACK
    return shaded(d, c["hair"], c["hair_sh"], uid + "hb", dx=-10, dy=-8)


def hair_front(c, uid) -> str:
    if c["hair_style"] == "braid":
        s = shaded(GIRL_FRONT, c["hair"], c["hair_sh"], uid + "hf", dx=8, dy=-10, hi=c["hair_hi"],
                   hi_ellipse=(236, 128, 46, 14, -22))
        # a yellow clip on her left side
        s += (f'<rect x="196" y="164" width="52" height="18" rx="9" transform="rotate(-28 222 173)" fill="{c["trim"]}" '
              f'stroke="{INK}" stroke-width="4.5"/>')
        return s
    return shaded(BOY_FRONT, c["hair"], c["hair_sh"], uid + "hf", dx=8, dy=-10, hi=c["hair_hi"],
                  hi_ellipse=(250, 118, 50, 14, -18))


def braid(c) -> str:
    """Over her left shoulder (the viewer's right), in front of the top."""
    s = []
    pts = [(420 + 8 * math.sin(k * 0.9), 400 + 44 * k) for k in range(6)]
    for i, (x, y) in enumerate(pts):
        s.append(f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{30 - i}" ry="30" transform="rotate({-14 if i % 2 else 14} {f(x)} {f(y)})" '
                 f'fill="{c["hair"]}" stroke="{INK}" stroke-width="{OL - 1}"/>')
        s.append(f'<path d="M {f(x-14)} {f(y-12)} Q {f(x)} {f(y+2)} {f(x+16)} {f(y-6)}" fill="none" stroke="{c["hair_hi"]}" '
                 'stroke-width="4" stroke-linecap="round"/>')
    x, y = pts[-1]
    s.append(f'<rect x="{f(x-20)}" y="{f(y+22)}" width="40" height="16" rx="8" fill="{c["trim"]}" stroke="{INK}" stroke-width="4.5"/>')
    s.append(f'<path d="M {f(x-16)} {f(y+38)} Q {f(x-20)} {f(y+70)} {f(x)} {f(y+84)} Q {f(x+18)} {f(y+70)} {f(x+16)} {f(y+38)} Z" '
             f'fill="{c["hair"]}" stroke="{INK}" stroke-width="{OL - 1}" stroke-linejoin="round"/>')
    return "".join(s)


# ── body ────────────────────────────────────────────────────
def torso(who, c, uid) -> str:
    s = [shaded(TORSO, c["top"], c["top_sh"], uid + "t", dx=-14, dy=-10)]
    if who == "girl":
        # kurta: round neck with yellow piping, a short placket, and an ID card on a lanyard
        s.append(f'<path d="M 254 442 Q 300 512 346 442 Z" fill="{c["skin_sh"]}" stroke="{INK}" stroke-width="5"/>')
        s.append(f'<path d="M 250 442 Q 300 520 350 442" fill="none" stroke="{c["trim"]}" stroke-width="9"/>')
        s.append(f'<path d="M 250 442 Q 300 520 350 442" fill="none" stroke="{INK}" stroke-width="2.5" '
                 'transform="translate(0 6)" opacity=".6"/>')
        s.append(f'<path d="M 300 486 L 300 600" stroke="{c["trim"]}" stroke-width="8"/>')
        for y in (520, 556, 592):
            s.append(f'<circle cx="300" cy="{y}" r="6" fill="#fff" stroke="{INK}" stroke-width="3"/>')
        s.append(id_card(208, 640, -4))
    else:
        # hoodie: hood folded round the neck, drawstrings, front pocket
        s.append(f'<path d="M 230 446 C 236 500 364 500 370 446 C 340 470 260 470 230 446 Z" fill="{c["skin_sh"]}" '
                 f'stroke="{INK}" stroke-width="5"/>')
        s.append(f'<path d="M 196 452 C 214 530 386 530 404 452 C 398 488 202 488 196 452 Z" fill="{c["top_sh"]}" '
                 f'stroke="{INK}" stroke-width="5.5" stroke-linejoin="round"/>')
        for x, x2 in ((272, 266), (328, 334)):
            s.append(f'<path d="M {x} 500 L {x2} 590" stroke="#fff" stroke-width="7" stroke-linecap="round"/>'
                     f'<rect x="{x2-7}" y="586" width="14" height="22" rx="5" fill="{c["trim"]}" stroke="{INK}" stroke-width="3.5"/>')
        s.append(f'<path d="M 170 700 L 430 700 L 456 800 L 144 800 Z" fill="{c["top_sh"]}" opacity=".55"/>'
                 f'<path d="M 170 700 L 430 700" stroke="{INK}" stroke-width="4.5" stroke-linecap="round"/>')
    return "".join(s)


def id_card(x, y, rot) -> str:
    return (f'<path d="M 268 450 L {x+30} {y}" stroke="#2F7DBA" stroke-width="6"/>'
            f'<g transform="rotate({rot} {x+30} {y+50})">'
            f'<rect x="{x}" y="{y}" width="64" height="88" rx="8" fill="#fff" stroke="{INK}" stroke-width="4"/>'
            f'<rect x="{x}" y="{y}" width="64" height="20" rx="6" fill="#2F7DBA"/>'
            f'<circle cx="{x+32}" cy="{y+44}" r="12" fill="#C8CED8"/>'
            f'<path d="M {x+14} {y+68} L {x+50} {y+68} M {x+18} {y+78} L {x+46} {y+78}" stroke="#C8CED8" stroke-width="5" '
            'stroke-linecap="round"/></g>')


def ears(c) -> str:
    s = []
    for cx, side in ((168, -1), (432, 1)):
        s.append(f'<ellipse cx="{cx}" cy="280" rx="22" ry="30" fill="{c["skin"]}" stroke="{INK}" stroke-width="{OL}"/>')
        s.append(f'<path d="M {cx + side * 4} 266 Q {cx + side * 12} 280 {cx + side * 2} 296" fill="none" stroke="{c["skin_sh"]}" '
                 'stroke-width="5" stroke-linecap="round"/>')
    return "".join(s)


def glasses() -> str:
    s = []
    for cx, cy in EYES:
        s.append(f'<rect x="{cx-40}" y="{cy-34}" width="80" height="66" rx="22" fill="#DDEEFF" fill-opacity=".18" '
                 f'stroke="{INK}" stroke-width="6.5"/>')
    s.append(f'<path d="M 292 268 Q 300 260 308 268" fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>'
             f'<path d="M 212 262 L 176 256 M 388 262 L 424 256" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>')
    return "".join(s)


def head(who, face, uid, talk=0, blink=False, look=None) -> str:
    c = CAST[who]
    cfg = dict(FACES[face])
    if blink and cfg["lid"] >= 0:
        cfg["lid"] = 0.93
    s = [ears(c),
         shaded(HEAD, c["skin"], c["skin_sh"], uid + "h", dx=-10, dy=-14),
         f'<ellipse cx="208" cy="326" rx="22" ry="12" fill="#F27D86" opacity=".45"/>'
         f'<ellipse cx="392" cy="326" rx="22" ry="12" fill="#F27D86" opacity=".45"/>',
         f'<path d="M 302 290 Q 290 314 306 318" fill="none" stroke="{c["skin_sh"]}" stroke-width="5.5" stroke-linecap="round"/>']
    mk = cfg["mouth"] if talk == 0 else ("talk1" if talk == 1 else "talk2")
    if talk and cfg["mouth"] == "grin":
        mk = "talk1" if talk == 1 else "grin"
    s.append(mouth(mk))
    for i, (cx, cy) in enumerate(EYES):
        s.append(eye(i, cx, cy, cfg, uid, c, look))
    if c["glasses"]:
        s.append(glasses())
    s.append(hair_front(c, uid))
    s.append(brows(cfg["brow"], c["hair"]))
    if cfg.get("sweat"):
        s.append(f'<path d="M 420 186 C 408 208 410 222 422 224 C 434 222 436 208 420 186 Z" fill="#8FD3F4" '
                 f'stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>')
    return "".join(s)


# ── arms and hands ──────────────────────────────────────────
def hand(kind, color) -> tuple[str, str]:
    """(svg, front svg) with the wrist at 0,0, pointing to +x, thumb toward -y."""
    if kind == "open":
        return blob([("e", 22, 0, 22, 21), ("l", 32, -13, 50, -20, 13), ("l", 36, -2, 56, -2, 13),
                     ("l", 32, 10, 48, 16, 13), ("l", 12, -14, 4, -30, 13)], color), ""
    if kind == "point":
        crease = (f'<path d="M 28 4 Q 36 6 40 0 M 24 13 Q 32 15 38 9" fill="none" stroke="{INK}" '
                  'stroke-width="3" stroke-linecap="round"/>')
        return blob([("c", 20, 0, 21), ("l", 28, -9, 64, -14, 13), ("l", 10, -13, 22, -22, 12)], color) + crease, ""
    if kind == "fist":
        crease = (f'<path d="M 32 -7 Q 40 -5 40 -1 M 34 4 Q 42 6 40 10" fill="none" stroke="{INK}" '
                  'stroke-width="3" stroke-linecap="round"/>')
        return blob([("c", 20, 0, 22), ("l", 12, -14, 27, -20, 13)], color) + crease, ""
    if kind == "hold":
        return blob([("c", 20, 0, 21)], color), blob([("l", 28, -12, 36, -12, 14), ("l", 30, 0, 38, 0, 14),
                                                      ("l", 28, 12, 36, 12, 14)], color)
    raise ValueError(kind)


def thumbs_up(color) -> str:
    crease = (f'<path d="M 4 -32 L 18 -32 M 4 -21 L 18 -21 M 4 -10 L 16 -10" fill="none" stroke="{INK}" '
              'stroke-width="3" stroke-linecap="round"/>')
    return blob([("e", 0, -24, 22, 20), ("l", -5, -40, -5, -66, 15)], color) + crease


ARMS = {
    "down":     ((488, 640), (500, 860), "fist"),
    "raise":    ((506, 470), (520, 332), "open"),
    "wave":     ((512, 474), (548, 350), "open"),
    "chin":     ((400, 700), (338, 452), "fist"),
    "shrug":    ((520, 640), (586, 566), "open"),
    "point":    ((506, 600), (584, 516), "point"),
    "point_up": ((500, 548), (540, 400), "point"),
    "thumb":    ((502, 668), (522, 580), "thumb"),
    "cheer":    ((526, 450), (552, 316), "fist"),
    "hold":     ((480, 690), (430, 610), "hold"),
    "hip":      ((520, 650), (470, 760), "fist"),
}


def arm(side, spec, c, props) -> tuple[str, str]:
    if isinstance(spec, str):
        spec = ARMS[spec]
    elbow, wrist, kind = spec
    if side == "left":
        elbow, wrist = (600 - elbow[0], elbow[1]), (600 - wrist[0], wrist[1])
    sx, sy = SHOULDERS[side]
    w = 56
    d = f"M {sx} {sy} Q {f(elbow[0])} {f(elbow[1])} {f(wrist[0])} {f(wrist[1])}"
    ang = math.degrees(math.atan2(wrist[1] - elbow[1], wrist[0] - elbow[0]))
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    c0 = (wrist[0] - ux * 12, wrist[1] - uy * 12)
    sleeve = (f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{f(w+2*OL)}" stroke-linecap="round"/>'
              f'<path d="{d}" fill="none" stroke="{c["top"]}" stroke-width="{w}" stroke-linecap="round"/>'
              + capsule(c0, wrist, w - 4, c["top_sh"]))
    if kind == "thumb":
        th = thumbs_up(c["skin"])
        th = th if side == "right" else f'<g transform="scale(-1 1)">{th}</g>'
        return sleeve + f'<g transform="translate({f(wrist[0])} {f(wrist[1])})">{th}</g>', ""
    back, front = hand(kind, c["skin"])
    sy_ = -1 if side == "left" else 1
    if 90 < abs(ang) <= 180:
        sy_ = -sy_
    tf = f"translate({f(wrist[0])} {f(wrist[1])}) rotate({f(ang)}) scale(1 {sy_})"
    prop = props.get(side, "")
    held = f'<g transform="translate({f(wrist[0])} {f(wrist[1])})">{prop}</g>' if prop else ""
    return sleeve + f'<g transform="{tf}">{back}</g>' + held, (f'<g transform="{tf}">{front}</g>' if front else "")


# ── whole character ─────────────────────────────────────────
POSES = {
    "talk":     {"face": "smile", "left": "down", "right": "shrug"},
    "ask":      {"face": "confused", "left": "down", "right": "raise", "tilt": -4},
    "think":    {"face": "think", "left": "down", "right": "chin", "front": ("right",), "tilt": 4},
    "shocked":  {"face": "shocked", "left": "shrug", "right": "shrug"},
    "worried":  {"face": "worried", "left": "down", "right": "down", "tilt": -3},
    "happy":    {"face": "happy", "left": "down", "right": "thumb"},
    "excited":  {"face": "excited", "left": "down", "right": "cheer"},
    "aha":      {"face": "aha", "left": "down", "right": "point_up"},
    "shrug":    {"face": "confused", "left": "shrug", "right": "shrug"},
    "listen":   {"face": "listen", "left": "down", "right": "down", "tilt": 3},
    "doubt":    {"face": "doubt", "left": "down", "right": "chin", "front": ("right",)},
    "point":    {"face": "smile", "left": "down", "right": "point"},
}


def character(who, pose, uid="s", talk=0, blink=False, props=None) -> str:
    """SVG group (600 x 800 box, the bottom cut off by the frame) for one student in one pose."""
    p = dict(POSES[pose] if isinstance(pose, str) else pose)
    c = CAST[who]
    props = props or {}
    la, lf = arm("left", p.get("left", "down"), c, props)
    ra, rf = arm("right", p.get("right", "down"), c, props)
    front = p.get("front", ())
    neck = (f'<path d="M 266 380 L 266 452 Q 300 474 334 452 L 334 380 Z" fill="{c["skin_sh"]}" stroke="{INK}" '
            f'stroke-width="{OL}"/>')
    s = [hair_back(c, uid), neck, torso(who, c, uid)]
    if c["hair_style"] == "braid":
        s.append(braid(c))
    for side, a, fr in (("left", la, lf), ("right", ra, rf)):
        if side not in front:
            s += [a, fr]
    tilt = p.get("tilt", 0)
    s.append(f'<g transform="rotate({tilt} 300 420)">' + head(who, p.get("face", "smile"), uid, talk, blink, p.get("look")) + "</g>")
    for side, a, fr in (("left", la, lf), ("right", ra, rf)):
        if side in front:
            s += [a, fr]
    return "<g>" + "".join(s) + "</g>"


def back_view(who, uid="b") -> str:
    """The student from behind: back of the head and shoulders (for shots over their shoulders)."""
    c = CAST[who]
    s = [shaded(TORSO, c["top"], c["top_sh"], uid + "t", dx=14, dy=-10)]
    if who == "boy":                                   # the hood lying on the back
        s.append(f'<path d="M 214 452 C 220 560 380 560 386 452 C 360 480 240 480 214 452 Z" fill="{c["top_sh"]}" '
                 f'stroke="{INK}" stroke-width="5.5" stroke-linejoin="round"/>')
    s.append(f'<path d="M 266 380 L 266 452 L 334 452 L 334 380 Z" fill="{c["skin_sh"]}" stroke="{INK}" stroke-width="{OL}"/>')
    s.append(ears(c))
    head_d = HEAD
    if c["hair_style"] == "braid":
        s.append(shaded(head_d, c["hair"], c["hair_sh"], uid + "h", dx=10, dy=-12, hi=c["hair_hi"],
                        hi_ellipse=(350, 150, 60, 18, 20)))
        s.append(f'<path d="M 300 120 L 300 300" stroke="{c["hair_sh"]}" stroke-width="5" stroke-linecap="round"/>')
        pts = [(300 + 6 * math.sin(k), 400 + 42 * k) for k in range(5)]
        for i, (x, y) in enumerate(pts):
            s.append(f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{28 - i}" ry="28" fill="{c["hair"]}" stroke="{INK}" stroke-width="{OL - 1}"/>')
        x, y = pts[-1]
        s.append(f'<rect x="{f(x-18)}" y="{f(y+20)}" width="36" height="15" rx="7" fill="{c["trim"]}" stroke="{INK}" stroke-width="4"/>')
    else:
        s.append(shaded(head_d, c["hair"], c["hair_sh"], uid + "h", dx=10, dy=-12, hi=c["hair_hi"],
                        hi_ellipse=(350, 150, 60, 18, 20)))
        s.append(f'<path d="M 230 372 Q 300 392 370 372" fill="none" stroke="{c["hair_sh"]}" stroke-width="5" stroke-linecap="round"/>')
    return "<g>" + "".join(s) + "</g>"


def svg(who, pose="talk", talk=0, blink=False, w=600, h=800) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800" width="{w}" height="{h}">'
            + character(who, pose, "p", talk, blink) + "</svg>")
