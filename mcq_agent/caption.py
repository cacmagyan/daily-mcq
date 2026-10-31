"""Instagram captions and image alt text for an MCQ and for the concept of the day."""

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
    if item.get("author"):
        lines += ["", f"Prepared by {item['author']}"]
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


def _plain(text: str) -> str:
    return (text or "").replace("==", "").replace("!!", "").strip()


def _clock(hhmm: str) -> str:
    """'12:25' -> '12:25 PM'."""
    t = dt.time.fromisoformat(hhmm)
    return f"{(t.hour % 12) or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _notes_cta(cfg: Config) -> str:
    from .replies import cta
    return cta(cfg)


def build_concept_caption(cfg: Config, item: dict, date: dt.date) -> str:
    course = cfg.course(item["course_id"])
    handle = cfg.brand.get("handle", "").strip()
    n = int(cfg.instagram.get("max_hashtags", 5))
    tags = ["#ConceptNotes"] + [t for t in course.get("hashtags", []) if t.lower() not in ("#dailymcq", "#conceptnotes")]
    slide2 = ("the formula" if item.get("formulas") else "the journal entries" if item.get("entries")
              else "the summary table")
    asked = sorted({t.strip() for p in item.get("past_papers") or [] for t in p.get("papers", "").split("·")[0].split(",")
                    if t.strip().startswith("PY")})
    lines = [
        f"📒 {course.get('emoji', '')} {course['name']} · Concept of the day".replace("  ", " "),
        f"{item['paper_code']}: {item['paper_name']}",
        f"{item['topic']}",
        "",
        f"In simple words: {_plain(item.get('simple_words'))}",
        *(["", f"📝 Asked in past papers: {', '.join(asked)}"] if asked else []),
        "",
        f"Swipe for {slide2}, a memory trick, the mistakes that cost marks"
        + (" and the past exam radar." if item.get("past_papers") else "."),
        "Save 🔖 this for revision.",
        *([_cta] if (_cta := _notes_cta(cfg)) else []),
        *([f"Tomorrow's {course['name']} MCQ ({_clock(course['post_time'])}) tests this concept."]
          if course["id"] in cfg.mcq_course_ids(date + dt.timedelta(days=1)) else []),
    ]
    if item.get("applicability"):
        lines += ["", f"Based on {item['applicability']}."]
    if item.get("author"):
        lines += ["", f"Notes by {item['author']}"]
    if handle:
        lines += ["", f"Follow {handle} for daily MCQs and concept notes."]
    lines += ["", " ".join(tags[:n]), "", post_ref(item.get("kind") or "concept", date)]
    return "\n".join(lines)[:2200]


def build_reel_caption(cfg: Config, item: dict, src: dict, date: dt.date) -> str:
    """Caption for the MCQ reel. `src` is the MCQ it shows."""
    course = cfg.course(item["course_id"])
    handle = cfg.brand.get("handle", "").strip()
    think = (item.get("seconds") or {}).get("think", 8)
    tags = course.get("hashtags", [])[: int(cfg.instagram.get("max_hashtags", 5))]
    lines = [
        f"⏱ {course.get('emoji', '')} {course['name']} · {think}-second MCQ challenge".replace("  ", " "),
        "",
        src.get("question", ""),
        "",
        "Comment A, B, C or D before the timer ends 👇 Pause if you need more time.",
        f"Full working: our {course['name']} MCQ post today at {_clock(course['post_time'])}.",
    ]
    if item.get("share_option"):
        lines.append("Send this to a friend who'd get it wrong 😄")       # the reel names the option; no spoiler here
    lines += [
        "",
        f"{item['paper_code']}: {item['paper_name']} · Topic: {item['topic']}",
    ]
    if src.get("applicability"):
        lines.append(f"Based on {src['applicability']}.")
    if item.get("author"):
        lines += [f"Prepared by {item['author']}"]
    if handle:
        lines += ["", f"Follow {handle} for a daily MCQ in every CA and CMA level."]
    lines += ["", " ".join(tags), "", post_ref("reel", date)]
    return "\n".join(lines)[:2200]


def concept_alt_texts(item: dict) -> list[str]:
    """One alt text per slide, in slide order."""
    topic = _plain(item.get("topic"))
    defs = " ".join(f"{d.get('term')}: {_plain(d.get('meaning'))}" for d in item.get("definitions") or [])
    points = " ".join(f"{i}. {_plain(p)}" for i, p in enumerate(item.get("key_points") or [], 1))
    one = f"Concept note: {topic}. In simple words: {_plain(item.get('simple_words'))} {defs} {points}"
    parts = []
    for f in item.get("formulas") or []:
        rhs = f.get("rhs") or f"({f.get('numerator')}) divided by ({f.get('denominator')})"
        if f.get("denominator") and f.get("square_root"):
            rhs = f"square root of {rhs}"
        parts.append(f"{f.get('name')}: {f.get('lhs')} = {rhs} {f.get('suffix') or ''}. {f.get('legend') or ''}")
    table = item.get("table") or {}
    for row in table.get("rows") or []:
        parts.append(", ".join(f"{h}: {_plain(c)}" for h, c in zip(table.get("headers") or [], row)))
    for e in item.get("entries") or []:
        parts.append(f"Journal entry, {e.get('label', '')}: " + ", ".join(f"{a} debit" for a in e.get("debit") or [])
                     + ", " + ", ".join(f"to {a}" for a in e.get("credit") or []) + ".")
    insight = item.get("insight") or {}
    two = f"{topic}. " + " ".join(parts) + f" {insight.get('punchline', '')} {_plain(insight.get('text'))}"
    trick = item.get("memory_trick") or {}
    doubt = item.get("doubt") or {}
    three = (f"Study trick for {topic}: {trick.get('mnemonic', '')}. {_plain(trick.get('explanation'))} "
             f"Steps: {'; '.join(item.get('steps') or [])}. Exam tip: {_plain(item.get('exam_tip'))} "
             f"Doubt: {doubt.get('question', '')} {_plain(doubt.get('answer'))}")
    four = f"Common mistakes in {topic}: " + " ".join(
        f"Wrong: {_plain(m.get('wrong'))} Right: {_plain(m.get('right'))}" for m in item.get("mistakes") or []) + "".join(
        f" Past exam: {p.get('papers', '')}, {_plain(p.get('point'))}." for p in item.get("past_papers") or [])
    return [" ".join(t.split())[:900] for t in (one, two, three, four)]
