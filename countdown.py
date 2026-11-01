"""Exam countdown: a daily Story, "40 days to CMA Inter", with one must-revise topic.

It follows the day's MCQ family (CMA on a CMA day, CA on a CA day); the exams of that family take
turns. The topic comes from the exam course's paper of the day; for papers with a question bank,
Claude is shown the sections past papers ask most. A topic that doesn't pass the check is left out:
the Story then shows only the days left (it never stops the countdown)."""

from __future__ import annotations

import datetime as dt
import json

from .config import Config, batch_dir

COUNTDOWN = "countdown"


def path(date: dt.date):
    return batch_dir(date) / "countdown.json"


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


def exam_for(cfg: Config, date: dt.date) -> dict | None:
    """The exam to count down to on this date: the day's MCQ family, exams taking turns."""
    fam = (cfg.mcq_course_ids(date) or [""])[0].split("_")[0]          # "ca" or "cma"
    exams = [e for e in cfg.countdown.get("exams") or []
             if str(e.get("course", "")).split("_")[0] == fam and dt.date.fromisoformat(str(e["date"])) >= date]
    if not exams:                     # nothing ahead for today's family: any exam still ahead
        exams = [e for e in cfg.countdown.get("exams") or [] if dt.date.fromisoformat(str(e["date"])) >= date]
    if not exams:
        return None
    exams.sort(key=lambda e: str(e["date"]))
    return exams[date.toordinal() // 2 % len(exams)]


def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


TOPIC_TOOL = {
    "name": "pick_topic",
    "description": "One must-revise topic for today.",
    "input_schema": {"type": "object", "properties": {
        "topic": _s("A frequently examined topic of this paper, at most 40 characters"),
        "tip": _s("One correct, practical revision line for it, at most 100 characters"),
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
        "required": ["topic", "tip", "confidence"]},
}

TOPIC_SYSTEM = """You pick today's must-revise topic for Indian {course} students, {days} days before their exam. Paper: {paper}.
Choose one topic that is examined often and fits the paper's syllabus, different from the recent ones listed. The tip is one short, correct, practical line (what to revise or the point most students miss). Simple English, no emoji."""

CHECK_TOOL = {
    "name": "check_topic",
    "description": "Report problems.",
    "input_schema": {"type": "object", "properties": {
        "issues": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["none", "minor", "major"]}},
        "required": ["issues", "severity"]},
}

CHECK_SYSTEM = """Check a one-line revision tip for {course} students, paper: {paper}. "major" if the topic is outside the paper's syllabus or the tip is wrong or misleading; "minor" for wording; "none" if correct."""


def recent_topics(date: dt.date, days: int = 30) -> list[str]:
    out = []
    for i in range(1, days + 1):
        c = load(date - dt.timedelta(days=i)) or {}
        if c.get("topic"):
            out.append(c["topic"])
    return out


def make(cfg: Config, date: dt.date, instruction: str = "") -> dict:
    from . import pyq
    from .generator import GenerationError, _call_claude, call_checker

    exam = exam_for(cfg, date)
    if not exam:
        return {"kind": COUNTDOWN, "error": "no exam date ahead in config.yaml (countdown.exams)"}
    exam_date = dt.date.fromisoformat(str(exam["date"]))
    days = (exam_date - date).days
    course = cfg.course(exam["course"])
    paper = cfg.paper_for(course, date)
    item = {"kind": COUNTDOWN, "course_id": course["id"], "exam": exam["name"], "exam_date": exam_date.isoformat(),
            "days": days, "paper_code": paper["code"], "paper_name": cfg.paper_title(paper), "topic": "", "tip": "",
            "hold": False, "hold_reason": ""}
    user = f"Recent topics (choose another):\n" + "\n".join(f"- {t}" for t in recent_topics(date)[:20] or ["none"])
    bank = pyq.questions(course["id"], paper)
    if bank:
        user += "\nSections past papers ask most:\n" + pyq.section_counts(bank, 15)
    if instruction:
        user += f"\nReviewer's instruction: {instruction}"
    try:
        model = cfg.models.get("writer", "claude-sonnet-5-5")
        sysp = TOPIC_SYSTEM.format(course=course["name"], days=days, paper=cfg.paper_prompt(paper))
        t = _call_claude(model, sysp, user, TOPIC_TOOL, max_tokens=500)
        topic, tip = t.get("topic", "")[:48], t.get("tip", "")[:120]
        check = call_checker(cfg, CHECK_SYSTEM.format(course=course["name"], paper=cfg.paper_prompt(paper)),
                             f"Topic: {topic}\nTip: {tip}", CHECK_TOOL, max_tokens=600)
        if topic and tip and t.get("confidence") != "low" and check.get("severity") != "major":
            item.update(topic=topic, tip=tip)
        else:
            item["notes"] = ["topic left out: " + "; ".join(check.get("issues", []) or ["unsure"])[:200]]
    except GenerationError as exc:
        item["notes"] = [f"topic left out: {exc}"[:200]]
    return item
