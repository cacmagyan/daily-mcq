"""Cartoon explainer reel of the day (posts at the reel time, 6 PM, in place of the MCQ reel).

Two styles (config.yaml explainer: style):
- "story" (default): a classroom scene of about a minute. The page's two students ask about the
  concept of the day and the elephant teacher explains it at a chalkboard; each character has their
  own free Kokoro voice, mouths move with the voice, and the board drawings appear as they are said.
- "classic": the elephant alone explains it in about 40 seconds, one big word on screen at a time.
Either way it only explains: no exam traps or mistakes. Claude writes the script from the already-
checked concept note and a second call checks it; the video is drawn and voiced here, so it needs no
key. If anything fails the MCQ reel posts instead, as before.
Files: queue/DATE/explainer.json, explainer.mp4, explainer_cover.jpg.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .config import ROOT, Config, batch_dir

EXPLAINER = "explainer"
VIDEO, COVER = "explainer.mp4", "explainer_cover.jpg"
FOLLOW_LINE = "Follow for one concept every day!"
SCRIPT_KEYS = ("title", "caption_hook", "hook_label", "scenes", "lines")


def style(cfg: Config) -> str:
    return "classic" if str(cfg.explainer.get("style", "story")).lower() == "classic" else "story"


def is_story(script: dict) -> bool:
    return bool(script.get("lines"))


class ExplainerError(RuntimeError):
    pass


# ── files (slot "" = the evening video, "2" = the second video of the day: explainer2.*) ──
def path(date: dt.date, slot: str = "") -> Path:
    return batch_dir(date) / f"explainer{slot}.json"


def load(date: dt.date, slot: str = "") -> dict | None:
    p = path(date, slot)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def slot_of(item: dict) -> str:
    return "2" if str(item.get("kind", "")).endswith("2") else ""


def save(date: dt.date, item: dict, slot: str | None = None) -> Path:
    p = path(date, slot_of(item) if slot is None else slot)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(item, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return p


# ── the script ──────────────────────────────────────────────
def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


TEMPLATES_USED = ("hook", "talk", "sign", "board", "versus", "formula", "calc", "flow", "stacks", "paper",
                  "hold", "follow")
_CARD = {"type": "object", "properties": {
    "title": _s("At most 10 characters"), "lines": {"type": "array", "items": _s("At most 14 characters"), "maxItems": 2},
    "icon": _s("One of the icons"), "color": _s("navy, green, red, blue or yellow")}}
WRITE_TOOL = {
    "name": "submit_script",
    "description": "Submit the finished explainer reel script.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": _s("What the reel teaches, at most 50 characters, e.g. 'Nominal vs effective interest rate'"),
            "caption_hook": _s("First line of the Instagram caption, at most 90 characters, no hashtags"),
            "scenes": {"type": "array", "minItems": 8, "maxItems": 12, "items": {
                "type": "object",
                "properties": {
                    "template": {"type": "string", "enum": list(TEMPLATES_USED)},
                    "say": _s("The voice line for this scene"),
                    "pose": _s("Elephant pose"), "stamp": _s("hook"), "bubble": _s("talk"), "speech": _s("talk"),
                    "lines": {"type": "array", "items": {"type": "string"}, "description": "sign, board, paper"},
                    "title": _s("board, paper, formula"), "left": _CARD, "right": _CARD,
                    "joiner": _s("versus: VS or OR"), "right_on": _s("versus"), "formula": _s("formula"),
                    "sub": _s("formula"), "top": _s("calc"), "big": _s("calc"), "from": _s("flow"),
                    "from_note": _s("flow"), "to": _s("flow"), "to_note": _s("flow"), "label": _s("flow, hold"),
                    "to_on": _s("flow"), "labels": {"type": "array", "items": {"type": "string"}, "description": "stacks"},
                    "values": {"type": "array", "items": {"type": "string"}, "description": "stacks"},
                    "note": _s("stacks"), "item": _s("hold"), "face": _s("hold"), "confetti": {"type": "boolean"},
                },
                "required": ["template", "say"]}},
            "reviewer_note": _s("Anything a reviewer should double-check; empty if nothing"),
        },
        "required": ["title", "caption_hook", "scenes", "reviewer_note"],
    },
}

WRITER_SYSTEM = """You write the script of a 35-45 second cartoon explainer reel for an Instagram page for Indian CA and CMA students. A friendly elephant in a navy suit acts out each scene, a warm female voice reads the lines, and each spoken word appears big on screen as it is said.

The reel only explains the concept of the day (its checked note is given), so that a student who knows nothing about it gets it in one watch. It is not about exam traps or mistakes: never mention traps, mistakes, examiners or "students get this wrong".

Order of scenes
1. "hook" first. Its line makes people curious in under 3 seconds: a surprising true fact, a relatable question or a bold simple claim that the reel then explains, at most 10 words. Its stamp shows it in 1-3 words, a number or a tiny formula (e.g. "₹1,000 = ₹1,104?", "WHY?").
2. A tiny story or example (2-4 scenes): an everyday situation an Indian student relates to (money, a shop, a job, a family business), and what it shows.
3. The concept in simple words (2-4 scenes), with its formula ("formula") or rule ("board"), and for a numerical topic a small worked example ("calc", "flow" or "stacks") whose numbers add up.
4. One recap line ("sign" or "board"): the idea to remember, in a few words.
5. "follow" last; its line is added for you (write "Follow for one concept every day!").

Voice lines ("say")
- 8-12 scenes, 85-115 words in all, at most 22 words a line. Spoken, simple Indian classroom English, short sentences, a friendly teacher's tone. No filler, no emoji, no hashtags.
- Write amounts and percentages normally (₹1,000, 10.38%, 12%): they are read out correctly. Write a formula or symbol expression as {{shown|spoken}}, e.g. {{(1+r/m)^m|one plus r over m, to the power m}}; on screen the shown part appears as one word. Acronyms in capitals (NPV, GST) are spelt out letter by letter; write ordinary words in normal case.
- A field ending in _on names one word of that scene's line: its picture appears when that word is spoken.
- Every fact, number, formula and example must be correct for this paper under current ICAI/ICMAI study material, and every number must add up. {law_line}
- Never claim what you can't know ("90% of students", "asked in every exam").

Templates and fields (text limits in characters are strict; a picture never shows more):
- hook: stamp (16), pose
- talk: pose, and either bubble (6, a thought cloud, e.g. "?" or "₹?") or speech (16, a speech bubble)
- sign: lines (1-2 lines of 12) on a signpost, pose
- board: title (18), lines (2-4 lines of 22) with ticks, pose (only if every line is at most 14 and title 12; otherwise no pose)
- versus: left and right cards {{title (10), lines (1-2 of 14), icon, color}}, joiner ("VS" or "OR"), right_on
- formula: formula (28; use ^ for a power, e.g. EAR = (1 + r/m)^m − 1), sub (38, what the symbols mean), title (18, default EXAM FORMULA)
- calc: top (18, the sum), big (9, the answer), pose
- flow: from (10), from_note (14), to (10), to_note (14), label (8, on the arrow), to_on. Two amounts starting with ₹ are drawn as cash bundles.
- stacks: labels (2-5 of 7), values (same count, 8 each), note (34): coin stacks that grow with the values
- paper: title (12), lines (2-4 of 20; a last line ending in "?" turns red), pose: a question sheet
- hold: item (cash, coin, ticket or doc), label (9), face (happy, excited, worried, proud, shocked, joy), confetti (true/false)
- follow: nothing else
Poses: explain (points up), happy (waves), joy (jumps), think (hand on chin), shocked, worried, shrug, thumbs, wink, present (open hand to the side), sleepy, hold, excited.
Icons: money, calendar, clock, door, doc, check, cross, chart_up, chart_down, scale, factory, bank, people, bulb.
Use a variety of templates; never the same template twice in a row.
{traps}"""

CHECKER_SYSTEM = """You are a strict examiner checking the script of a short explainer reel for {course} ({body}) students, paper: {paper}.
Go through every voice line and every on-screen text. Work out yourself what is correct, then compare: every fact, rule, definition, formula, number and calculation (redo the arithmetic), the example and the hook's claim. Flag claims that can't be known (statistics about students, "asked every time").
Severity "major" for anything wrong or misleading (a wrong number, formula or rule, an example that doesn't add up, a false hook, outdated law, an invented section, rate or limit). "minor" for wording only. "none" if all is correct. For each problem give where it is and the correct version.
{law_line}{traps}"""


def _scene_texts(sc: dict) -> list[str]:
    out = []
    for k, v in sc.items():
        if k in ("template", "say", "pose", "face", "icon", "item", "joiner", "color", "n") or k.endswith("_on") or k == "on":
            continue
        if isinstance(v, str) and v.strip():
            out.append(f"{k}: {v}")
        elif isinstance(v, list):
            out.append(f"{k}: " + " | ".join(str(x) for x in v))
        elif isinstance(v, dict):
            out.append(f"{k}: " + "; ".join(f"{a}={b}" for a, b in v.items() if a != "icon"))
        elif isinstance(v, bool) and k == "answer":
            out.append(f"answer: {'TRUE' if v else 'FALSE'}")
    return out


def plain(script: dict) -> str:
    """The script as plain text, for the checker and the report."""
    lines = [f"Title: {script.get('title', '')}"]
    for i, sc in enumerate(script.get("scenes") or [], 1):
        lines.append(f"Scene {i} ({sc.get('template')}): voice: {sc.get('say', '')}")
        lines += [f"    on screen {t}" for t in _scene_texts(sc)]
    return "\n".join(lines)


def follow_line(cfg: Config) -> str:
    from .replies import settings
    s = settings(cfg)
    if s.get("enabled"):
        word = (s.get("keywords") or ["notes"])[0].upper()
        return f"Comment {word} for the full note, and follow for one concept every day!"
    return FOLLOW_LINE


def tidy(script: dict) -> dict:
    def clean(v):
        if isinstance(v, str):
            return " ".join(v.split())
        if isinstance(v, list):
            return [clean(x) for x in v if not (isinstance(x, str) and not x.strip())]
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items() if x not in (None, "", [])}
        return v
    script = clean(script)
    scenes = [sc for sc in script.get("scenes") or [] if isinstance(sc, dict)]
    if scenes and scenes[-1].get("template") == "follow":
        scenes[-1]["say"] = FOLLOW_LINE
    script["scenes"] = scenes
    return script


def word_count(script: dict) -> int:
    from .cartoon_video import tokens
    return sum(len(tokens(sc.get("say", ""))) for sc in script.get("scenes") or [])


def validate(script: dict) -> list[str]:
    from .cartoon_scenes import check_scene

    scenes = script.get("scenes") or []
    out = []
    if not 8 <= len(scenes) <= 12:
        out.append(f"use 8-12 scenes (there are {len(scenes)})")
    if not scenes or scenes[0].get("template") != "hook":
        out.append("the first scene must be the hook")
    if not scenes or scenes[-1].get("template") != "follow":
        out.append("the last scene must be follow")
    unused = sorted({sc.get("template") for sc in scenes if sc.get("template") not in TEMPLATES_USED})
    if unused:
        out.append(f"don't use these templates: {', '.join(map(str, unused))}")
    n = word_count(script)
    if not 75 <= n <= 125:
        out.append(f"the voice lines have {n} words; write 85-115")
    said = " ".join(sc.get("say", "") for sc in scenes).lower()
    if re.search(r"\btraps?\b|\bmistakes?\b|\bexaminers?\b", said):
        out.append("the reel only explains: don't talk about traps, mistakes or examiners")
    for i, sc in enumerate(scenes, 1):
        out += check_scene(sc, i)
        if len((sc.get("say") or "").split()) > 26:
            out.append(f"scene {i}: the line is too long (at most 22 words)")
        if re.search(r"[\U0001F300-\U0001FAFF]|#\w", sc.get("say") or ""):
            out.append(f"scene {i}: no emoji or hashtags in the voice line")
    return out


def write_script(cfg: Config, concept: dict, course: dict, paper: dict, date: dt.date, instruction: str = "") -> dict:
    """Claude writes the script from the concept note; a second call checks it. Returns the script with
    `checked` True, or with `serious` set if the facts could not be confirmed."""
    from . import traps
    from .concept import CHECK_TOOL, plain as concept_plain
    from .generator import GenerationError, _call_claude, call_checker

    law_text = cfg.law_text(paper, date)
    writer = cfg.models.get("writer", "claude-sonnet-5-5")
    trap_text = traps.block(course, paper)
    law_line = (f"Law and tax: follow exactly this basis: {law_text}. Never invent a section number, rate or limit."
                if law_text else "")
    story = style(cfg) == "story"
    system = (STORY_SYSTEM if story else WRITER_SYSTEM).format(law_line=law_line, traps=trap_text)
    tool = STORY_TOOL if story else WRITE_TOOL
    check_fn, plain_fn = (story_validate, story_plain) if story else (validate, plain)
    check_system = CHECKER_SYSTEM.format(course=course["name"], body=course.get("body", ""),
                                         paper=cfg.paper_prompt(paper), traps=trap_text,
                                         law_line=f"Law basis to apply: {law_text}.\n" if law_text else "")
    user = (f"Course: {course['name']} ({course.get('body', '')})\nPaper: {cfg.paper_prompt(paper)}\n"
            f"Concept of the day: {concept.get('topic', '')}\n\nThe checked concept note:\n{concept_plain(concept)}\n")
    if instruction:
        user += f"\nReviewer's instruction for this reel: {instruction}\n"

    feedback, last, notes = "", None, []
    attempts = int(cfg.explainer.get("max_attempts", 2))
    for attempt in range(1, attempts + 1):
        msg = user + (f"\nYour previous script was rejected:\n{feedback}\nWrite a corrected script.\n" if feedback else "")
        raw = _call_claude(writer, system, msg, tool, max_tokens=6000)
        draft = story_tidy(cfg, raw) if story else tidy(raw)
        if draft.get("scenes") and draft["scenes"][-1].get("template") == "follow":
            draft["scenes"][-1]["say"] = follow_line(cfg)
        last = draft
        problems = check_fn(draft)
        if problems:
            feedback = "Format problems: " + "; ".join(problems[:12])
            notes = [f"Format: {p}" for p in problems[:6]]
            continue
        check = call_checker(cfg, check_system, plain_fn(draft), CHECK_TOOL, max_tokens=2500)
        notes = [f"Checker: {i}" for i in check.get("issues", []) if i]
        minor_left = check.get("severity") == "minor" and check.get("issues") and attempt < attempts
        if check.get("severity") != "major" and not minor_left:
            draft.update(attempts=attempt, checked=True, serious=False,
                         check_notes=([f"Writer: {draft['reviewer_note']}"] if draft.get("reviewer_note") else []) + notes)
            return draft
        feedback = ("An independent examiner found these errors: " if check.get("severity") == "major" else
                    "An independent examiner asks for these wording fixes (keep everything else): ") + "; ".join(check.get("issues", []))
    if not last or check_fn(last):
        raise GenerationError("Claude's explainer scripts didn't fit the format: " + feedback[:300])
    last.update(attempts=attempts, checked=False, serious=True,
                serious_reason="The checker found errors that weren't fixed" + (f" ({notes[0][:160]})" if notes else ""),
                check_notes=[f"Not confirmed after {attempts} attempts"] + notes)
    return last


# ── story scripts ───────────────────────────────────────────
_BOARD = {"type": "object", "description": "A new chalkboard drawing (teacher lines only)", "properties": {
    "kind": {"type": "string", "enum": ["title", "price", "calc", "formula", "versus", "flow", "list", "words"]},
    "title": _s("title, formula, list"), "sub": _s("title, formula"), "who": _s("price: people, factory or bank"),
    "says": _s("price"), "top": _s("calc"), "big": _s("calc"), "formula": _s("formula"),
    "left": _CARD, "right": _CARD, "right_on": _s("versus"), "from": _s("flow"), "from_note": _s("flow"),
    "to": _s("flow"), "to_note": _s("flow"), "label": _s("flow"), "to_on": _s("flow"),
    "lines": {"type": "array", "items": {"type": "string"}, "description": "list, words"}},
    "required": ["kind"]}
STORY_TOOL = {
    "name": "submit_story",
    "description": "Submit the finished classroom scene.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": _s("What the reel teaches, at most 50 characters"),
            "caption_hook": _s("First line of the Instagram caption, at most 90 characters, no hashtags"),
            "hook_label": _s("The hook as a short stamp on screen, at most 22 characters"),
            "lines": {"type": "array", "minItems": 10, "maxItems": 17, "items": {
                "type": "object",
                "properties": {
                    "who": {"type": "string", "enum": ["teacher", "girl", "boy"]},
                    "say": _s("What they say"),
                    "shot": {"type": "string", "enum": ["desk", "close", "board", "follow"]},
                    "pose": _s("Their pose"), "react": _s("desk shot: how the other student looks"),
                    "board": _BOARD},
                "required": ["who", "say", "shot"]}},
            "reviewer_note": _s("Anything a reviewer should double-check; empty if nothing"),
        },
        "required": ["title", "caption_hook", "hook_label", "lines", "reviewer_note"],
    },
}

STORY_SYSTEM = """You write a 50-65 second cartoon scene for an Instagram page for Indian CA and CMA students. In a classroom, two students (a boy and a girl, no names) ask about the concept of the day, and their teacher, a friendly elephant (they may call her Ma'am), explains it at a chalkboard. Each line is spoken in that character's own voice, with short subtitles.

The scene only explains the concept of the day (its checked note is given), so that a student who knows nothing about it gets it in one watch. It is not about exam traps or mistakes: never mention traps, mistakes, examiners or "students get this wrong".

How it goes
1. Line 1: a student's hook (shot "desk" or "close"): a surprised question or a relatable confusion that makes people want the answer, at most 12 words. hook_label shows it as a short stamp (at most 22 characters, e.g. "PRICE BEFORE PRODUCT?").
2. The teacher answers at the board, and the students keep asking the natural next question, react ("Oh!", "Wait...", "Hmm,") or make a guess the teacher builds on. Step by step: a tiny everyday example an Indian student relates to (money, a shop, a phone, a job, a family business), the rule or formula, and for a numerical topic a small worked example whose numbers add up.
3. One recap line from the teacher with a "words" board: the idea to remember in a few words.
4. Last line: the teacher, shot "follow" (its words are added for you; write "Follow for one concept every day!").

Lines
- 11-16 lines, 120-175 words in all. Teacher lines at most 22 words. Student lines at most 14 words and sound like real Indian college students talking: contractions, short reactions, curiosity. The teacher is warm and clear, with short sentences.
- Write amounts and percentages normally (₹1,000, 10.38%): they are read out correctly. Say a formula in words ("target cost equals target selling price minus target profit"); the board shows the symbols. Acronyms in capitals (NPV, GST) are spelt out letter by letter; write ordinary words in normal case.
- No emoji or hashtags. Every fact, number, formula and example must be correct for this paper under current ICAI/ICMAI study material, and every number must add up. {law_line}
- Never claim what you can't know ("90% of students", "asked in every exam").

Each line has who (teacher, girl, boy), say, shot, pose, and optionally react and board.
- shot: "desk" (both students at their desk; for student lines), "close" (a close-up of whoever speaks; for a strong question or an "Oh!" moment), "board" (the teacher at the chalkboard, the students seen from behind; for teacher lines), "follow" (the last line only). Mix desk and close shots for the students.
- Teacher poses: explain (points up), present (open hand to the board), thumbs, happy, think, excited, shrug, wink. Student poses: talk, ask, think, shocked, worried, happy, excited, aha (points: "got it!"), nervous, doubt. react (desk shots): how the other student looks: listen, think, happy, worried.
- board (teacher lines only): a new chalkboard drawing that stays up until the next one. Give the teacher's first line a board, and a new one at each new step (5-8 drawings in all). Kinds and fields (text limits in characters are strict; nothing longer fits):
  title: title (18), sub (26)
  price: who (people, factory or bank), says (14): a speech bubble from customers, a factory or a bank
  calc: top (18, the sum), big (9, the answer)
  formula: title (18), formula (28; ^ for a power), sub (44, what the symbols mean)
  versus: left and right cards {{title (10), lines (1-2 of 14), icon, color}}, right_on
  flow: from (9), from_note (12), to (9), to_note (12), label (12), to_on; two amounts starting with ₹ are drawn as cash bundles
  list: title (20), lines (1-4 of 24) with ticks
  words: lines (1-2 of 14) in big chalk letters
- A field ending in _on names one word of that line: that part appears when the word is spoken.
Icons: money, calendar, clock, door, doc, check, cross, chart_up, chart_down, scale, factory, bank, people, bulb. Colors: navy, green, red, blue, yellow.
{traps}"""


def story_plain(script: dict) -> str:
    out = [f"Title: {script.get('title', '')}", f"Hook stamp: {script.get('hook_label', '')}"]
    for i, ln in enumerate(script.get("lines") or [], 1):
        out.append(f"Line {i} ({ln.get('who')}, {ln.get('shot')}): {ln.get('say', '')}")
        b = ln.get("board")
        if isinstance(b, dict):
            out.append("    board: " + "; ".join(f"{k}={v}" for k, v in b.items() if not k.endswith("_on")))
    return "\n".join(out)


def story_tidy(cfg: Config | None, script: dict) -> dict:
    def clean(v):
        if isinstance(v, str):
            return " ".join(v.split())
        if isinstance(v, list):
            return [clean(x) for x in v if not (isinstance(x, str) and not x.strip())]
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items() if x not in (None, "", [])}
        return v
    script = clean(script)
    lines = [ln for ln in script.get("lines") or [] if isinstance(ln, dict)]
    if lines and lines[-1].get("shot") == "follow":
        lines[-1].update(who="teacher", say=follow_line(cfg) if cfg else FOLLOW_LINE)
        lines[-1].pop("board", None)
    script["lines"] = lines
    # the hook stamp: Claude sometimes leaves it out or makes it too long; build it from the title
    given = str(script.get("hook_label") or "").strip()
    hook = given or str(script.get("title") or "").strip().upper()
    if len(hook) > 22:
        cut = hook[:23].rsplit(" ", 1)[0].rstrip(" ,:;-&")
        hook = cut if len(cut) >= 8 else hook[:22]
    if hook:
        script["hook_label"] = hook
    return script


_BOARD_LONG = re.compile(r"board (?:title|sub|formula) is (\d+) characters; at most (\d+)$")


def _small_overrun(problem: str) -> bool:
    """Board text a little over its limit still fits: the chalk text shrinks to the board's width."""
    m = _BOARD_LONG.search(problem)
    return bool(m) and int(m.group(1)) <= int(m.group(2)) * 1.3


def story_validate(script: dict) -> list[str]:
    from .cartoon_video import tokens
    from .story_video import check

    lines = script.get("lines") or []
    out = [p for p in check(script) if not _small_overrun(p)]
    if lines and (lines[0].get("who") == "teacher" or lines[0].get("shot") not in ("desk", "close")):
        out.append("line 1 must be a student's hook in a desk or close shot")
    if len(str(script.get("hook_label") or "")) > 22 or not str(script.get("hook_label") or "").strip():
        out.append("hook_label is required, at most 22 characters")
    n = sum(len(tokens(ln.get("say", ""))) for ln in lines)
    if not 105 <= n <= 190:
        out.append(f"the lines have {n} words; write 120-175")
    said = " ".join(ln.get("say", "") for ln in lines).lower()
    if re.search(r"\btraps?\b|\bmistakes?\b|\bexaminers?\b", said):
        out.append("the scene only explains: don't talk about traps, mistakes or examiners")
    for i, ln in enumerate(lines, 1):
        words = len((ln.get("say") or "").split())
        if ln.get("who") == "teacher" and words > 26:
            out.append(f"line {i}: the teacher's line is too long (at most 22 words)")
        if ln.get("who") in ("girl", "boy") and words > 17:
            out.append(f"line {i}: a student's line is too long (at most 14 words)")
        if re.search(r"[\U0001F300-\U0001FAFF]|#\w", ln.get("say") or ""):
            out.append(f"line {i}: no emoji or hashtags")
    if lines and not any(ln.get("board") for ln in lines):
        out.append("give the teacher's lines board drawings")
    return out


# ── the reel ────────────────────────────────────────────────
def tag_for(cfg: Config, concept: dict) -> str:
    course = cfg.course(concept["course_id"])
    paper = (concept.get("paper_name") or "").split(" (")[0]
    short = {"Financial Management and Business Data Analytics": "FM & BDA",
             "Direct Tax Laws and International Taxation": "Direct Tax"}.get(paper, paper)
    tag = f"{course['name']} · {short}"
    return tag if len(tag) <= 44 else course["name"]


def make(cfg: Config, date: dt.date, concept: dict, out_dir: Path | None = None, script: dict | None = None,
         instruction: str = "", slot: str = "") -> dict:
    """Writes (unless `script` is given) and renders the day's explainer. Returns its record (not saved)."""
    from . import cartoon_video as engine

    out_dir = out_dir or batch_dir(date)
    course = cfg.course(concept["course_id"])
    paper = (cfg.find_paper(concept["course_id"], concept.get("paper_code", ""), concept.get("paper_name", ""))
             or {"code": concept.get("paper_code", ""), "name": concept.get("paper_name", "")})
    if script is None:
        script = write_script(cfg, concept, course, paper, date, instruction)
    ex = cfg.explainer
    script = json.loads(json.dumps(script))
    if script.get("scenes") and script["scenes"][-1].get("template") == "follow":
        script["scenes"][-1]["say"] = follow_line(cfg)
    from .replies import settings as dm_settings
    word = ((dm_settings(cfg).get("keywords") or ["notes"])[0].upper() if dm_settings(cfg).get("enabled") else "")
    logo = (cfg.brand.get("logo") or "").strip()
    video, cover = f"explainer{slot}.mp4", f"explainer{slot}_cover.jpg"
    common = dict(tag=tag_for(cfg, concept), handle=cfg.brand.get("handle", "").strip(),
                  logo=(ROOT / logo) if logo else None, with_music=bool(ex.get("music", True)),
                  crf=int(ex.get("crf", 28)), cta=f"Comment {word} for the PDF" if word else "",
                  speed=float(ex.get("speed", 1.05)))
    if is_story(script):
        from . import story_video
        script = story_tidy(cfg, script)
        res = story_video.render(script, out_dir / video, out_dir / cover, **common)
        voice = ", ".join(f"{who}: {c['voice']}" for who, c in story_video.CAST.items())
    else:
        voice = str(ex.get("voice", "af_heart"))
        res = engine.render(script, out_dir / video, out_dir / cover, voice=voice,
                            lang=str(ex.get("lang") or ("hi" if voice.startswith("h") else "en-us")), **common)
    item = {"kind": EXPLAINER + slot, "course_id": concept["course_id"], "paper_code": concept.get("paper_code", ""),
            "paper_name": concept.get("paper_name", ""), "topic": concept.get("topic", ""),
            "concept_topic": concept.get("topic", ""), "video": video, "cover": cover,
            "style": "story" if is_story(script) else "classic",
            "seconds": res["seconds"], "thumb_ms": res["thumb_ms"], "voice": voice,
            "script": {k: script[k] for k in SCRIPT_KEYS if k in script}}
    for k in ("checked", "serious", "serious_reason", "check_notes", "attempts", "reviewer_note"):
        if k in script:
            item[k] = script[k]
    item["caption"] = caption(cfg, item, date)
    return item


def problem(item: dict, concept: dict | None) -> str:
    """Why the explainer must not post now (empty if it can)."""
    if not concept or concept.get("error"):
        return "its concept note is missing"
    if concept.get("topic") != item.get("concept_topic"):
        return "the concept note was changed after the video was made; comment /regen explainer"
    return ""


def caption(cfg: Config, item: dict, date: dt.date) -> str:
    from .caption import _clock, post_ref

    course = cfg.course(item["course_id"])
    handle = cfg.brand.get("handle", "").strip()
    script = item.get("script") or {}
    n = int(cfg.instagram.get("max_hashtags", 5))
    tags = ["#ConceptExplained"] + [t for t in course.get("hashtags", []) if t.lower() not in ("#dailymcq",)]
    lines = [f"🎬 {course.get('emoji', '')} {course['name']} · {script.get('title') or item.get('topic', '')}".replace("  ", " ")]
    if script.get("caption_hook"):
        lines += ["", script["caption_hook"]]
    from .replies import cta
    lines += ["", f"📒 Full concept note today at {_clock(cfg.concept_time(slot_of(item)))}. Save 🔖 this for revision."]
    if cta(cfg):
        lines.append(cta(cfg))
    lines.append(f"{item['paper_code']}: {item['paper_name']}")
    if handle:
        lines += ["", f"Follow {handle} for one concept every day."]
    lines += ["", " ".join(tags[:n]), "", post_ref(item.get("kind") or EXPLAINER, date)]
    return "\n".join(lines)[:2200]


def alt_text(item: dict) -> str:
    script = item.get("script") or {}
    said = " ".join(sc.get("say", "") for sc in (script.get("lines") or script.get("scenes") or []))
    return f"Cartoon explainer: {script.get('title', item.get('topic', ''))}. {said}"[:900]


def sample_script(cfg: Config | None = None) -> dict:
    name = "sample_story.json" if cfg is None or style(cfg) == "story" else "sample_explainer.json"
    with open(ROOT / "samples" / name, encoding="utf-8") as fh:
        return json.load(fh)
