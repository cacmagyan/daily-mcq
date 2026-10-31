"""Builds the pull-request description you review each evening."""

from __future__ import annotations

import datetime as dt
import hashlib

from .batch import load_batch, load_concept, load_reel
from .config import LETTERS, Config, batch_dir

CONCEPT = "concept"
REEL = "reel"
EXPLAINER = "explainer"
SLOTS = ("", "2")              # the evening note and video, and the day's second note and video


def _explainer(cfg: Config, date: dt.date, slot: str = "") -> dict | None:
    """The day's explainer record, marked held when its concept note changed after it was made."""
    from . import explainer as X

    if not cfg.explainer.get("enabled"):
        return None
    ex = X.load(date, slot)
    if ex and not ex.get("error") and not ex.get("hold"):
        why = X.problem(ex, load_concept(date, slot))
        if why:
            ex = {**ex, "hold": True, "hold_reason": why}
    return ex


def _explainer_block(cfg: Config, e: dict, repo: str, branch: str, date: dt.date) -> list[str]:
    course = cfg.course(e["course_id"]) if e.get("course_id") else {"name": "", "emoji": ""}
    key = e.get("kind") or EXPLAINER
    out = [f"### 🎬 Cartoon explainer ({course.get('emoji', '')} {course['name']}): {e.get('topic', '')}"]
    if e.get("error"):
        backup = (f"The MCQ reel posts at {cfg.reel_time()} instead." if cfg.reels.get("enabled") and key == EXPLAINER
                  else "This video doesn't post unless it is made again.")
        return out + [f"❌ Could not make it: `{e['error'][:200]}`. {backup}",
                      f"Comment `/regen {key}` to try again.", ""]
    video = f"https://github.com/{repo}/raw/{branch}/queue/{date.isoformat()}/{e.get('video', 'explainer.mp4')}"
    script = e.get("script") or {}
    out += [f'<a href="{video}"><img src="{_img(repo, branch, date, e.get("cover", "explainer_cover.jpg"))}" width="220"></a>', "",
            f"[▶ Watch it]({video}) · {e.get('seconds', 0):g} seconds · {script.get('title', '')}", "",
            "<details><summary>What the voice says</summary>", ""]
    if script.get("lines"):
        names = {"teacher": "🐘 Teacher", "girl": "👧 Girl", "boy": "👦 Boy"}
        out += [f"{i}. **{names.get(ln.get('who'), ln.get('who'))}:** {ln.get('say', '')}"
                for i, ln in enumerate(script["lines"], 1)]
    else:
        out += [f"{i}. {sc.get('say', '')}" for i, sc in enumerate(script.get("scenes") or [], 1)]
    out += ["", "</details>"]
    notes = list(e.get("check_notes") or [])
    out += ([""] + [f"- {n}" for n in notes]) if notes else []
    return out + [""]


def _reel(cfg: Config, date: dt.date, batch: dict | None) -> dict | None:
    """The day's reel record, marked held when its MCQ is on hold or was changed after it was made."""
    from .reel import problem

    r = load_reel(date) if cfg.reels.get("enabled") else None
    if r and not r.get("error") and not r.get("hold"):
        why = problem(r, batch)
        if why:
            r = {**r, "hold": True, "hold_reason": why}
    return r


def _reel_block(cfg: Config, r: dict, repo: str, branch: str, date: dt.date) -> list[str]:
    course = cfg.course(r["course_id"])
    out = [f"### 🎬 MCQ reel ({course.get('emoji', '')} {course['name']}): {r.get('topic', '')}"]
    if r.get("error"):
        return out + [f"❌ Could not make the reel: `{r['error'][:200]}`", "Comment `/regen reel` to try again.", ""]
    video = f"https://github.com/{repo}/raw/{branch}/queue/{date.isoformat()}/{r.get('video', 'reel.mp4')}"
    out += [f'<a href="{video}"><img src="{_img(repo, branch, date, r.get("cover", "reel_cover.jpg"))}" width="220"></a>', "",
            f"[▶ Watch the reel]({video}) · {sum((r.get('seconds') or {}).values()):g} seconds · "
            f"shows the {course['name']} MCQ (key {r.get('correct', '?')})"]
    voice = f"🔊 Voice: {r['voice']}" if r.get("voice") else f"🔇 No voice: {r['voice_note']}" if r.get("voice_note") else ""
    who = f"Presented by {r.get('author')}" if r.get("presenter") else "No presenter (text too long to fit beside him)" \
        if r.get("presenter") is False and r.get("author") else ""
    notes = [n for n in (r.get("note"), "The reason was shortened to fit" if r.get("short_reason") else "", who, voice) if n]
    out += ([""] + [f"- {n}" for n in notes]) if notes else []
    return out + [""]


def _concept_block(cfg: Config, c: dict, repo: str, branch: str, date: dt.date) -> list[str]:
    course = cfg.course(c["course_id"])
    key = c.get("kind") or CONCEPT
    out = [f"### 📒 Concept note ({course.get('emoji', '')} {course['name']}): {c.get('topic', '')}"]
    if c.get("error"):
        return out + [f"❌ Could not write the concept note: `{c['error'][:200]}`",
                      f"Comment `/regen {key}` to try again.", ""]
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
    todays = set(cfg.mcq_course_ids(date))
    for it in sorted([i for i in batch["items"] if i["course_id"] in todays],
                     key=lambda i: cfg.course(i["course_id"])["post_time"]):
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
    for slot in SLOTS:
        concept = load_concept(date, slot)
        if concept:
            lines.append(f"| {cfg.concept_time(slot)} | 📒 Concept ({cfg.course(concept['course_id'])['name']}) | "
                         f"{concept.get('paper_code', '')} | {concept.get('topic', '–')} | – | "
                         f"{'❌ failed' if concept.get('error') else '⚠️ look closely' if concept.get('needs_check') else '✅'} |")
            details.append("\n".join(_concept_block(cfg, concept, repo, branch, date)))
    reel = _reel(cfg, date, batch)
    if reel:
        lines.append(f"| {cfg.reel_time()} | 🎬 Reel ({cfg.course(reel['course_id'])['name']}) | – | "
                     f"{reel.get('topic', '–')} | {reel.get('correct', '–')} | "
                     f"{'❌ failed' if reel.get('error') else '⛔ ' + reel.get('hold_reason', '') if reel.get('hold') else '✅'} |")
        details.append("\n".join(_reel_block(cfg, reel, repo, branch, date)))
    for slot in SLOTS:
        ex = _explainer(cfg, date, slot)
        if ex:
            lines.append(f"| {cfg.explainer_time(slot)} | 🎬 Explainer | – | {ex.get('topic', '–')} | – | "
                         f"{'❌ failed' if ex.get('error') else '⛔ ' + ex.get('hold_reason', '') if ex.get('hold') else '✅'} |")
            details.append("\n".join(_explainer_block(cfg, ex, repo, branch, date)))
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
    todays = set(cfg.mcq_course_ids(date))
    items = sorted([i for i in batch["items"] if i["course_id"] in todays or i["course_id"] in posted],
                   key=lambda i: cfg.course(i["course_id"])["post_time"])
    concepts = [c for c in (load_concept(date, slot) for slot in SLOTS) if c]
    concept = concepts[0] if concepts else None
    held = [it for it in items if (it.get("hold") or it.get("error")) and it["course_id"] not in posted]
    concepts_held = [c for c in concepts if (c.get("hold") or c.get("error")) and (c.get("kind") or CONCEPT) not in posted]
    concept_held = bool(concepts_held)
    reel = _reel(cfg, date, batch)
    exs = [e for e in (_explainer(cfg, date, slot) for slot in SLOTS) if e]
    ex = _explainer(cfg, date)
    ex_ok = bool(ex and REEL not in posted and (EXPLAINER in posted or (not ex.get("error") and not ex.get("hold"))))
    reel_held = bool(reel and not ex_ok and (reel.get("hold") or reel.get("error")) and REEL not in posted)
    from . import news as N
    news = N.load(date) if cfg.news_due(date) else None
    news_held = bool(news and (news.get("hold") or news.get("error")) and "news" not in posted)
    n_held = len(held) + len(concepts_held) + reel_held + news_held
    n_posts = (len(items) + len(concepts) + bool(reel or ex) + len([e for e in exs if e.get("kind") != EXPLAINER])
               + bool(news))
    mention = f"@{owner} " if owner else ""

    lines = [f"## MCQs for {date.strftime('%A %d %B %Y')} · Day {cfg.day_number(date)}", ""]
    if n_held:
        what = "post" if (concept_held or reel_held or news_held) and not held else "MCQ"
        lines += [f"{mention}**⛔ {n_held} {what}{'s' if n_held > 1 else ''} on hold.** "
                  "They won't post until you act (see below). The others post automatically.", ""]
    else:
        words = {5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
        lines += [f"**All {words.get(n_posts, n_posts)} post automatically** at the times below. Nothing needs your action.", ""]
    lines += ["| Time | Course | Topic | Key | Status |", "|---|---|---|---|---|"]

    def when_of(it: dict) -> str:
        kind = it.get("kind") or ""
        slot = "2" if kind.endswith("2") else ""
        if kind.startswith(CONCEPT):
            return cfg.concept_time(slot)
        if kind.startswith(EXPLAINER):
            return cfg.explainer_time(slot)
        if kind == REEL:
            return cfg.reel_time()
        if kind == "news":
            return cfg.news_time()
        return cfg.course(it["course_id"])["post_time"]

    rows = [(when_of(it), it) for it in items + concepts + exs + ([reel] if reel else []) + ([news] if news else [])]
    for when, it in sorted(rows, key=lambda r: r[0]):
        kind = it.get("kind") or ""
        is_concept = kind.startswith(CONCEPT)
        is_ex = kind.startswith(EXPLAINER)
        is_reel = kind == REEL or is_ex
        is_news = kind == "news"
        c = cfg.course(it["course_id"]) if it.get("course_id") else {"name": "", "emoji": "", "post_time": ""}
        cid = kind if (is_concept or is_reel or is_news) else it["course_id"]
        if cid in posted:
            link = posted[cid].get("permalink") or ""
            status = f"✅ [posted]({link})" if link else "✅ posted"
            if f"{cid}:story" in posted:
                status += " · 📱 story"
        elif kind == REEL and ex_ok:
            status = "backup: posts only if the explainer can't"
        elif kind == EXPLAINER and REEL in posted:
            status = "not posted: the MCQ reel took the slot"
        elif it.get("error"):
            status = ("❌ couldn't be made" if is_reel else "❌ couldn't be written") + (
                ", so the MCQ reel posts instead" if kind == EXPLAINER and cfg.reels.get("enabled") else "")
        elif it.get("hold"):
            status = f"⛔ on hold: {it.get('hold_reason', '')}" + (
                ", so the MCQ reel posts instead" if kind == EXPLAINER and cfg.reels.get("enabled") else "")
        else:
            notes = []
            if it.get("needs_check"):
                notes.append("⚠️ note")
            if it.get("law_sensitive"):
                notes.append("⚖️ law")
            status = "🕒 will post" + (f" ({', '.join(notes)})" if notes else "")
        key = it.get("correct", "–")
        if is_news:
            it = dict(it, topic=" · ".join(x["tag"] for x in it.get("stories") or []) or "–")
        label = ("📰 News" if is_news else f"📒 Concept ({c['name']})" if is_concept else f"🎬 Explainer ({c['name']})"
                 if is_ex else f"🎬 MCQ reel ({c['name']})" if is_reel
                 else f"{c.get('emoji', '')} {c['name']}")
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
    if reel_held:
        if not held and not concept_held:
            lines += ["", "## ⛔ On hold: please look", ""]
        lines += _reel_block(cfg, reel, repo, branch, date) + [
            "**To fix:** comment `/regen reel` to make it again (it uses another MCQ if this one is on hold), "
            "or `/approve reel` if you put it on hold yourself.", ""]
    for c in concepts_held:
        k = c.get("kind") or CONCEPT
        if not held and not reel_held and c is concepts_held[0]:
            lines += ["", "## ⛔ On hold: please look", ""]
        lines += _concept_block(cfg, c, repo, branch, date) + [
            f"**To fix:** comment `/approve {k}` to post it as it is, `/regen {k}` for a new note on the same "
            f"concept (add an instruction to change it), or edit `queue/{date.isoformat()}/{k}.json`.", ""]
    rest = [it for it in items if it not in held]
    if rest:
        lines += ["", "## All MCQs for the day", ""]
        for it in rest:
            lines += block(it)
    for c in concepts:
        if c not in concepts_held:
            lines += ["", f"## Concept note ({when_of(c)})", ""] + _concept_block(cfg, c, repo, branch, date)
    for e in exs:
        k = e.get("kind") or EXPLAINER
        lines += ["", f"## Cartoon explainer ({when_of(e)} reel)", ""] + _explainer_block(cfg, e, repo, branch, date)
        if e.get("hold") and not e.get("error") and k not in posted:
            lines += [f"**To post it anyway:** comment `/approve {k}`. `/regen {k}` writes a new one.", ""]
    if reel and not reel_held:
        lines += ["", "## MCQ reel" + (" (backup)" if ex_ok else ""), ""] + _reel_block(cfg, reel, repo, branch, date)
    if news:
        lines += ["", f"## 📰 News ({cfg.news_time()})", ""]
        if news.get("error"):
            lines += [f"❌ Not made: {news['error']}. Comment `/regen news` to try again.", ""]
        else:
            lines += [" ".join(f'<img src="{_img(repo, branch, date, n)}" width="160">' for n in news.get("images") or []), ""]
            for x in news.get("stories") or []:
                lines.append(f"- **{x['tag']}**: {x['headline']} ([{x['source']}]({x.get('link', '')}))"
                             + (" · ⚠️ editor notes: " + "; ".join(x.get("check_notes") or [])[:200] if x.get("check_notes") else ""))
            if news.get("hold") and "news" not in posted:
                lines += ["", f"**⛔ On hold: {news.get('hold_reason', '')}.** Comment `/approve news` to post it as it is, "
                          "or `/regen news` to make it again (add an instruction if you like)."]
            lines.append("")
    lines += ["---", "### Commands (comment on this issue)",
              "- `/hold <course>`: stop an MCQ from posting, e.g. you spotted a mistake",
              "- `/approve <course>`: post a held MCQ as it is",
              "- `/regen <course> [instruction]`: replace it with a new MCQ; it posts automatically if the check passes",
              f"- Edit `queue/{date.isoformat()}/mcqs.json` to change text; the images redraw by themselves",
              f"- Course ids: {', '.join(cfg.course_ids())}" + (", `concept` for the evening concept note" if concept else "")
              + (", `concept2` for the second note" if len(concepts) > 1 else "")
              + (", `reel` for the reel (`/regen reel` remakes it)" if reel else "")
              + (", `explainer` for the evening video" if ex else "")
              + (", `explainer2` for the second video" if any(e.get("kind") == "explainer2" for e in exs) else "")
              + (", `news` for the news carousel" if cfg.news_due(date) else ""),
              "", "_Posted MCQs can't be changed from here; edit or delete them in the Instagram app._"]
    return "\n".join(lines)


def report_title(cfg: Config, date: dt.date) -> str:
    """'⛔ Action needed: …' while something is on hold, so the issue list shows what needs you."""
    from .batch import load_posted

    batch = load_batch(date) or {"items": []}
    posted = load_posted(date)
    todays = set(cfg.mcq_course_ids(date))
    held = [it for it in batch["items"] if (it.get("hold") or it.get("error")) and it["course_id"] not in posted
            and it["course_id"] in todays]
    for slot in SLOTS:
        concept = load_concept(date, slot)
        if concept and (concept.get("hold") or concept.get("error")) and (concept.get("kind") or CONCEPT) not in posted:
            held.append(concept)
    reel = _reel(cfg, date, load_batch(date))
    ex = _explainer(cfg, date)
    ex_ok = bool(ex and (EXPLAINER in posted or (not ex.get("error") and not ex.get("hold"))))
    if reel and not ex_ok and (reel.get("hold") or reel.get("error")) and REEL not in posted:
        held.append(reel)
    from . import news as N
    news = N.load(date) if cfg.news_due(date) else None
    if news and (news.get("hold") or news.get("error")) and "news" not in posted:
        held.append(news)
    base = f"MCQs for {date.isoformat()} (Day {cfg.day_number(date)})"
    return f"⛔ Action needed: {base}" if held else base
