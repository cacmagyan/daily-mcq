"""Loads config.yaml and answers simple questions about it (dates, courses, papers, law basis)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue"
LETTERS = ["A", "B", "C", "D"]


class Config:
    def __init__(self, path: Path | None = None):
        path = path or ROOT / "config.yaml"
        with open(path, encoding="utf-8") as fh:
            self.raw = yaml.safe_load(fh)
        self.brand = self.raw["brand"]
        self.tz = ZoneInfo(self.raw.get("timezone", "Asia/Kolkata"))
        self.models = self.raw.get("models", {})
        self.review_mode = self.raw.get("review", {}).get("mode", "github_pr")
        self.instagram = self.raw.get("instagram", {})
        self.courses = self.raw["courses"]
        self.law_basis = self.raw.get("law_basis", {})
        self.start_date = dt.date.fromisoformat(str(self.brand.get("start_date")))

    # ── courses ────────────────────────────────────────────
    def course(self, course_id: str) -> dict:
        for c in self.courses:
            if c["id"] == course_id:
                return c
        raise KeyError(f"Unknown course id '{course_id}'. Known: {', '.join(self.course_ids())}")

    def course_ids(self) -> list[str]:
        return [c["id"] for c in self.courses]

    # ── dates ──────────────────────────────────────────────
    def now(self) -> dt.datetime:
        return dt.datetime.now(self.tz)

    def today(self) -> dt.date:
        return self.now().date()

    def resolve_date(self, value: str | None) -> dt.date:
        if not value or value == "tomorrow":
            return self.today() + dt.timedelta(days=1)
        if value == "today":
            return self.today()
        return dt.date.fromisoformat(value)

    def day_number(self, date: dt.date) -> int:
        return (date - self.start_date).days + 1

    # ── papers ─────────────────────────────────────────────
    def paper_for(self, course: dict, date: dt.date) -> dict:
        """One paper per day per course, cycling through the list in config order."""
        papers = course["papers"]
        return papers[(self.day_number(date) - 1) % len(papers)]

    def law_text(self, paper: dict, date: dt.date) -> str:
        key = paper.get("law")
        if not key:
            return ""
        for entry in self.law_basis.get(key, []):
            start = entry.get("from")
            end = entry.get("until")
            if start and date < dt.date.fromisoformat(str(start)):
                continue
            if end and date > dt.date.fromisoformat(str(end)):
                continue
            return entry["text"]
        return ""


def batch_dir(date: dt.date) -> Path:
    return QUEUE / date.isoformat()


def date_label(date: dt.date) -> str:
    return f"{date.day} {date.strftime('%b %Y')}"
