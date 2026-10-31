"""Places and board pictures for the story explainers (1080 x 1920 SVG): the classroom with a chalkboard
(the elephant teaches there, the two students watch from the front row) and the students' desk.

Board pictures are drawn inside the chalkboard: BOARD_KINDS lists them and the fields each takes.
"""

from __future__ import annotations

import math

from . import cartoon_props as P
from .elephant import INK, TIE as YELLOW

W, H = 1080, 1920
CHALK = "'Caveat', 'Patrick Hand', 'Poppins', sans-serif"
CHALK_WHITE, CHALK_YELLOW, CHALK_PINK, CHALK_BLUE = "#F4F1E8", "#FFD75E", "#FF9DB5", "#9FD8FF"
BOARD = (74, 239, 1006, 951)               # inner chalkboard
BOARD_CX, BOARD_CY = 540, 615              # centre of the drawing area (below the tag line)
DESK_TOP = 1530


def at(svg: str, x, y, s=1.0, rot=0) -> str:
    return f'<g transform="translate({x} {y}) rotate({rot}) scale({s})">{svg}</g>'


def chalk(x, y, s, size, color=CHALK_WHITE, anchor="middle", weight=700) -> str:
    return P.text(x, y, s, size, color=color, weight=weight, anchor=anchor, font=CHALK)


def fit(text: str, size: int, width: float, k=0.5) -> int:
    return int(max(28, min(size, width / max(1, len(text.replace("^", "")) * k))))


# ── places ──────────────────────────────────────────────────
def _wall(top="#F5E7D2", bottom="#E9D3B2", uid="w") -> str:
    return (f'<defs><linearGradient id="{uid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient></defs>'
            f'<rect width="{W}" height="{H}" fill="url(#{uid})"/>'
            + "".join(f'<rect x="{x}" y="0" width="34" height="{H}" fill="#fff" opacity=".07"/>' for x in range(0, W, 90)))


def classroom(tag: str = "") -> str:
    """The wall with the chalkboard (board drawings are separate layers)."""
    x0, y0, x1, y1 = BOARD
    s = [_wall(uid="wb")]
    s.append(f'<rect x="0" y="1460" width="{W}" height="{H-1460}" fill="#C99566"/>'
             f'<rect x="0" y="1446" width="{W}" height="22" fill="#E2B78A" stroke="{INK}" stroke-width="4"/>')
    s.append(f'<rect x="{x0-24}" y="{y0-24}" width="{x1-x0+48}" height="{y1-y0+48}" rx="26" fill="#9A6A42" stroke="{INK}" stroke-width="7"/>'
             f'<rect x="{x0-12}" y="{y0-12}" width="{x1-x0+24}" height="{y1-y0+24}" rx="18" fill="#7E5432"/>')
    s.append('<defs><radialGradient id="cb" cx=".5" cy=".45" r=".75"><stop offset="0" stop-color="#3B6B57"/>'
             '<stop offset="1" stop-color="#25493B"/></radialGradient></defs>')
    s.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="10" fill="url(#cb)" stroke="{INK}" stroke-width="5"/>')
    for cx, cy, rx, ry, rot in ((300, 420, 210, 46, -8), (760, 820, 240, 40, 6), (820, 380, 150, 30, 10), (240, 840, 160, 30, -4)):
        s.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" transform="rotate({rot} {cx} {cy})" fill="#fff" opacity=".045"/>')
    # chalk tray with chalk and a duster
    s.append(f'<rect x="{x0+20}" y="{y1+22}" width="{x1-x0-40}" height="26" rx="8" fill="#B07A4C" stroke="{INK}" stroke-width="5"/>')
    for x, col in ((220, "#fff"), (262, YELLOW), (300, "#FF9DB5")):
        s.append(f'<rect x="{x}" y="{y1+10}" width="34" height="13" rx="6" fill="{col}" stroke="{INK}" stroke-width="3"/>')
    s.append(f'<rect x="{x1-230}" y="{y1-4}" width="120" height="30" rx="8" fill="#3E5C8A" stroke="{INK}" stroke-width="4"/>'
             f'<rect x="{x1-230}" y="{y1+14}" width="120" height="12" rx="4" fill="#D9D2C3" stroke="{INK}" stroke-width="3"/>')
    if tag:
        s.append(chalk(x0 + 34, y0 + 46, tag, 44, CHALK_YELLOW, anchor="start"))
        s.append(f'<path d="M {x0+34} {y0+78} q 140 -8 {min(560, len(tag)*19)} 0" fill="none" stroke="{CHALK_YELLOW}" '
                 'stroke-width="4" stroke-linecap="round" opacity=".7"/>')
    return "".join(s)


def study_room() -> str:
    """The students' side of the room: a window and a pinboard behind their desk."""
    s = [_wall("#F2E4CF", "#E4CDAB", "ws")]
    # window
    s.append('<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#A9DCF7"/>'
             '<stop offset="1" stop-color="#E4F5FF"/></linearGradient></defs>')
    s.append(f'<rect x="60" y="250" width="440" height="560" rx="16" fill="#FFF8EC" stroke="{INK}" stroke-width="7"/>'
             f'<rect x="88" y="278" width="384" height="504" rx="6" fill="url(#sky)" stroke="{INK}" stroke-width="4"/>')
    s.append(f'<circle cx="400" cy="350" r="40" fill="#FFE07A" opacity=".9"/>'
             f'<path d="M 88 650 L 150 600 L 150 520 L 230 520 L 230 610 L 300 580 L 300 650 Z" fill="#C8D9E8"/>'
             f'<path d="M 88 700 C 120 640 200 640 230 690 C 260 630 360 630 380 700 C 410 660 460 670 472 700 L 472 782 L 88 782 Z" '
             f'fill="#7CC27E" stroke="{INK}" stroke-width="4"/>')
    s.append(f'<path d="M 280 278 L 280 782 M 88 530 L 472 530" stroke="#FFF8EC" stroke-width="14"/>'
             f'<path d="M 280 278 L 280 782 M 88 530 L 472 530" stroke="{INK}" stroke-width="3" opacity=".35"/>')
    s.append(f'<rect x="44" y="806" width="472" height="26" rx="8" fill="#FFF8EC" stroke="{INK}" stroke-width="6"/>')
    # pinboard with notes
    s.append(f'<rect x="590" y="300" width="420" height="380" rx="16" fill="#D7A46A" stroke="{INK}" stroke-width="7"/>'
             f'<rect x="608" y="318" width="384" height="344" rx="8" fill="#E2B57E"/>')
    notes = [(650, 350, -6, "#FFE27A", "₹"), (800, 340, 5, "#FFB3C7", "%"), (900, 470, -4, "#B8E2FF", "Σ"),
             (660, 500, 4, "#C5F0B8", "P&L"), (790, 520, -3, "#FFE27A", "Exam!")]
    for x, y, rot, col, label in notes:
        s.append(f'<g transform="rotate({rot} {x+60} {y+60})"><rect x="{x}" y="{y}" width="120" height="112" fill="{col}" '
                 f'stroke="{INK}" stroke-width="4"/>{P.text(x+60, y+62, label, 44 if len(label) < 3 else 30, font=CHALK)}'
                 f'<circle cx="{x+60}" cy="{y+12}" r="9" fill="{P.RED}" stroke="{INK}" stroke-width="3"/></g>')
    # shelf with books
    s.append(f'<rect x="600" y="740" width="400" height="20" rx="6" fill="#B07A4C" stroke="{INK}" stroke-width="5"/>')
    x = 620
    for wbk, hbk, col in ((40, 110, "#E5484D"), (34, 96, "#2F7DBA"), (46, 120, "#F5B700"), (36, 100, "#2FA85A"),
                          (40, 112, "#7B5CD6"), (30, 90, "#E9ECF2")):
        s.append(f'<rect x="{x}" y="{740-hbk}" width="{wbk}" height="{hbk}" rx="4" fill="{col}" stroke="{INK}" stroke-width="4"/>'
                 f'<path d="M {x+6} {760-hbk} L {x+wbk-6} {760-hbk}" stroke="#fff" stroke-width="4" opacity=".7"/>')
        x += wbk + 4
    s.append(f'<g transform="rotate(-18 {x+60} 700)"><rect x="{x+30}" y="640" width="36" height="104" rx="4" fill="#E58B3A" '
             f'stroke="{INK}" stroke-width="4"/></g>')
    s.append(f'<rect x="0" y="1180" width="{W}" height="{H-1180}" fill="#D3A57A"/>'
             f'<rect x="0" y="1168" width="{W}" height="20" fill="#E8C29A" stroke="{INK}" stroke-width="4"/>')
    return "".join(s)


def desk() -> str:
    """The front of the students' desk, drawn over them (it hides their lower half)."""
    top = DESK_TOP
    s = [f'<path d="M -20 {top} L {W+20} {top} L {W+20} {top+70} L -20 {top+70} Z" fill="#E0A766" stroke="{INK}" stroke-width="7"/>',
         f'<rect x="-20" y="{top+70}" width="{W+40}" height="{H-top}" fill="#B9773F" stroke="{INK}" stroke-width="7"/>',
         f'<path d="M -20 {top+16} L {W+20} {top+16}" stroke="#F0C58C" stroke-width="6" opacity=".8"/>']
    # an open book (left), a pen, a calculator (right)
    s.append(f'<g transform="translate(150 {top-6}) rotate(-4)">'
             f'<path d="M -120 0 Q -60 -30 0 -6 Q 60 -30 120 0 L 120 34 Q 60 6 0 30 Q -60 6 -120 34 Z" fill="#fff" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
             f'<path d="M 0 -6 L 0 30" stroke="{INK}" stroke-width="4"/></g>')
    s.append(f'<g transform="translate(930 {top-8}) rotate(6)"><rect x="-70" y="-26" width="140" height="56" rx="12" fill="#5A6074" '
             f'stroke="{INK}" stroke-width="5"/><rect x="-54" y="-16" width="108" height="20" rx="5" fill="#CFE8C8"/></g>')
    return "".join(s)


# ── board pictures ──────────────────────────────────────────
# kind -> {field: (type, limit)}; type: text (max chars), lines (max lines, max chars), word, card
BOARD_KINDS = {
    "title":   {"title": ("text", 18), "sub": ("text", 26)},
    "price":   {"who": ("choice", ("people", "factory", "bank")), "says": ("text", 14)},
    "calc":    {"top": ("text", 18), "big": ("text", 9)},
    "formula": {"title": ("text", 18), "formula": ("text", 28), "sub": ("text", 44)},
    "versus":  {"left": ("card",), "right": ("card",), "right_on": ("word",)},
    "flow":    {"from": ("text", 9), "from_note": ("text", 12), "to": ("text", 9), "to_note": ("text", 12),
                "label": ("text", 12), "to_on": ("word",)},
    "list":    {"title": ("text", 20), "lines": ("lines", 4, 24)},
    "words":   {"lines": ("lines", 2, 14)},
}


def board_layers(b: dict) -> list[tuple[str, float]]:
    """[(svg, delay key)] for one board picture; delay key is 0 (at once) or a field name whose word
    triggers it (e.g. 'to_on'). Everything is placed inside the chalkboard."""
    k = b["kind"]
    cx, cy = BOARD_CX, BOARD_CY
    if k == "title":
        t, sub = b.get("title", ""), b.get("sub", "")
        out = [(chalk(cx, cy - 40, t, fit(t, 130, 820, 0.48)), 0)]
        if sub:
            out.append((chalk(cx, cy + 90, sub, fit(sub, 70, 780, 0.45), CHALK_YELLOW), 0.35))
        return out
    if k == "price":
        says = b.get("says", "")
        return [(at(P.icon(b.get("who") or "people", 150), cx - 230, cy + 110), 0),
                (at(P.speech(says, size=fit(says, 66, 500, 0.6), tail="left"), cx + 120, cy - 110), 0.3)]
    if k == "calc":
        return [(at(P.calculator(b.get("top", ""), b["big"]), cx, cy, 0.95), 0)]
    if k == "formula":
        f, title, sub = b["formula"], b.get("title", ""), b.get("sub", "")
        out = []
        if title:
            out.append((chalk(cx, cy - 190, title, fit(title, 64, 760, 0.45), CHALK_YELLOW), 0))
        out.append((at(f'<rect x="-420" y="-80" width="840" height="160" rx="24" fill="#fff" opacity=".08"/>', cx, cy - 10)
                    + chalk(cx, cy - 10, f, fit(f, 92, 800, 0.46)), 0))
        if sub:
            out.append((chalk(cx, cy + 150, sub, fit(sub, 50, 820, 0.42), CHALK_BLUE), 0.3))
        return out
    if k == "versus":
        out = []
        for side, x, rot, col in (("left", cx - 250, -3, P.NAVY), ("right", cx + 250, 3, P.GREEN)):
            c = b[side]
            colr = {"red": P.RED, "green": P.GREEN, "navy": P.NAVY, "blue": P.BLUE_SH, "yellow": YELLOW}.get(
                str(c.get("color") or "").lower(), col)
            out.append((at(P.card(c["title"], c.get("lines") or [], c.get("icon") or "doc", colr), x, cy + 20, 0.9, rot),
                        0 if side == "left" else "right_on"))
        out.insert(1, (chalk(cx, cy + 10, "vs", 90, CHALK_YELLOW), 0.2))
        return out
    if k == "flow":
        money = str(b["from"]).startswith("₹") and str(b["to"]).startswith("₹")
        if money:
            a = P.cash(b["from"]) + (chalk(0, 150, b.get("from_note", ""), 54) if b.get("from_note") else "")
            z = P.cash(b["to"], layers=6) + (chalk(0, 170, b.get("to_note", ""), 54, CHALK_YELLOW) if b.get("to_note") else "")
        else:
            a = P.tile(b["from"], b.get("from_note") or "")
            z = P.tile(b["to"], b.get("to_note") or "", color=P.GREEN)
        return [(at(a, cx - 240, cy + 30, 0.95), 0),
                (at(P.curved_arrow("", 260), cx, cy - 120, 0.95)
                 + chalk(cx, cy - 230, b.get("label") or "", 64, CHALK_PINK), 0.35),
                (at(z, cx + 240, cy + 30, 1.05), "to_on")]
    if k == "list":
        title, lines = b.get("title", ""), b["lines"]
        out = [(chalk(cx, 400, title, fit(title, 76, 820, 0.45), CHALK_YELLOW), 0)]
        top = cy + 60 - 56 * (len(lines) - 1)
        for i, line in enumerate(lines):
            y = top + i * 112
            tick = (f'<path d="M 168 {y} l 18 20 l 34 -42" fill="none" stroke="#7EE08A" stroke-width="10" '
                    'stroke-linecap="round" stroke-linejoin="round"/>')
            out.append((tick + chalk(250, y, line, fit(line, 78, 700, 0.42), anchor="start"), 0.25 + 0.45 * i))
        return out
    if k == "words":
        lines = b["lines"]
        n = len(lines)
        out = []
        for i, line in enumerate(lines):
            y = cy + (i - (n - 1) / 2) * 170
            out.append((chalk(cx, y, line, fit(line, 140, 820, 0.5), CHALK_WHITE if i == 0 else CHALK_YELLOW), 0.3 * i))
        out.append((f'<path d="M {cx-300} {cy + (n-1)*85 + 90} q 300 -26 600 0" fill="none" stroke="{CHALK_PINK}" '
                    'stroke-width="9" stroke-linecap="round"/>', 0.3 * n))
        return out
    raise ValueError(f"unknown board picture {k}")


def check_board(b, say_words: set[str], where: str) -> list[str]:
    if not isinstance(b, dict) or b.get("kind") not in BOARD_KINDS:
        return [f"{where}: board kind must be one of {', '.join(BOARD_KINDS)}"]
    out = []
    for field, rule in BOARD_KINDS[b["kind"]].items():
        v = b.get(field)
        # title, sub and formula chalk shrinks to the board's width, so a small overrun still fits
        limit = (int(rule[1] * 1.3) if field in ("title", "sub", "formula") else rule[1]) if rule[0] == "text" else 0
        if rule[0] == "text" and v is not None and len(str(v).replace("^", "")) > limit:
            out.append(f"{where}: board {field} is {len(str(v))} characters; at most {rule[1]}")
        elif rule[0] == "lines" and v is not None and (not isinstance(v, list) or not 1 <= len(v) <= rule[1]
                                                        or any(len(str(x)) > rule[2] for x in v)):
            out.append(f"{where}: board {field} needs 1-{rule[1]} lines of at most {rule[2]} characters")
        elif rule[0] == "word" and v and str(v).lower().strip(".,!?") not in say_words:
            out.append(f"{where}: board {field} '{v}' is not a word of the line")
        elif rule[0] == "choice" and v is not None and v not in rule[1]:
            out.append(f"{where}: board {field} must be one of {', '.join(rule[1])}")
        elif rule[0] == "card":
            if not isinstance(v, dict) or not str(v.get("title") or "").strip():
                out.append(f"{where}: board {field} needs a title")
                continue
            if len(str(v["title"])) > 10:
                out.append(f"{where}: board {field} title is {len(str(v['title']))} characters; at most 10")
            lines = v.get("lines") or []
            if not isinstance(lines, list) or len(lines) > 2 or any(len(str(x)) > 14 for x in lines):
                out.append(f"{where}: board {field} needs at most 2 lines of at most 14 characters")
            if v.get("icon") and v["icon"] not in P.ICONS:
                out.append(f"{where}: board {field} icon must be one of {', '.join(P.ICONS)}")
    required = {"title": ["title"], "price": ["says"], "calc": ["big"], "formula": ["formula"],
                "versus": ["left", "right"], "flow": ["from", "to"], "list": ["lines"], "words": ["lines"]}[b["kind"]]
    out += [f"{where}: board {r} is required" for r in required if not b.get(r)]
    return out
