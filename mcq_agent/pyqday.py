"""PYQ of the day: a real past-paper MCQ from the question banks (pyq.py), posted as the usual
two slides (question, then the solution) with an "Asked in" tag.

Only MCQs with an official answer key are used. Claude solves the question itself; if its answer
differs from the key, or the examiner finds an error (for example an outdated law), the next
question is tried. Questions already used are never repeated."""

from __future__ import annotations

import datetime as dt
import json
import re

from .config import LETTERS, ROOT, Config, batch_dir

PYQ = "pyq"
MONTHS = {"J": "June", "D": "December"}


def path(date: dt.date):
    return batch_dir(date) / "pyq.json"


def load(date: dt.date) -> dict | None:
    p = path(date)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save(date: dt.date, item: dict) -> None:
    p = path(date)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(item, fh, ensure_ascii=False, indent=2)


def used_refs() -> set[str]:
    out = set()
    for f in (ROOT / "queue").glob("*/pyq.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.update(d.get("tried") or [])
        if d.get("ref"):
            out.add(d["ref"])
    return out


def _clean(s: str) -> str:
    """Drops PDF bullet glyphs (private-use characters such as \uf0a7) and extra spaces."""
    s = "".join(ch for ch in s if not (0xE000 <= ord(ch) <= 0xF8FF) and ch not in "▪•")
    return " ".join(s.split())


def split_mcq(text: str) -> tuple[str, list[str]] | None:
    """'Stem (a) x (c) z (b) y (d) w' -> ('Stem', [x, y, z, w]); None unless all four options are there."""
    text = _clean(text)
    marks = list(re.finditer(r"\(([a-d])\)\s*", text))
    if len(marks) < 4:
        return None
    stem = text[: marks[0].start()].strip(" ▪:")
    opts: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        opts.setdefault(m.group(1), text[m.end():end].strip(" ,;"))
    if set(opts) != set("abcd") or not stem:
        return None
    return stem, [opts[k] for k in "abcd"]


def asked_in(tags: list[str], exam: str = "CMA Inter") -> str:
    """['PY D24', 'MQP J26 S2'] -> 'CMA Inter December 2024 exam'; model papers named as such."""
    pys = [t for t in tags if t.startswith("PY")]
    t = (pys or tags)[0]
    m = re.search(r"\b([JD])(\d\d)\b", t)
    if not m:
        return t
    when = f"{MONTHS[m.group(1)]} 20{m.group(2)}"
    return f"{exam} {when} exam" if t.startswith("PY") else f"ICMAI model paper, {when}"


def asked_short(tags: list[str]) -> str:
    """['PY D24'] -> 'Dec 2024 exam'; model papers -> 'Model paper, Jun 2026' (fits the slide's small box)."""
    pys = [t for t in tags if t.startswith("PY")]
    t = (pys or tags)[0]
    m = re.search(r"\b([JD])(\d\d)\b", t)
    if not m:
        return t
    when = f"{'Jun' if m.group(1) == 'J' else 'Dec'} 20{m.group(2)}"
    return f"{when} exam" if t.startswith("PY") else f"Model paper {when}"


def _year(q: dict) -> int:
    ys = [int(m.group(1)) for t in q["papers"] for m in [re.search(r"\b[JD](\d\d)\b", t)] if m]
    return max(ys) if ys else 0


def papers(cfg: Config) -> list[dict]:
    """The papers of the PYQ course that have past-paper MCQs with an answer key, in config order."""
    from . import pyq

    course = cfg.course(cfg.pyq.get("course", "cma_inter"))
    return [p for p in course["papers"] if any(q.get("answer") and q["kind"] == "mcq"
                                               for q in pyq.questions(course["id"], p))]


def candidates(cfg: Config, date: dt.date) -> tuple[dict, dict, list[dict]]:
    """(course, paper, questions best first) for the day: papers take turns."""
    from . import pyq

    course = cfg.course(cfg.pyq.get("course", "cma_inter"))
    ps = papers(cfg)
    if not ps:
        return course, {}, []
    start = dt.date.fromisoformat(str(cfg.pyq.get("start_date") or cfg.start_date))
    paper = ps[(date - start).days % len(ps)]
    used = used_refs()
    out = []
    for q in pyq.questions(course["id"], paper):
        ref = f"{paper['code']}|{paper.get('part', '')}|{q['chapter']}-{q['q']}"
        if q["kind"] != "mcq" or not q.get("answer") or ref in used:
            continue
        parts = split_mcq(q["text"])
        if not parts or len(parts[0]) > 420 or any(len(o) > 120 for o in parts[1]):
            continue
        out.append({**q, "ref": ref, "stem": parts[0], "opts": parts[1],
                    "key": q["answer"].strip("()").upper()})
    out.sort(key=lambda q: (any(t.startswith("PY") for t in q["papers"]), _year(q)), reverse=True)
    return course, paper, out


def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


SOLVE_TOOL = {
    "name": "solve_pyq",
    "description": "Solve the past-paper MCQ and write the solution slide.",
    "input_schema": {"type": "object", "properties": {
        "your_answer": {"type": "string", "enum": LETTERS, "description": "The answer you get when you solve it yourself"},
        "topic": _s("Chapter or topic, at most 40 characters"),
        "question": _s("The question exactly as given; only fix broken spacing or obvious typos. At most 420 characters"),
        "options": {"type": "array", "minItems": 4, "maxItems": 4, "items": _s("Option text as given, cleaned the same way")},
        "explanation": _s("Why the answer is right, at most 260 characters"),
        "working": {"type": "array", "maxItems": 6, "description": "Short rough-work rows for numericals; empty for theory",
                    "items": {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                              "required": ["label", "value"]}},
        "why_not": {"type": "object", "description": "One short line, at most 80 characters, for each wrong option letter",
                    "properties": {l: {"type": "string"} for l in LETTERS}},
        "exam_tip": _s("One memorable tip, at most 140 characters"),
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
        "required": ["your_answer", "topic", "question", "options", "explanation", "working", "why_not", "exam_tip",
                     "confidence"]},
}

SOLVE_SYSTEM = """You write the solution slide for a real past-paper MCQ for Indian {course} students, paper: {paper}.
Solve it yourself first and give your answer in your_answer. Keep the question and options exactly as asked (fix only broken spacing or typos). Then explain the correct answer simply, as a teacher would: the rule or formula, the working for numericals (rough-work rows), one line on why each other option is wrong, and one exam tip. Simple Indian classroom English, no filler, no emoji. If the question depends on a law, rate or limit that has changed since it was set, say so by giving confidence "low"."""

CHECK_TOOL = {
    "name": "check_pyq",
    "description": "Report problems in the solution.",
    "input_schema": {"type": "object", "properties": {
        "issues": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["none", "minor", "major"]}},
        "required": ["issues", "severity"]},
}

CHECK_SYSTEM = """You are a strict examiner for {course}, paper: {paper}. Solve the MCQ yourself before reading the solution.
"major" if the stated answer is wrong, if the explanation, working or a "why not" line is wrong, or if the question rests on a law, rate or limit that is outdated now (then students would learn something false). "minor" for wording only. "none" otherwise."""


def _plain(it: dict) -> str:
    lines = [f"Question: {it['question']}"] + [f"({LETTERS[i]}) {o}" for i, o in enumerate(it["options"])]
    lines += [f"Stated answer: {it['correct']}", f"Explanation: {it['explanation']}"]
    lines += [f"Working: {w.get('label')}: {w.get('value')}" for w in it.get("working") or []]
    lines += [f"Why not {k}: {v}" for k, v in (it.get("why_not") or {}).items() if v]
    return "\n".join(lines + [f"Exam tip: {it.get('exam_tip', '')}"])


def make(cfg: Config, date: dt.date, instruction: str = "") -> dict:
    """Tonight's (or tomorrow's) PYQ item, solved and checked; not yet drawn."""
    from .generator import GenerationError, _call_claude, call_checker

    course, paper, cands = candidates(cfg, date)
    base = {"kind": PYQ, "course_id": course["id"], "paper_code": paper.get("code", ""),
            "paper_name": cfg.paper_title(paper) if paper else "", "tried": []}
    if not cands:
        return {**base, "error": "no unused past-paper MCQ with an answer key for this paper"}
    model = cfg.models.get("writer", "claude-sonnet-5-5")
    system = SOLVE_SYSTEM.format(course=course["name"], paper=cfg.paper_prompt(paper))
    check_system = CHECK_SYSTEM.format(course=course["name"], paper=cfg.paper_prompt(paper))
    notes = []
    for q in cands[: int(cfg.pyq.get("max_tries", 4))]:
        base["tried"].append(q["ref"])
        user = (f"Question: {q['stem']}\n" + "\n".join(f"({LETTERS[i]}) {o}" for i, o in enumerate(q["opts"]))
                + f"\nOfficial answer key: {q['key']}\nAsked in: {', '.join(q['papers'])}\n")
        if instruction:
            user += f"\nReviewer's instruction: {instruction}\n"
        try:
            s = _call_claude(model, system, user, SOLVE_TOOL, max_tokens=2000)
        except GenerationError as exc:
            notes.append(f"{q['ref']}: {exc}")
            continue
        if s.get("your_answer") != q["key"]:
            notes.append(f"{q['ref']}: Claude got {s.get('your_answer')}, the key says {q['key']}; skipped")
            continue
        if s.get("confidence") == "low":
            notes.append(f"{q['ref']}: may be outdated; skipped")
            continue
        it = {**base, "ref": q["ref"], "topic": s["topic"][:48], "question": s.get("question") or q["stem"],
              "options": (s.get("options") if len(s.get("options") or []) == 4 else q["opts"]),
              "correct": q["key"], "explanation": s["explanation"], "working": s.get("working") or [],
              "why_not": {k: v for k, v in (s.get("why_not") or {}).items() if v and k != q["key"]},
              "exam_tip": s.get("exam_tip", ""), "asked_in": asked_in(q["papers"]),
              "asked_short": asked_short(q["papers"]), "papers_tags": q["papers"]}
        check = call_checker(cfg, check_system, _plain(it), CHECK_TOOL, max_tokens=1500)
        if check.get("severity") == "major":
            notes.append(f"{q['ref']}: examiner: " + "; ".join(check.get("issues", []))[:200])
            continue
        it.update(check_notes=check.get("issues", []), notes=notes, hold=False, hold_reason="")
        return it
    return {**base, "error": "no question passed the checks", "notes": notes}


def caption(cfg: Config, item: dict, date: dt.date) -> str:
    from .caption import post_ref

    course = cfg.course(item["course_id"])
    handle = cfg.brand.get("handle", "").strip()
    lines = [f"📜 PYQ of the day · {course['name']}", f"{item['paper_code']}: {item['paper_name']}",
             f"Asked in the {item['asked_in']}" if item["asked_in"].endswith("exam") else f"From the {item['asked_in']}",
             "", "Try it first: comment your answer (A, B, C or D), then swipe for the solution.",
             "Save 🔖 it for revision: past papers repeat ideas."]
    if handle:
        lines += ["", f"Follow {handle} for a past-paper question every day."]
    tags = cfg.pyq.get("hashtags") or ["#PYQ", "#CMAInter", "#ICMAI", "#CMAExam", "#PastPapers"]
    lines += ["", " ".join(tags[: int(cfg.instagram.get("max_hashtags", 5))]), "", post_ref(PYQ, date)]
    return "\n".join(lines)[:2200]
