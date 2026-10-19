"""Builds the pull-request description you review each evening."""

from __future__ import annotations

import datetime as dt
import hashlib

from .batch import load_batch, load_concept
from .config import LETTERS, Config, batch_dir

CONCEPT = "concept"


def _concept_block(cfg: Config, c: dict, repo: str, branch: str, date: dt.date) -> list[str]:
    course = cfg.course(c["course_id"])
    out = [f"### 📒 Concept of the day ({course.get('emoji', '')} {course['name']}): {c.get('topic', '')}"]
    if c.get("error"):
        return out + [f"❌ Could not write the concept note: `{c['error'][:200]}`",
                      "Comment `/regen concept` to try again.", ""]
    imgs = " ".join(f'<img src="{_img(repo, branch, date, n)}" width="220">' for n in c.get("images", []))
    out += [imgs, "", f"**Paper:** {c.get('paper_code', '')} {c.get('paper_name', '')} · **Signed:** {c.get('author', '')}"]
    notes = list(c.get("check_notes", [])) + list(c.get("fit_notes", []))
    if c.get("applicability"):
        notes.insert(0, f"Law basis: {c['applicability']}")
    out += ([""] + [f"- {n}" for n in notes]) if notes else []
    return out + [""]


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
    concept = load_concept(date)
    if concept:
        lines.append(f"| {cfg.concept_time()} | 📒 Concept ({cfg.course(concept['course_id'])['name']}) | "
                     f"{concept.get('paper_code', '')} | {concept.get('topic', '–')} | – | "
                     f"{'❌ failed' if concept.get('error') else '⚠️ look closely' if concept.get('needs_check') else '✅'} |")
        details.append("\n".join(_concept_block(cfg, concept, repo, branch, date)))
    lines += ["", *details,
              "---",
              "### To change something",
              f"- **Edit text:** open *Files changed*, edit `queue/{date.isoformat()}/mcqs.json` (pencil icon), commit. "
              "The images redraw by themselves in about two minutes.",
              "- **Rewrite one MCQ:** comment `/regen <course>` e.g. `/regen ca_inter`, optionally with an instruction: "
              "`/regen cma_final make it a numerical on WACC`.",
              f"- **Skip the whole day:** close this pull request. Course ids: {', '.join(cfg.course_ids())}"]
    return "\n".join(lines)


def report(cfg: Config, date: dt.date, repo: str, branch: str = "main", owner: str = "") -> str:
    """The daily issue in auto mode: what posts when, what is on hold, and what already went out."""
    from .batch import load_posted

    batch = load_batch(date)
    if not batch:
        return f"No MCQs were prepared for {date}."
    posted = load_posted(date)
    items = sorted(batch["items"], key=lambda i: cfg.course(i["course_id"])["post_time"])
    concept = load_concept(date)
    held = [it for it in items if (it.get("hold") or it.get("error")) and it["course_id"] not in posted]
    concept_held = bool(concept and (concept.get("hold") or concept.get("error")) and CONCEPT not in posted)
    n_held = len(held) + concept_held
    n_posts = len(items) + bool(concept)
    mention = f"@{owner} " if owner else ""

    lines = [f"## MCQs for {date.strftime('%A %d %B %Y')} · Day {cfg.day_number(date)}", ""]
    if n_held:
        what = "post" if concept_held and not held else "MCQ"
        lines += [f"{mention}**⛔ {n_held} {what}{'s' if n_held > 1 else ''} on hold.** "
                  "They won't post until you act (see below). The others post automatically.", ""]
    else:
        words = {5: "five", 6: "six", 7: "seven", 8: "eight"}
        lines += [f"**All {words.get(n_posts, n_posts)} post automatically** at the times below. Nothing needs your action.", ""]
    lines += ["| Time | Course | Topic | Key | Status |", "|---|---|---|---|---|"]
    rows = [(cfg.course(it["course_id"])["post_time"], it) for it in items]
    if concept:
        rows.append((cfg.concept_time(), concept))
    for _, it in sorted(rows, key=lambda r: r[0]):
        is_concept = it.get("kind") == CONCEPT
        c = cfg.course(it["course_id"])
        cid = CONCEPT if is_concept else it["course_id"]
        if cid in posted:
            link = posted[cid].get("permalink") or ""
            status = f"✅ [posted]({link})" if link else "✅ posted"
        elif it.get("error"):
            status = "❌ couldn't be written"
        elif it.get("hold"):
            status = f"⛔ on hold: {it.get('hold_reason', '')}"
        else:
            notes = []
            if it.get("needs_check"):
                notes.append("⚠️ note")
            if it.get("law_sensitive"):
                notes.append("⚖️ law")
            status = "🕒 will post" + (f" ({', '.join(notes)})" if notes else "")
        key = it.get("correct", "–")
        when = cfg.concept_time() if is_concept else c["post_time"]
        label = f"📒 Concept ({c['name']})" if is_concept else f"{c.get('emoji', '')} {c['name']}"
        lines.append(f"| {when} | {label} | {it.get('topic', '–')} | {key} | {status} |")

    def block(it: dict) -> list[str]:
        c = cfg.course(it["course_id"])
        out = [f"### {c.get('emoji', '')} {c['name']}: {it.get('topic', '')}"]
        if it.get("error"):
            return out + [f"❌ Could not write this MCQ: `{it['error'][:200]}`", f"Comment `/regen {c['id']}` to try again.", ""]
        q = _img(repo, branch, date, it["images"]["question"])
        a = _img(repo, branch, date, it["images"]["answer"])
        out += [f'<img src="{q}" width="300"> <img src="{a}" width="300">', "",
                f"**Key:** {it['correct']}. {it['options'][LETTERS.index(it['correct'])]}"]
        notes = list(it.get("check_notes", [])) + list(it.get("fit_notes", []))
        if it.get("applicability"):
            notes.insert(0, f"Law basis: {it['applicability']}")
        out += [""] + [f"- {n}" for n in notes] if notes else []
        return out + [""]

    if held:
        lines += ["", "## ⛔ On hold: please look", ""]
        for it in held:
            cid = it["course_id"]
            lines += block(it) + [f"**To fix:** comment `/approve {cid}` to post it as it is, `/regen {cid}` for a new "
                                  f"MCQ (add an instruction if you like), or edit `queue/{date.isoformat()}/mcqs.json`.", ""]
    if concept_held:
        if not held:
            lines += ["", "## ⛔ On hold: please look", ""]
        lines += _concept_block(cfg, concept, repo, branch, date) + [
            "**To fix:** comment `/approve concept` to post it as it is, `/regen concept` for a new note on the same "
            f"concept (add an instruction to change it), or edit `queue/{date.isoformat()}/concept.json`.", ""]
    rest = [it for it in items if it not in held]
    if rest:
        lines += ["", "## All MCQs for the day", ""]
        for it in rest:
            lines += block(it)
    if concept and not concept_held:
        lines += ["", "## Concept of the day", ""] + _concept_block(cfg, concept, repo, branch, date)
    lines += ["---", "### Commands (comment on this issue)",
              "- `/hold <course>`: stop an MCQ from posting, e.g. you spotted a mistake",
              "- `/approve <course>`: post a held MCQ as it is",
              "- `/regen <course> [instruction]`: replace it with a new MCQ; it posts automatically if the check passes",
              f"- Edit `queue/{date.isoformat()}/mcqs.json` to change text; the images redraw by themselves",
              f"- Course ids: {', '.join(cfg.course_ids())}" + (", and `concept` for the concept note" if concept else ""),
              "", "_Posted MCQs can't be changed from here; edit or delete them in the Instagram app._"]
    return "\n".join(lines)


def report_title(cfg: Config, date: dt.date) -> str:
    """'⛔ Action needed: …' while something is on hold, so the issue list shows what needs you."""
    from .batch import load_posted

    batch = load_batch(date) or {"items": []}
    posted = load_posted(date)
    held = [it for it in batch["items"] if (it.get("hold") or it.get("error")) and it["course_id"] not in posted]
    concept = load_concept(date)
    if concept and (concept.get("hold") or concept.get("error")) and CONCEPT not in posted:
        held.append(concept)
    base = f"MCQs for {date.isoformat()} (Day {cfg.day_number(date)})"
    return f"⛔ Action needed: {base}" if held else base
