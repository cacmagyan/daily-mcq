"""Builds the pull-request description you review each evening."""

from __future__ import annotations

import datetime as dt
import hashlib

from .batch import load_batch
from .config import LETTERS, Config, batch_dir


def _img(repo: str, branch: str, date: dt.date, name: str) -> str:
    path = batch_dir(date) / name
    v = hashlib.md5(path.read_bytes()).hexdigest()[:8] if path.exists() else "0"
    return f"https://github.com/{repo}/raw/{branch}/queue/{date.isoformat()}/{name}?v={v}"


def pr_body(cfg: Config, date: dt.date, repo: str, branch: str) -> str:
    batch = load_batch(date)
    if not batch:
        return f"No batch found for {date}."
    lines = [
        f"## MCQs for {date.strftime('%A %d %B %Y')} · Day {cfg.day_number(date)}",
        "",
        "**Merge this pull request to approve.** Each MCQ posts at its time below. "
        "If it isn't merged, nothing is posted.",
        "",
        "| Time | Course | Paper | Topic | Key | Check |",
        "|---|---|---|---|---|---|",
    ]
    details = []
    for it in sorted(batch["items"], key=lambda i: cfg.course(i["course_id"])["post_time"]):
        c = cfg.course(it["course_id"])
        if it.get("error"):
            lines.append(f"| {c['post_time']} | {c.get('emoji','')} {c['name']} | {it['paper_code']} | – | – | ❌ failed |")
            details.append(f"### {c.get('emoji','')} {c['name']}\n❌ Could not write this MCQ: `{it['error'][:200]}`\n"
                           f"Comment `/regen {c['id']}` to try again.\n")
            continue
        flags = []
        if it.get("needs_check"):
            flags.append("⚠️ look closely")
        if it.get("law_sensitive"):
            flags.append("⚖️ law")
        if it.get("fit_notes"):
            flags.append("✂️ long text")
        status = " ".join(flags) or "✅"
        lines.append(f"| {c['post_time']} | {c.get('emoji','')} {c['name']} | {it['paper_code']} | "
                     f"{it.get('topic','')} | {it['correct']} | {status} |")
        notes = list(it.get("check_notes", [])) + list(it.get("fit_notes", []))
        if it.get("applicability"):
            notes.insert(0, f"Law basis: {it['applicability']}")
        q = _img(repo, branch, date, it["images"]["question"])
        a = _img(repo, branch, date, it["images"]["answer"])
        block = [f"### {c.get('emoji','')} {c['name']}: {it.get('topic','')}",
                 f'<img src="{q}" width="300"> <img src="{a}" width="300">', ""]
        block.append(f"**Key:** {it['correct']}. {it['options'][LETTERS.index(it['correct'])]}")
        if notes:
            block += [""] + [f"- {n}" for n in notes]
        details.append("\n".join(block) + "\n")
    lines += ["", *details,
              "---",
              "### To change something",
              f"- **Edit text:** open *Files changed*, edit `queue/{date.isoformat()}/mcqs.json` (pencil icon), commit. "
              "The images redraw by themselves in about two minutes.",
              "- **Rewrite one MCQ:** comment `/regen <course>` e.g. `/regen ca_inter`, optionally with an instruction: "
              "`/regen cma_final make it a numerical on WACC`.",
              f"- **Skip the whole day:** close this pull request. Course ids: {', '.join(cfg.course_ids())}"]
    return "\n".join(lines)
