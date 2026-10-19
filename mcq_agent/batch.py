"""Reading and writing the daily batch files under queue/YYYY-MM-DD/."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .config import QUEUE, batch_dir


def batch_path(date: dt.date) -> Path:
    return batch_dir(date) / "mcqs.json"


def load_batch(date: dt.date) -> dict | None:
    p = batch_path(date)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_batch(date: dt.date, batch: dict) -> Path:
    p = batch_path(date)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(batch, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return p


def find_item(batch: dict, course_id: str) -> dict | None:
    return next((it for it in batch["items"] if it["course_id"] == course_id), None)


def load_posted(date: dt.date) -> dict:
    p = batch_dir(date) / "posted.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_posted(date: dt.date, posted: dict) -> None:
    p = batch_dir(date) / "posted.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(posted, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def merge_posted(saved: Path) -> list[str]:
    """Adds records from saved copies (saved/queue/<date>/posted.json) to the current queue.
    A record already in the queue is kept as it is. Returns what was added."""
    added = []
    for src in sorted(Path(saved).glob("queue/*/posted.json")):
        dest = QUEUE / src.parent.name / "posted.json"
        with open(src, encoding="utf-8") as fh:
            mine = json.load(fh)
        theirs = {}
        if dest.exists():
            with open(dest, encoding="utf-8") as fh:
                theirs = json.load(fh)
        new = sorted(set(mine) - set(theirs))
        if new:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                json.dump({**mine, **theirs}, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            added += [f"{src.parent.name}: {k}" for k in new]
    return added


def recent_items(course_id: str, before: dt.date, limit: int = 60) -> list[dict]:
    """Other days' MCQs for a course (earlier and already-prepared later days), newest first,
    so the writer can avoid repeating topics."""
    found = []
    if not QUEUE.exists():
        return found
    for d in sorted(QUEUE.iterdir(), reverse=True):
        try:
            day = dt.date.fromisoformat(d.name)
        except ValueError:
            continue
        if day == before or not (d / "mcqs.json").exists():
            continue
        with open(d / "mcqs.json", encoding="utf-8") as fh:
            for it in json.load(fh).get("items", []):
                if it.get("course_id") == course_id and it.get("question"):
                    found.append({"date": d.name, "topic": it.get("topic", ""), "question": it.get("question", "")})
        if len(found) >= limit:
            break
    return found[:limit]


# ── concept of the day: queue/YYYY-MM-DD/concept.json ───────────────────────

def concept_path(date: dt.date) -> Path:
    return batch_dir(date) / "concept.json"


def load_concept(date: dt.date) -> dict | None:
    p = concept_path(date)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_concept(date: dt.date, item: dict) -> Path:
    p = concept_path(date)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(item, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return p


def recent_concepts(course_id: str, before: dt.date, limit: int = 60) -> list[str]:
    """Topics of other days' concept notes for a course, newest first."""
    found = []
    if not QUEUE.exists():
        return found
    for d in sorted(QUEUE.iterdir(), reverse=True):
        if d.name == before.isoformat() or not (d / "concept.json").exists():
            continue
        with open(d / "concept.json", encoding="utf-8") as fh:
            it = json.load(fh)
        if it.get("course_id") == course_id and it.get("topic"):
            found.append(it["topic"])
        if len(found) >= limit:
            break
    return found
