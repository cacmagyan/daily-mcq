"""QT trap of the day: a CA Foundation Quantitative Aptitude question as a 60-80 s reel (qt3d.py / qt_video.py).

It takes the PYQ slot (pyq.format: qt_video). Claude writes only the content: the trap (the tempting wrong
answer), the question, the steps, the shortcut, a follow-up question and simple scene data. The fixed
format (hook -> trap -> question -> options -> pause -> reveal -> steps -> shortcut -> your turn) is put
together here, so every video has the same rhythm. A second Claude call solves the question on its own;
if its answer differs, the video is held.

Questions: a real ICAI past-paper MCQ when the bank has unused ones (badge "ASKED IN ..."), on alternate
days; otherwise an original question in the CA Foundation pattern (badge "CA FOUNDATION · QT")."""

from __future__ import annotations

import datetime as dt
import json
import re

from .config import LETTERS, ROOT, Config, batch_dir

KIND = "pyq"
THEMES = ["green", "purple", "navy", "teal", "maroon"]
TOPICS = [
    ("Business Mathematics", "Ratio and proportion"), ("Business Mathematics", "Indices"),
    ("Business Mathematics", "Logarithms"), ("Business Mathematics", "Linear and quadratic equations"),
    ("Business Mathematics", "Linear inequalities"), ("Business Mathematics", "Simple interest"),
    ("Business Mathematics", "Compound interest and effective rate"), ("Business Mathematics", "Annuities and present value"),
    ("Business Mathematics", "Permutations"), ("Business Mathematics", "Combinations"),
    ("Business Mathematics", "Arithmetic progression"), ("Business Mathematics", "Geometric progression"),
    ("Business Mathematics", "Sets, relations and functions"), ("Business Mathematics", "Basic differentiation"),
    ("Logical Reasoning", "Number series"), ("Logical Reasoning", "Coding and decoding"),
    ("Logical Reasoning", "Direction sense"), ("Logical Reasoning", "Seating arrangement"),
    ("Logical Reasoning", "Blood relations"), ("Logical Reasoning", "Ranking and order"),
    ("Statistics", "Mean, median and mode"), ("Statistics", "Dispersion: range, quartile and standard deviation"),
    ("Statistics", "Probability"), ("Statistics", "Binomial and Poisson distribution"),
    ("Statistics", "Correlation and regression"), ("Statistics", "Index numbers"),
]
SCENE_HELP = """Scene (the picture in the middle of the screen; keep it simple, it only illustrates):
- {"type": "row", "item": "bell|pole|tree|coin|person|box|dot", "n": 4, "lit": 0 or "all" or [indexes],
   "gaps": ["3 s", "3 s", "3 s"] (one short label per gap, optional), "note": "3 gaps = 9 s",
   "counters": [{"label": "From the top", "value": 9}] (optional, up to 3 big counting tiles)}
   For counting things in a line: clock strikes, trees, poles, ranks, terms of a series, people in a row.
- {"type": "track", "length": 100, "runners": [{"name": "A", "pos": 100, "label": "100 m"}], "note": "..."}
   For races, relative speed, "A beats B".
- {"type": "bars", "max": 400, "bars": [{"label": "Start", "segments": [{"v": 100, "label": "₹100"}], "top": "2 times"}], "note": "..."}
   For money growing, frequencies, ratios, index numbers, mean as levelling. Up to 6 bars, up to 5 segments.
- {"type": "line", "from": 0, "to": 20, "tick": 2, "jumps": [{"from": 2, "to": 6, "label": "+4"}],
   "points": [{"at": 14, "label": "next = 14", "good": true}], "note": "..."}
   For series, inequalities, ratios on a scale, directions along a line.
- {"type": "board", "lines": ["log 8 ÷ log 2", "= 3"]}  big working lines; the fallback for algebra.
Labels and notes: at most 22 characters. A step's scene replaces only the keys it gives."""


def path(date: dt.date):
    return batch_dir(date) / "pyq.json"


def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


WRITE_TOOL = {
    "name": "write_qt_trap",
    "description": "Write one CA Foundation QT trap video.",
    "input_schema": {"type": "object", "properties": {
        "topic": _s("The topic, at most 30 characters"),
        "theme": {"type": "string", "enum": THEMES},
        "question": _s("The full MCQ as asked, with the 2-3 key phrases in **double stars**. At most 300 characters"),
        "options": {"type": "array", "minItems": 4, "maxItems": 4, "items": _s("Option text, at most 24 characters")},
        "answer": {"type": "integer", "minimum": 0, "maximum": 3, "description": "Index of the correct option"},
        "trap": {"type": "integer", "minimum": 0, "maximum": 3,
                 "description": "Index of the tempting wrong option most students pick"},
        "hook_small": _s("Tiny label above the hook, e.g. 'Simple interest', at most 24 characters"),
        "hook_big": _s("The fact of the question in a few words, e.g. 'Doubles in 5 years', at most 22 characters"),
        "hook_say": _s("One or two short spoken sentences giving the whole question with every number needed (it is not read out anywhere else), e.g. 'A sum doubles in 5 years at simple interest. When does it become four times?'"),
        "wrong_big": _s("The tempting wrong working, e.g. '5 × 2 = 10 years?', at most 22 characters"),
        "wrong_say": _s("One spoken sentence of the wrong thinking, ending 'Right?'"),
        "steps": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "object", "properties": {
            "title": _s("Step title, at most 30 characters, e.g. 'What doubling means'"),
            "says": {"type": "array", "minItems": 1, "maxItems": 3, "items": _s("One spoken sentence or two, plain words")},
            "rows": {"type": "array", "minItems": 1, "maxItems": 4,
                     "items": _s("A short working line shown on the card, at most 34 characters; **stars** mark the key result")},
            "scene": {"type": "object", "description": "Optional scene change for this step (see the scene rules)"}},
            "required": ["title", "says", "rows"]}},
        "shortcut_say": _s("One or two spoken sentences giving the shortcut or rule, applied to this question"),
        "shortcut_rows": {"type": "array", "minItems": 1, "maxItems": 2, "items": _s("At most 40 characters")},
        "your_turn_say": _s("A spoken follow-up question of the same type with new numbers"),
        "your_turn_rows": {"type": "array", "minItems": 1, "maxItems": 2, "items": _s("At most 34 characters")},
        "your_turn_answer": _s("The answer to the follow-up question"),
        "scene": {"type": "object", "description": "The first scene (see the scene rules)"},
        "hook_scene": {"type": "object", "description": "Optional scene change during the hook"},
    }, "required": ["topic", "theme", "question", "options", "answer", "trap", "hook_small", "hook_big", "hook_say",
                    "wrong_big", "wrong_say", "steps", "shortcut_say", "shortcut_rows", "your_turn_say",
                    "your_turn_rows", "your_turn_answer", "scene"]},
}

WRITE_SYSTEM = """You write a daily 90-110 second "trap" reel for Indian CA Foundation students, Paper 3 Quantitative Aptitude ({part}: {topic}).
The format, fast and direct: the question's facts, the tempting wrong working and its answer (the trap), "Wrong", then straight to the right answer and why in 2-4 short steps, a shortcut, and a follow-up question for the comments. The question and the options are NOT read out, so hook_say must give every fact needed to solve it.
Rules:
- The question must be a genuine CA Foundation-level MCQ with exactly one correct option, and a tempting wrong option that most students pick for a clear reason (the trap).
- Every number must be right. Work the answer out fully before writing; the steps must lead to the answer.
- Spoken lines: simple Indian classroom English, short sentences, no filler, no emoji. Say numbers as digits (₹100, 15 years). Total spoken words across hook_say, wrong_say, steps, shortcut_say and your_turn_say: 100-140 (the reel should run about 60-80 seconds; every extra word costs time). Don't start your_turn_say with "Your turn" or a step with "Step one"; those are added.
- Card rows are short working lines, not sentences.
- Keep to the syllabus as it stands now; avoid anything that depends on a changed law or rate.
{scene_help}"""

CHECK_TOOL = {
    "name": "check_qt_trap",
    "description": "Solve the MCQ yourself and report problems.",
    "input_schema": {"type": "object", "properties": {
        "your_answer": {"type": "string", "enum": LETTERS},
        "follow_up_answer": _s("Your answer to the follow-up question"),
        "issues": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["none", "minor", "major"]}},
        "required": ["your_answer", "follow_up_answer", "issues", "severity"]},
}

CHECK_SYSTEM = """You are a strict examiner for CA Foundation Paper 3 (Quantitative Aptitude). Solve the MCQ and the follow-up yourself first, then read the script.
"major" if the question has no single correct option, the stated answer or the trap is wrong, any working row or spoken line has a wrong number or wrong reasoning, the follow-up answer is wrong, or the question is outside the CA Foundation QT syllabus. "minor" for wording only. "none" otherwise."""


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _plain(text: str) -> str:
    return text.replace("**", "")


def valid_scene(sc) -> dict | None:
    """The scene if it is one the renderer knows, with sane sizes; else None."""
    from . import qt_video as V

    if not isinstance(sc, dict) or sc.get("type") not in V.SCENES:
        return None
    sc = json.loads(json.dumps(sc, ensure_ascii=False))
    try:
        if sc["type"] == "row":
            sc["n"] = max(1, min(20, int(sc.get("n", 4))))
            if sc.get("gaps"):
                sc["gaps"] = [_clip(g, 8) for g in sc["gaps"]][: sc["n"] - 1]
        if sc["type"] == "bars":
            sc["bars"] = sc.get("bars", [])[:6]
            for b in sc["bars"]:
                b["label"] = _clip(b.get("label", ""), 12)
                b["segments"] = [{**g, "v": float(g.get("v", 0))} for g in b.get("segments", [])[:5]]
        if sc["type"] == "line":
            float(sc.get("from", 0)), float(sc.get("to", 10))
        if sc["type"] == "track":
            sc["runners"] = sc.get("runners", [])[:4]
            for r in sc["runners"]:
                r["pos"] = float(r.get("pos", 0))
        for c in sc.get("counters") or []:
            c["label"] = _clip(c.get("label", ""), 18)
        if sc.get("note"):
            sc["note"] = _clip(sc["note"], 26)
    except (TypeError, ValueError, KeyError):
        return None
    return sc


_LEAD = re.compile(r"^\s*(your turn|the shortcut|shortcut|step\s+(one|two|three|four|\d))\s*[.:!,-]*\s*", re.I)


def _unlead(say: str) -> str:
    """Drops a leading "Your turn." / "Step two:" / "The shortcut:" (the fixed lines add their own)."""
    return _LEAD.sub("", str(say or "").strip(), count=1)


def assemble(w: dict, badge: dict, header: str, asked: str = "") -> dict:
    """The full video script from Claude's content, in the fixed order. `asked` ("June 2024") opens the
    video with the attempt that asked a real past-paper question."""
    opts = [_clip(o, 24) for o in w["options"]]
    ans, trap = int(w["answer"]), int(w["trap"])
    scene0 = valid_scene(w.get("scene")) or {"type": "board", "lines": [_clip(w["hook_big"], 22)]}
    lines = []
    if asked:
        lines.append({"say": f"This question came in the CA Foundation {asked} exam.",
                      "card": {"kind": "attempt", "exam": "CA Foundation", "when": asked, "sub": "Paper 3 · Quantitative Aptitude"}})
    lines += [
        {"say": w["hook_say"], "card": {"kind": "hook", "small": w["hook_small"], "big": _clip(w["hook_big"], 22)},
         **({"scene": s} if (s := valid_scene(w.get("hook_scene"))) else {})},
        {"say": w["wrong_say"], "card": {"kind": "hook", "small": "So...", "big": _clip(w["wrong_big"], 22)}},
        {"say": f"Wrong. {opts[trap]} is the trap.",
         "card": {"kind": "trap", "small": badge.get("text", ""), "big": f"{opts[trap]} ×", "sub": "that is the trap"}},
        {"say": f"The right answer is {opts[ans]}. Here's why.",
         "card": {"kind": "answer", "small": "The right answer", "big": opts[ans]}},
    ]
    for n, st in enumerate(w["steps"], 1):
        title = f"Step {n} · {_clip(st['title'], 30)}"
        rows = [_clip(r, 40) for r in st["rows"]][:4]
        says = st["says"][:3]
        for i, say in enumerate(says):
            last = i == len(says) - 1
            shown = rows if last else rows[: max(1, round(len(rows) * (i + 1) / len(says)))]
            ln = {"say": (f"Step {['one', 'two', 'three', 'four'][n - 1]}. " if i == 0 else "") + _unlead(say),
                  "card": {"kind": "step", "title": title, "rows": shown, **({"all": True} if i else {})}}
            if i == 0 and (sc := valid_scene(st.get("scene"))):
                ln["scene"] = sc
            lines.append(ln)
    srows = [_clip(r, 44) for r in w["shortcut_rows"]][:2]
    lines.append({"say": "The shortcut. " + _unlead(w["shortcut_say"]), "card": {"kind": "shortcut", "rows": srows}})
    yrows = [_clip(r, 40) for r in w["your_turn_rows"]][:2]
    lines.append({"say": "Your turn. " + _unlead(w["your_turn_say"]), "card": {"kind": "your_turn", "rows": yrows}})
    lines.append({"say": "Comment your answer. Follow for a QT trap every day.",
                  "card": {"kind": "your_turn", "rows": yrows, "all": True}})
    return {"theme": w["theme"] if w["theme"] in THEMES else "green", "badge": badge, "header": header,
            "question": w["question"], "options": opts, "answer": ans, "scene": scene0, "lines": lines}


def check_content(w: dict) -> list[str]:
    out = []
    if len(set(o.strip().lower() for o in w.get("options", []))) != 4:
        out.append("the 4 options must all differ")
    if w.get("answer") == w.get("trap"):
        out.append("the trap must be a wrong option")
    words = sum(len(str(x).split()) for x in [w.get("hook_say"), w.get("wrong_say"), w.get("shortcut_say"),
                                               w.get("your_turn_say")] + [s for st in w.get("steps", []) for s in st.get("says", [])])
    if not 85 <= words <= 160:
        out.append(f"the spoken lines have {words} words; use 100-140 so the reel runs about 60-80 s")
    return out


def topic_for(cfg: Config, date: dt.date) -> tuple[str, str]:
    recent = set()
    for i in range(1, 15):
        p = path(date - dt.timedelta(days=i))
        if p.exists():
            try:
                recent.add(json.loads(p.read_text(encoding="utf-8")).get("topic_key", ""))
            except ValueError:
                pass
    order = TOPICS[date.toordinal() % len(TOPICS):] + TOPICS[: date.toordinal() % len(TOPICS)]
    for part, topic in order:
        if topic not in recent:
            return part, topic
    return order[0]


def attempt_name(asked: str) -> str:
    """'Jun 2024 exam' / 'June 2024' / 'PY S25' -> 'June 2024' (what the voice says and the card shows)."""
    t = re.sub(r"\s*exam$", "", str(asked or "").strip(), flags=re.I)
    months = {"jan": "January", "feb": "February", "mar": "March", "apr": "April", "may": "May", "jun": "June",
              "jul": "July", "aug": "August", "sep": "September", "sept": "September", "oct": "October",
              "nov": "November", "dec": "December"}
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{4})$", t)
    if m and m.group(1).lower()[:4].rstrip("t") in months or (m and m.group(1).lower()[:3] in months):
        key = m.group(1).lower()
        return f"{months.get(key[:4], months.get(key[:3]))} {m.group(2)}"
    return t


BANK_COURSE = "ca_foundation_qt"     # ca_foundation_qt_bank.json


def past_paper_candidate(cfg: Config, date: dt.date) -> dict | None:
    """The next unused real CA Foundation Paper 3 MCQ from the QT bank (ICAI's booklets with official keys),
    every day while the bank lasts; None when it has run out (then an original question is written)."""
    from . import pyq
    from .pyqday import asked_short, split_mcq, used_refs

    used = used_refs()
    paper = {"code": "Paper 3", "name": "Quantitative Aptitude"}
    for q in pyq.questions(BANK_COURSE, paper):
        ref = f"{BANK_COURSE}|{q.get('chapter')}-{q.get('q')}"
        if q.get("kind") != "mcq" or not q.get("answer") or ref in used:
            continue
        parts = split_mcq(q.get("text", ""))
        if parts:
            return {"ref": ref, "stem": parts[0], "opts": parts[1], "key": q["answer"].strip("()").upper(),
                    "asked": q.get("asked") or asked_short(q.get("papers") or []),
                    "part": q.get("section") or "Business Mathematics", "topic": q.get("chapter_title") or "",
                    "trap": (q.get("trap") or "").strip("()").upper(), "trap_why": q.get("trap_why") or "",
                    "qno": q.get("q")}
    return None


def make(cfg: Config, date: dt.date, instruction: str = "") -> dict:
    """Write and check the day's QT trap (not yet voiced or drawn)."""
    from .generator import GenerationError, _call_claude, call_checker

    model = cfg.models.get("writer", "claude-sonnet-5-5")
    past = past_paper_candidate(cfg, date)
    part, topic = topic_for(cfg, date)
    user = ""
    if past:
        part = past["part"]
        topic = past.get("topic") or "as in the question"
        badge = {"tag": "ASKED IN", "text": f"CA FOUNDATION {attempt_name(past['asked']).upper()} · QT"}
        header = f"CA Foundation {attempt_name(past['asked'])} · Paper 3 · QT"
        user += ("Use this real past-paper question exactly (fix only spacing and obvious typos). Its official answer is "
                 f"({past['key'].lower()}).\nQuestion: {past['stem']}\n"
                 + "\n".join(f"({'abcd'[i]}) {o}" for i, o in enumerate(past["opts"])) + "\n")
        if past.get("trap"):
            user += (f"The trap: most students pick ({past['trap'].lower()}) because {past['trap_why']}. "
                     "Use it as the trap unless another option is clearly the more common mistake.\n")
    else:
        badge = {"tag": "CA FOUNDATION", "text": f"QT · {topic.upper()[:28]}"}
        header = "CA Foundation pattern · Paper 3 · Quantitative Aptitude"
        user += f"Write an original question on {topic} ({part}).\n"
    if instruction:
        user += f"Reviewer's instruction: {instruction}\n"
    system = WRITE_SYSTEM.format(part=part, topic=topic, scene_help=SCENE_HELP)
    base = {"kind": KIND, "format": "qt_video", "course_id": "ca_foundation", "paper_code": "Paper 3",
            "paper_name": f"Quantitative Aptitude: {part}", "topic_key": topic, "ref": past["ref"] if past else "",
            "tried": [past["ref"]] if past else []}
    notes = []
    for attempt in range(3):
        try:
            w = _call_claude(model, system, user + ("\nFix: " + "; ".join(notes[-2:]) if notes else ""), WRITE_TOOL, max_tokens=5000)
        except GenerationError as exc:
            return {**base, "error": str(exc)[:300]}
        probs = check_content(w)
        if past and LETTERS[int(w.get("answer", -1))] != past["key"]:
            probs.append(f"the official answer is ({past['key'].lower()})")
        if probs:
            notes.append("; ".join(probs))
            continue
        if not past:
            badge = {"tag": "CA FOUNDATION", "text": f"QT · {_clip(w.get('topic') or topic, 28).upper()}"}
        real = past and "model" not in past["asked"].lower()
        script = assemble(w, badge, header, asked=attempt_name(past["asked"]) if real else "")
        plain = (f"Question: {_plain(w['question'])}\n" + "\n".join(f"({LETTERS[i]}) {o}" for i, o in enumerate(script['options']))
                 + f"\nStated answer: {LETTERS[script['answer']]}\nTrap: {script['options'][int(w['trap'])]}\n"
                 + "\n".join(f"{ln['say']} | card: {' / '.join(ln['card'].get('rows', []))}" for ln in script["lines"])
                 + f"\nFollow-up answer stated: {w['your_turn_answer']}")
        check = call_checker(cfg, CHECK_SYSTEM, plain, CHECK_TOOL, max_tokens=1500)
        if check.get("your_answer") != LETTERS[script["answer"]]:
            notes.append(f"the examiner got ({check.get('your_answer', '?').lower()}): " + "; ".join(check.get("issues", []))[:200])
            continue
        if check.get("severity") == "major":
            notes.append("examiner: " + "; ".join(check.get("issues", []))[:240])
            continue
        return {**base, "topic": w["topic"][:40], "script": script, "correct": LETTERS[script["answer"]],
                "trap": script["options"][int(w["trap"])], "your_turn_answer": w["your_turn_answer"],
                "asked_in": past["asked"] if past else "CA Foundation pattern", "check_notes": check.get("issues", []),
                "notes": notes, "hold": False, "hold_reason": ""}
    return {**base, "error": "no script passed the checks: " + " | ".join(notes)[-300:]}


def caption(cfg: Config, item: dict, date: dt.date) -> str:
    from .caption import post_ref

    s = item["script"]
    handle = cfg.brand.get("handle", "").strip()
    asked = item.get("asked_in", "")
    hook = next((ln["card"]["big"] for ln in s["lines"] if ln["card"].get("kind") == "hook"), "")
    lines = [f"{hook}… so {item['trap']}? That's the trap. 🪤",
             "", _plain(s["question"]), ""] + [f"({'abcd'[i]}) {o}" for i, o in enumerate(s["options"])]
    lines += ["", "Did you pick the trap too? Tell me in the comments 👇",
              (f"Asked in CA Foundation {attempt_name(asked)} · Paper 3 (ICAI's official answer key)." if asked and "pattern" not in asked
               else "CA Foundation Paper 3 · Quantitative Aptitude."),
              "Save 🔖 it for your QT revision."]
    if handle:
        lines += ["", f"Follow {handle} for a QT trap every day."]
    tags = cfg.pyq.get("hashtags_qt") or ["#CAFoundation", "#QuantitativeAptitude", "#CAStudents", "#ICAI", "#MathsTricks"]
    lines += ["", " ".join(tags[: int(cfg.instagram.get("max_hashtags", 5))]), "", post_ref(KIND, date)]
    return "\n".join(lines)[:2200]
