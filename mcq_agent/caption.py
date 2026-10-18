"""Instagram caption and image alt text for one MCQ."""

from __future__ import annotations

import datetime as dt

from .config import LETTERS, Config


def post_ref(course_id: str, date: dt.date) -> str:
    """Short marker at the end of each caption; lets the publisher spot a post it already made."""
    return f"ref {course_id.replace('_', '-')}-{date.strftime('%y%m%d')}"


def colour_key(cfg: Config) -> str:
    rows = {}
    for c in cfg.courses:
        rows.setdefault(c.get("body", ""), []).append(f"{c.get('emoji', '')} {c['name']}".strip())
    return "\n".join("  ".join(names) for _, names in sorted(rows.items()))


def build_caption(cfg: Config, item: dict, date: dt.date) -> str:
    course = cfg.course(item["course_id"])
    handle = cfg.brand.get("handle", "").strip()
    tags = course.get("hashtags", [])[: int(cfg.instagram.get("max_hashtags", 5))]
    lines = [
        f"{course.get('emoji', '')} {course['name']} · MCQ of the day · Day {cfg.day_number(date)}".strip(),
        f"{item['paper_code']}: {item['paper_name']}",
        f"Topic: {item['topic']}",
        "",
        "Try it before you swipe. Comment A, B, C or D 👇",
        "Slide 2 has the answer with the full working.",
    ]
    if item.get("applicability"):
        lines += ["", f"Based on {item['applicability']}."]
    lines += ["", "Find your course by colour:", colour_key(cfg)]
    if handle:
        lines += ["", f"Follow {handle} for one MCQ a day in every course."]
    lines += ["", " ".join(tags), "", post_ref(item["course_id"], date)]
    caption = "\n".join(lines)
    return caption[:2200]


def alt_texts(item: dict) -> dict:
    opts = "; ".join(f"{l}) {o}" for l, o in zip(LETTERS, item["options"]))
    q = f"MCQ, {item['paper_code']} {item['paper_name']}. {item['question']} Options: {opts}."
    ans = item["options"][LETTERS.index(item["correct"])]
    a = f"Answer: option {item['correct']}, {ans}. {item['explanation']}"
    if item.get("exam_tip"):
        a += f" Exam tip: {item['exam_tip']}"
    return {"question": q[:900], "answer": a[:900]}
