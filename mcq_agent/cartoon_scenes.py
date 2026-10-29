"""Scene templates for the explainer reels. Claude chooses a template and writes its words; the
template places the elephant and the props, so every scene fits the 1080 x 1920 frame.

Each builder returns layers: {"svg", "anim", "delay", "bob", "drift", "anchor", "alt"} where `alt` is
the same picture with the elephant's eyes shut (for blinking). `when(word)` gives the second (from
the scene start) at which a word of the scene's voice line is spoken, or None.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from . import cartoon_props as P
from . import elephant as M

W, H = 1080, 1920
POSES = tuple(M.POSES)
FACES = ("happy", "excited", "worried", "proud", "shocked", "joy")
COLORS = {"red": P.RED, "green": P.GREEN, "navy": P.NAVY, "blue": P.BLUE_SH, "yellow": M.TIE}


# ── layer helpers ───────────────────────────────────────────
def at(svg: str, x, y, s=1.0, rot=0) -> str:
    return f'<g transform="translate({x} {y}) rotate({rot}) scale({s})">{svg}</g>'


def char(pose, x=540, top=610, s=1.3, hold=None, uid="c", blink=False) -> str:
    p = dict(M.POSES[pose] if isinstance(pose, str) else pose)
    if blink:
        p["blink"] = True
    return f'<g transform="translate({x - 300 * s} {top}) scale({s})">' + M.character(p, uid, hold or {}) + "</g>"


def L(svg, anim="pop", delay=0.0, bob=False, drift=(0, 0), anchor=None, alt=None) -> dict:
    return {"svg": svg, "anim": anim, "delay": max(0.0, float(delay)), "bob": bob, "drift": drift,
            "anchor": anchor, "alt": alt}


class _Uid:
    n = 0

    @classmethod
    def next(cls) -> str:
        cls.n += 1
        return f"u{cls.n}"


def C(pose, x=540, top=610, s=1.3, hold=None, anim="pop", delay=0.0, under="", bob=True) -> dict:
    """The elephant as a layer, with a blinking copy."""
    uid = _Uid.next()
    return L(under + char(pose, x, top, s, hold, uid), anim, delay, bob=bob,
             alt=under + char(pose, x, top, s, hold, uid + "k", blink=True))


def _pose(name, default):
    return name if name in M.POSES else default


def _col(name, default):
    return COLORS.get(str(name or "").lower(), default)


def _fit(text: str, size: int, width: float, k=0.62) -> int:
    """Largest font size (at most `size`) at which `text` fits `width` pixels."""
    return int(max(24, min(size, width / max(1, len(text) * k))))


def follow_card(handle: str, logo: Path | None, cta: str = "") -> str:
    """Logo, handle and a Follow button; with `cta`, a second line under them (e.g. Comment NOTES…)."""
    w, h = 820, (330 if cta else 240)
    top = -h / 2
    cy = top + 120                                   # the logo's centre
    img = ""
    if logo and logo.exists():
        data = base64.b64encode(logo.read_bytes()).decode()
        img = (f'<clipPath id="lg"><circle cx="{-w/2+120}" cy="{cy}" r="96"/></clipPath>'
               f'<image href="data:image/png;base64,{data}" x="{-w/2+24}" y="{cy-96}" width="192" height="192" '
               f'clip-path="url(#lg)" preserveAspectRatio="xMidYMid meet"/>')
    out = (f'<g transform="translate(540 {760 + (45 if cta else 0)})">'
           f'<rect x="{-w/2}" y="{top}" width="{w}" height="{h}" rx="{min(120, h/2)}" fill="#fff" stroke="{M.INK}" stroke-width="7"/>'
           f'<circle cx="{-w/2+120}" cy="{cy}" r="100" fill="#fff" stroke="{M.INK}" stroke-width="6"/>{img}'
           + P.text(-w / 2 + 250, cy - 42, handle, _fit(handle, 64, 540), anchor="start")
           + f'<rect x="{-w/2+250}" y="{cy+10}" width="250" height="78" rx="39" fill="{M.TIE}" stroke="{M.INK}" stroke-width="6"/>'
           + P.text(-w / 2 + 375, cy + 50, "Follow", 42)
           + P.text(-w / 2 + 530, cy + 50, "1 concept a day", 30, weight=600, anchor="start"))
    if cta:
        out += (f'<path d="M {-w/2+60} {cy+118} L {w/2-60} {cy+118}" stroke="#E6DCCB" stroke-width="4"/>'
                + P.text(0, cy + 165, cta, _fit(cta, 44, w - 120, 0.6), color=P.RED))
    return out + "</g>"


# ── templates ───────────────────────────────────────────────
# field rules: ("text", max chars, required) · ("lines", min, max, max chars) · ("pose",) · ("face",)
# ("icon",) · ("word",) a word of the voice line · ("bool",) · ("card",) · ("choice", options)
CARD = {"title": ("text", 10, True), "lines": ("lines", 1, 2, 14), "icon": ("icon",), "color": ("choice", tuple(COLORS))}
TEMPLATES = {
    "hook": {"stamp": ("text", 16, True), "pose": ("pose",)},
    "talk": {"pose": ("pose",), "bubble": ("text", 6, False), "speech": ("text", 16, False)},
    "sign": {"lines": ("lines", 1, 2, 12), "pose": ("pose",)},
    "board": {"title": ("text", 18, True), "lines": ("lines", 2, 4, 22), "pose": ("pose",)},
    "versus": {"left": ("card",), "right": ("card",), "joiner": ("choice", ("VS", "OR")), "right_on": ("word",)},
    "formula": {"formula": ("text", 28, True), "sub": ("text", 38, False), "title": ("text", 18, False)},
    "calc": {"top": ("text", 18, False), "big": ("text", 9, True), "pose": ("pose",)},
    "flow": {"from": ("text", 10, True), "from_note": ("text", 14, False), "to": ("text", 10, True),
             "to_note": ("text", 14, False), "label": ("text", 8, False), "to_on": ("word",)},
    "stacks": {"labels": ("lines", 2, 5, 7), "values": ("lines", 2, 5, 8), "note": ("text", 34, False)},
    "paper": {"title": ("text", 12, False), "lines": ("lines", 2, 4, 20), "pose": ("pose",)},
    "hold": {"item": ("choice", ("cash", "coin", "ticket", "doc")), "label": ("text", 9, False), "face": ("face",),
             "confetti": ("bool",)},
    "mistakes_intro": {"text": ("text", 16, False), "pose": ("pose",)},
    "mistake": {"wrong": ("text", 24, True), "wrong_note": ("text", 36, False), "fix": ("text", 24, True),
                "fix_note": ("text", 36, False), "pose": ("pose",), "fix_on": ("word",)},
    "truefalse": {"statement": ("text", 90, True), "answer": ("bool",), "on": ("word",), "pose": ("pose",)},
    "follow": {},
}
MISTAKE_TEMPLATES = ("mistake", "truefalse")


def _words(say: str) -> set[str]:
    return {re.sub(r"[^\w₹%.'-]", "", w).lower().strip(".") for w in re.sub(r"\{[^|}]*\|([^}]*)\}", r"\1", say).split()}


def check_scene(sc: dict, i: int) -> list[str]:
    """Format problems in one scene (template, fields, lengths)."""
    where = f"scene {i}"
    t = sc.get("template")
    if t not in TEMPLATES:
        return [f"{where}: unknown template '{t}' (use one of {', '.join(TEMPLATES)})"]
    out = []
    say = str(sc.get("say") or "")
    if not say.strip():
        out.append(f"{where}: 'say' is empty")
    if t == "talk" and sc.get("bubble") and sc.get("speech"):
        out.append(f"{where}: talk takes a bubble or a speech line, not both")

    def check(rule, val, label):
        kind = rule[0]
        if kind == "text":
            s = str(val or "")
            if rule[2] and not s.strip():
                out.append(f"{label} is required")
            if len(s.replace("^", "")) > rule[1]:
                out.append(f"{label} is {len(s)} characters; at most {rule[1]}")
        elif kind == "lines":
            if val is None:
                return
            if not isinstance(val, list) or not (rule[1] <= len(val) <= rule[2]):
                out.append(f"{label} needs {rule[1]}-{rule[2]} lines")
                return
            for j, s in enumerate(val, 1):
                if len(str(s)) > rule[3]:
                    out.append(f"{label} line {j} is {len(str(s))} characters; at most {rule[3]}")
        elif kind == "pose" and val is not None and val not in M.POSES:
            out.append(f"{label} '{val}' is not a pose ({', '.join(POSES)})")
        elif kind == "face" and val is not None and val not in FACES:
            out.append(f"{label} '{val}' is not one of {', '.join(FACES)}")
        elif kind == "icon" and val is not None and val not in P.ICONS:
            out.append(f"{label} '{val}' is not an icon ({', '.join(P.ICONS)})")
        elif kind == "choice" and val is not None and str(val) not in rule[1]:
            out.append(f"{label} must be one of {', '.join(rule[1])}")
        elif kind == "word" and val and str(val).lower().strip(".,!?") not in _words(say):
            out.append(f"{label} '{val}' is not a word of the voice line")
        elif kind == "card":
            if not isinstance(val, dict):
                out.append(f"{label} is required")
                return
            for k, r in CARD.items():
                check(r, val.get(k), f"{label}.{k}")
    for field, rule in TEMPLATES[t].items():
        check(rule, sc.get(field), f"{where} {field}")
    if t == "stacks" and len(sc.get("labels") or []) != len(sc.get("values") or []):
        out.append(f"{where}: stacks needs as many values as labels")
    return out


def _at(when, word, fallback, dur=None):
    """When a picture tied to `word` appears: as the word is spoken, but never later than 60% into
    the scene, so it stays on screen long enough to see."""
    s = when(word) if word else None
    s = fallback if s is None else max(0.2, s - 0.08)
    return min(s, 0.6 * dur) if dur else s


def _num(v: str) -> float | None:
    m = re.search(r"-?\d[\d,]*\.?\d*", str(v))
    return float(m.group(0).replace(",", "")) if m else None


def layers(sc: dict, when, dur: float, handle: str = "", logo: Path | None = None, cta: str = "") -> list[dict]:
    """The layers of one scene. `dur` is the scene's length in seconds."""
    t = sc["template"]
    pose = sc.get("pose")
    if t == "hook":
        stamp = sc["stamp"]
        return [C(_pose(pose, "shocked"), 540, 720, 1.18, anim="none"),
                L(at(P.label(stamp, P.RED, _fit(stamp, 96, 840, 0.66)), 540, 700), "stamp", 0.15)]
    if t == "talk":
        if sc.get("bubble"):
            return [C(_pose(pose, "think"), 450), L(at(P.bubble(sc["bubble"]), 840, 700), "pop", 0.3)]
        if sc.get("speech"):
            sp = sc["speech"]
            return [C(_pose(pose, "happy"), 420), L(at(P.speech(sp, size=_fit(sp, 60, 520)), 800, 680), "pop", 0.3)]
        return [C(_pose(pose, "explain"))]
    if t == "sign":
        return [C(_pose(pose, "explain"), 330),
                L(at(P.sign(sc["lines"], 440), 790, 700), "drop", 0.2)]
    if t == "board":
        lines = sc["lines"]
        n = len(lines)
        if pose and max(len(x) for x in lines) <= 14 and len(sc["title"]) <= 12:
            h = max(330, 170 + 82 * n)
            return [C(_pose(pose, "present"), 285, 730, 1.05),
                    L(at(P.board(sc["title"], lines, 520, h), 790, 1010), "pop", 0.3)]
        h = max(330, 170 + 82 * n)
        return [L(at(P.board(sc["title"], lines, 840, h), 540, 1000), "pop")]
    if t == "versus":
        out = []
        for side, x, rot, col, d in (("left", 268, -3, P.NAVY, 0.0), ("right", 812, 3, P.GREEN, None)):
            c = sc[side]
            card = P.card(c["title"], c.get("lines") or [], c.get("icon") or "doc", _col(c.get("color"), col))
            delay = d if d is not None else _at(when, sc.get("right_on"), 0.45 * dur, dur)
            out.append(L(at(card, x, 1080, 1.0, rot), "pop", delay))
        out.insert(1, L(at(P.text(0, 0, sc.get("joiner") or "VS", 84), 540, 1080), "pop", 0.4))
        return out
    if t == "formula":
        f = sc["formula"]
        size = _fit(f.replace("^", ""), 76, 790, 0.6)
        return [L(at(P.formula_board(sc.get("title") or "EXAM FORMULA", P.text(0, 0, f, size, color="#fff"),
                                     sc.get("sub") or "", 880, 430), 540, 930), "pop"),
                C("explain", 800, 1130, 0.62, delay=0.4)]
    if t == "calc":
        return [C(_pose(pose, "thumbs"), 290, 760, 1.0),
                L(at(P.calculator(sc.get("top") or "", sc["big"]), 760, 1090, 0.95), "pop", 0.2)]
    if t == "flow":
        money = str(sc["from"]).startswith("₹") and str(sc["to"]).startswith("₹")
        if money:                              # cash bundles, each with its note on a badge below
            a = P.cash(sc["from"]) + (at(P.badge(sc["from_note"], P.NAVY, 40), 0, 175) if sc.get("from_note") else "")
            b = P.cash(sc["to"], layers=6) + (at(P.badge(sc["to_note"], P.GREEN, 40), 0, 190) if sc.get("to_note") else "")
        else:
            a = P.tile(sc["from"], sc.get("from_note") or "")
            b = P.tile(sc["to"], sc.get("to_note") or "", color=P.GREEN)
        out = [L(at(a, 250, 1150, 1.05 if money else 0.95), "pop"),
               L(at(P.curved_arrow(sc.get("label") or "", 300), 540, 1000, 1.05), "pop", 0.35)]
        out.append(L(at(b, 812, 1150, 1.2 if money else 1.0), "stamp", _at(when, sc.get("to_on"), 0.5 * dur, dur)))
        return out
    if t == "stacks":
        labels, values = sc["labels"], sc["values"]
        nums = [_num(v) for v in values]
        if all(v is not None for v in nums) and max(nums) > min(nums):
            lo, hi = min(nums), max(nums)
            counts = [round(3 + 5 * (v - lo) / (hi - lo)) for v in nums]
        else:
            counts = [4 + i for i in range(len(labels))]
        out = [L(at(P.coin_bars(labels, values, counts), 540, 1330, 1.1), "pop")]
        if sc.get("note"):
            out.append(L(at(P.badge(sc["note"], P.NAVY, _fit(sc["note"], 40, 760)), 540, 760), "pop", 0.2))
        return out
    if t == "paper":
        lines = [(x, P.RED if i == len(sc["lines"]) - 1 and x.strip().endswith("?") else M.INK)
                 for i, x in enumerate(sc["lines"])]
        return [C(_pose(pose, "explain"), 320, 680, 1.15),
                L(at(P.paper(lines, sc.get("title") or "EXAM", w=440, h=520), 790, 1080, 1.0, 4), "pop", 0.25)]
    if t == "hold":
        face = sc.get("face") if sc.get("face") in FACES else "happy"
        item, label = sc.get("item") or "cash", sc.get("label") or ""
        held = {"cash": (P.cash(label or "₹"), (104, -62, 0.6, -12)),
                "coin": (P.coin(110, label or "₹"), (92, -60, 0.5, 0)),
                "ticket": (P.ticket("ADMIT ONE", label or "₹"), (100, -60, 0.68, -14)),
                "doc": (P.icon("doc", 70), (90, -60, 0.9, -8))}[item]
        svg, (dx, dy, s, rot) = held
        p = {"face": face, "left": "cheer" if face in ("excited", "joy") else "hip", "right": "hold_up"}
        out = [C(p, 520, 610, 1.3, {"right": at(svg, dx, dy, s, rot)})]
        if sc.get("confetti"):
            out.insert(0, L(at(P.confetti(1000, 900), 540, 1000), "fade", 0.05, drift=(0, 60)))
        return out
    if t == "mistakes_intro":
        text = sc.get("text") or "EXAM MISTAKES"
        return [C(_pose(pose, "shocked"), 540, 760, 1.15),
                L(at(P.label(text, P.RED, _fit(text, 78, 840, 0.66)), 540, 700), "stamp", 0.2)]
    if t == "mistake":
        n = sc.get("n") or ""
        return [L(at(P.badge(f"MISTAKE {n}".strip(), P.RED, 52), 540, 740), "pop"),
                L(at(P.mistake_row(sc["wrong"], sc.get("wrong_note") or ""), 540, 940), "pop", 0.3),
                L(at(P.mistake_row(sc["fix"], sc.get("fix_note") or "", ok=True), 540, 1150), "pop",
                  _at(when, sc.get("fix_on"), 0.5 * dur, dur)),
                C(_pose(pose, "explain"), 540, 1250, 0.45, delay=0.2)]
    if t == "truefalse":
        ok = bool(sc.get("answer"))
        return [L(at(P.statement(sc["statement"]), 540, 900), "pop"),
                C(_pose(pose, "think"), 300, 1110, 0.62, delay=0.2),
                L(at(P.label("TRUE" if ok else "FALSE", P.GREEN if ok else P.RED, 96, -8), 760, 1300), "stamp",
                  _at(when, sc.get("on"), 0.55 * dur, dur))]
    if t == "follow":
        return [L(follow_card(handle, logo, cta), "drop"), C("wink", 540, 900 if cta else 860, 1.08 if cta else 1.12, delay=0.15)]
    raise ValueError(f"unknown template {t}")
