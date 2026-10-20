"""The four jobs: prepare a day's batch, re-render it, regenerate one MCQ, publish what's due."""

from __future__ import annotations

import copy
import datetime as dt
import json
import traceback
from pathlib import Path

from . import batch as B
from .caption import alt_texts, build_caption, build_concept_caption, build_reel_caption, concept_alt_texts, post_ref
from .config import ROOT, Config, batch_dir
from .render import Renderer, contact_sheet

CONCEPT = "concept"     # id of the concept note in commands, posted.json and the report
REEL = "reel"           # id of the MCQ reel of the day
EXTRAS = (CONCEPT, REEL)


def _new_item(cfg: Config, course: dict, date: dt.date) -> dict:
    paper = cfg.paper_for(course, date)
    return {"course_id": course["id"], "paper_code": paper["code"], "paper_name": cfg.paper_title(paper)}


def _sign(cfg: Config, item: dict) -> None:
    """Puts the paper's author on the MCQ (authors.show_on_mcqs); redraws pick up config changes too."""
    if cfg.authors.get("show_on_mcqs"):
        paper = cfg.find_paper(item["course_id"], item.get("paper_code", ""), item.get("paper_name", ""))
        item["author"] = cfg.author_for(paper or {})
    else:
        item.pop("author", None)


def concept_link(course_id: str, date: dt.date) -> dict | None:
    """Yesterday's concept note, if it was for this course: today's MCQ then tests it."""
    c = B.load_concept(date - dt.timedelta(days=1))
    if c and c.get("course_id") == course_id and c.get("topic") and not c.get("error"):
        return c
    return None


def _fill_item(cfg: Config, course: dict, date: dt.date, instruction: str = "") -> dict:
    from .generator import write_mcq

    paper = cfg.paper_for(course, date)
    item = _new_item(cfg, course, date)
    link = None if instruction else concept_link(course["id"], date)
    mcq = write_mcq(cfg, course, paper, date, B.recent_items(course["id"], date), instruction, link)
    item.update(mcq)
    if link:
        item["linked_concept"] = link["topic"]
    return item


def _finish(cfg: Config, renderer: Renderer, item: dict, date: dt.date) -> None:
    out = batch_dir(date)
    _sign(cfg, item)
    res = renderer.render_item(item, date, out)
    item["images"] = res["images"]
    item["fit_notes"] = res["fit_notes"]
    item["caption"] = build_caption(cfg, item, date)
    set_hold(item)


def tomorrows_mcq(course_id: str, date: dt.date) -> dict | None:
    """Tomorrow's MCQ for the course, if it is already written (a day prepared ahead)."""
    nxt = B.load_batch(date + dt.timedelta(days=1))
    m = B.find_item(nxt, course_id) if nxt else None
    return m if m and m.get("topic") and not m.get("error") else None


def _concept_paper(cfg: Config, item: dict) -> dict:
    return (cfg.find_paper(item["course_id"], item["paper_code"], item["paper_name"])
            or {"code": item["paper_code"], "name": item["paper_name"]})


def _concept_base(cfg: Config, date: dt.date) -> dict:
    course = cfg.concept_course(date)
    paper = cfg.concept_paper(date)
    m = tomorrows_mcq(course["id"], date)
    if m:   # tomorrow's MCQ is already written: the note teaches its topic, from its paper
        paper = cfg.find_paper(course["id"], m.get("paper_code", ""), m.get("paper_name", "")) or paper
    base = {"kind": CONCEPT, "course_id": course["id"], "paper_code": paper["code"],
            "paper_name": cfg.paper_title(paper), "author": cfg.author_for(paper)}
    if m:
        base["linked_mcq"] = m["topic"]
    return base


def _make_concept(cfg: Config, renderer: Renderer, date: dt.date, instruction: str = "", topic: str = "",
                  sample: bool = False) -> dict:
    from .concept import write_concept

    item = _concept_base(cfg, date)
    if sample:
        with open(ROOT / "samples" / "sample_concept.json", encoding="utf-8") as fh:
            samples = json.load(fh)["items"]
        pick = next((x for x in samples if x["course_id"] == item["course_id"]), samples[0])
        item.update(copy.deepcopy(pick))           # the sample's own course and paper, so they match its text
        papers = cfg.course(item["course_id"])["papers"]
        paper = next((x for x in papers if x["code"] == item.get("paper_code")), {"code": "", "name": ""})
        item["author"] = cfg.author_for(paper)
    else:
        course, paper = cfg.course(item["course_id"]), _concept_paper(cfg, item)
        if not topic and not instruction:
            topic = item.get("linked_mcq", "")
        note = write_concept(cfg, course, paper, date, B.recent_concepts(course["id"], date), instruction, topic,
                             fit_check=lambda draft: renderer.measure_concept({**item, **draft}, date))
        item.update(note)
    _finish_concept(cfg, renderer, item, date)
    return item


def _finish_concept(cfg: Config, renderer: Renderer, item: dict, date: dt.date) -> None:
    res = renderer.render_concept(item, date, batch_dir(date))
    item["images"] = res["images"]
    item["fit_notes"] = res["fit_notes"]
    item["fit"] = res["fit"]
    item["caption"] = build_concept_caption(cfg, item, date)
    set_hold(item)


def _concept_error(cfg: Config, date: dt.date, exc: Exception) -> dict:
    item = _concept_base(cfg, date)
    item["error"] = str(exc)[:500]
    return item


def auto_hold_reason(item: dict) -> str:
    """A serious problem that should stop an MCQ from posting until you look at it."""
    if item.get("serious"):
        return item.get("serious_reason") or "The checker could not confirm the answer key"
    if any("cut off" in n for n in item.get("fit_notes", [])):
        return "The text is too long and gets cut off on the image"
    return ""


def set_hold(item: dict) -> None:
    if item.get("held_by_you"):
        item["hold"], item["hold_reason"] = True, "You put this on hold"
    else:
        reason = auto_hold_reason(item)
        item["hold"], item["hold_reason"] = bool(reason), reason


def prepare(cfg: Config, date: dt.date, course_ids: list[str] | None = None, sample: bool = False) -> dict:
    """Writes queue/DATE/mcqs.json with both images per course, then the day's concept note
    (queue/DATE/concept.json, 4 images) and the MCQ reel (queue/DATE/reel.json + reel.mp4).
    `course_ids` may include "concept" and "reel"; with only those, the MCQs are left as they are."""
    # sample runs always include a concept note and a reel (if switched on), so you can see them before the start date
    concept_due = cfg.concept_due(date) or (sample and bool(cfg.concepts.get("enabled")))
    reel_due = cfg.reel_due(date) or (sample and bool(cfg.reels.get("enabled")))
    want_concept = concept_due and (not course_ids or CONCEPT in course_ids)
    want_reel = reel_due and (not course_ids or REEL in course_ids)
    ids = [c for c in (course_ids or cfg.course_ids()) if c not in EXTRAS]
    if course_ids and not ids:          # only the concept note and/or the reel
        if not (want_concept or want_reel):
            raise SystemExit(f"Nothing to add on {date}: check enabled and start_date under concepts and reels "
                             "in config.yaml.")
        with Renderer(cfg) as r:
            if want_concept:
                _prepare_concept(cfg, r, date, sample)
            if want_reel:
                _prepare_reel(cfg, r, date)
        return B.load_batch(date) or {"date": date.isoformat(), "items": []}
    existing = B.load_batch(date) or {"date": date.isoformat(), "items": []}
    batch = {"date": date.isoformat(), "day": cfg.day_number(date), "status": "pending_review",
             "approved": False, "created_at": cfg.now().isoformat(timespec="seconds"),
             "items": [it for it in existing["items"] if it["course_id"] not in ids]}
    samples = {}
    if sample:
        with open(ROOT / "samples" / "sample_batch.json", encoding="utf-8") as fh:
            samples = {it["course_id"]: it for it in json.load(fh)["items"]}

    with Renderer(cfg) as r:
        for cid in ids:
            course = cfg.course(cid)
            try:
                if sample:
                    if cid not in samples:
                        raise RuntimeError(f"no sample MCQ for {cid}")
                    item = copy.deepcopy(samples[cid])
                else:
                    item = _fill_item(cfg, course, date)
                _finish(cfg, r, item, date)
                print(f"  ✓ {course['name']}: {item['topic']} (answer {item['correct']})")
            except Exception as exc:  # keep going; the reviewer can /regen this one
                traceback.print_exc()
                item = _new_item(cfg, course, date)
                item["error"] = str(exc)[:500]
                print(f"  ✗ {course['name']}: {exc}")
            batch["items"].append(item)
        order = {cid: i for i, cid in enumerate(cfg.course_ids())}
        batch["items"].sort(key=lambda it: order.get(it["course_id"], 99))
        B.save_batch(date, batch)
        if want_concept:
            _prepare_concept(cfg, r, date, sample)
        if want_reel:
            _prepare_reel(cfg, r, date)

    _preview(date, batch)
    return batch


def _prepare_concept(cfg: Config, r: Renderer, date: dt.date, sample: bool) -> dict:
    try:
        item = _make_concept(cfg, r, date, sample=sample)
        print(f"  ✓ Concept note ({cfg.course(item['course_id'])['name']}): {item['topic']}")
    except Exception as exc:  # keep going; the reviewer can /regen concept
        traceback.print_exc()
        item = _concept_error(cfg, date, exc)
        print(f"  ✗ Concept note: {exc}")
    B.save_concept(date, item)
    return item


def _prepare_reel(cfg: Config, r: Renderer, date: dt.date) -> dict | None:
    """Makes (or remakes) the day's reel from its MCQs. Never touches a reel that is already posted."""
    from .reel import make_reel

    if REEL in B.load_posted(date):
        print("  • The reel is already posted; leaving it as it is")
        return B.load_reel(date)
    old = B.load_reel(date) or {}
    try:
        batch = B.load_batch(date)
        if not batch:
            raise RuntimeError(f"no MCQs for {date}")
        item = make_reel(cfg, r, batch, date)
        print(f"  ✓ Reel ({cfg.course(item['course_id'])['name']}): {item['topic']}")
    except Exception as exc:  # the MCQs still post; the report shows the reel failed
        traceback.print_exc()
        ids = cfg.reel_courses()
        item = {"kind": REEL, "course_id": old.get("course_id") or ids[cfg.reel_course_index(date)], "error": str(exc)[:500]}
        print(f"  ✗ Reel: {exc}")
    if old.get("held_by_you"):
        item["held_by_you"] = True
    set_hold(item)
    B.save_reel(date, item)
    return item


def rerender(cfg: Config, date: dt.date, course_ids: list[str] | None = None) -> dict:
    """Use after hand-editing mcqs.json: redraws the images and refreshes captions."""
    batch = B.load_batch(date)
    concept = B.load_concept(date)
    if not batch and not concept:
        raise SystemExit(f"No batch for {date}")
    with Renderer(cfg) as r:
        for item in (batch or {"items": []})["items"]:
            if item.get("error") or (course_ids and item["course_id"] not in course_ids):
                continue
            _finish(cfg, r, item, date)
            print(f"  ✓ re-rendered {item['course_id']}")
        if concept and not concept.get("error") and (not course_ids or CONCEPT in course_ids):
            _finish_concept(cfg, r, concept, date)
            B.save_concept(date, concept)
            print("  ✓ re-rendered the concept note")
        if batch:
            B.save_batch(date, batch)
            reel = B.load_reel(date)
            wanted = reel is not None or cfg.reel_due(date)
            if wanted and cfg.reels.get("enabled") and (
                    not course_ids or REEL in course_ids or (reel or {}).get("course_id") in course_ids):
                _prepare_reel(cfg, r, date)        # the reel shows an MCQ, so it is remade from the edited text
    if batch:
        _preview(date, batch)
    return batch or {"date": date.isoformat(), "items": []}


def _not_posted(date: dt.date, course_id: str) -> None:
    if course_id in B.load_posted(date):
        raise SystemExit(f"{course_id} is already posted on Instagram for {date}; it can't be changed here. "
                         "Edit or delete the post in the Instagram app.")


def regenerate_concept(cfg: Config, date: dt.date, instruction: str = "") -> dict:
    """/regen concept: a new note on the same concept (so tomorrow's MCQ still matches),
    unless your instruction asks for something else."""
    _not_posted(date, CONCEPT)
    old = B.load_concept(date) or {}
    topic = "" if instruction else old.get("topic", "")
    with Renderer(cfg) as r:
        item = _make_concept(cfg, r, date, instruction, topic)
    B.save_concept(date, item)
    print(f"  ✓ new concept note: {item['topic']}")
    return item


def regenerate_reel(cfg: Config, date: dt.date) -> dict:
    """/regen reel: remakes the reel from the day's MCQs (no new text is written)."""
    _not_posted(date, REEL)
    with Renderer(cfg) as r:
        item = _prepare_reel(cfg, r, date)
    return item or {}


def regenerate(cfg: Config, date: dt.date, course_id: str, instruction: str = "") -> dict:
    if course_id == CONCEPT:
        return regenerate_concept(cfg, date, instruction)
    if course_id == REEL:
        return regenerate_reel(cfg, date)
    batch = B.load_batch(date)
    if not batch:
        raise SystemExit(f"No batch for {date}")
    _not_posted(date, course_id)
    course = cfg.course(course_id)
    item = _fill_item(cfg, course, date, instruction)
    with Renderer(cfg) as r:
        _finish(cfg, r, item, date)
    batch["items"] = [item if it["course_id"] == course_id else it for it in batch["items"]]
    if not B.find_item(batch, course_id):
        batch["items"].append(item)
    B.save_batch(date, batch)
    _preview(date, batch)
    print(f"  ✓ new MCQ for {course['name']}: {item['topic']} (answer {item['correct']})")
    reel = B.load_reel(date)
    if reel and reel.get("course_id") == course_id and REEL not in B.load_posted(date):
        with Renderer(cfg) as r:              # the reel showed the old MCQ: remake it
            _prepare_reel(cfg, r, date)
    return item


def _target(date: dt.date, course_id: str):
    """(item, save) for an MCQ or the concept note."""
    if course_id == CONCEPT:
        item = B.load_concept(date)
        if not item:
            raise SystemExit(f"No concept note for {date}")
        return item, lambda: B.save_concept(date, item)
    if course_id == REEL:
        item = B.load_reel(date)
        if not item:
            raise SystemExit(f"No reel for {date}")
        return item, lambda: B.save_reel(date, item)
    batch = B.load_batch(date)
    item = B.find_item(batch or {"items": []}, course_id)
    if not item:
        raise SystemExit(f"No {course_id} MCQ for {date}")
    return item, lambda: B.save_batch(date, batch)


def release(date: dt.date, course_id: str) -> str:
    """/approve: post a held MCQ (or the concept note) as it is."""
    item, save = _target(date, course_id)
    what = {CONCEPT: "concept note", REEL: "reel"}.get(course_id, "MCQ")
    if item.get("error"):
        raise SystemExit(f"{course_id} has no {what} to approve (it failed to generate); use /regen {course_id}")
    item["serious"], item["held_by_you"] = False, False
    item["fit_notes"] = [n for n in item.get("fit_notes", []) if "cut off" not in n]
    set_hold(item)
    save()
    return f"{course_id} approved for {date}; it posts at its time (or at the next run if that has passed)"


def hold(date: dt.date, course_id: str) -> str:
    """/hold: stop an MCQ (or the concept note) from posting."""
    item, save = _target(date, course_id)
    _not_posted(date, course_id)
    item["held_by_you"] = True
    set_hold(item)
    save()
    return f"{course_id} on hold for {date}; it won't post until you comment /approve {course_id} or /regen {course_id}"


def approve(date: dt.date) -> None:
    batch = B.load_batch(date)
    if not batch:
        raise SystemExit(f"No batch for {date}")
    batch["approved"] = True
    batch["status"] = "approved"
    B.save_batch(date, batch)
    print(f"Approved {date}.")


def _preview(date: dt.date, batch: dict) -> None:
    ready = [it for it in batch["items"] if it.get("images")]
    if ready:
        contact_sheet(batch_dir(date), ready, batch_dir(date) / "preview.jpg")


# ── publishing ──────────────────────────────────────────────────────────────

def _key(item: dict) -> str:
    return item["kind"] if item.get("kind") in EXTRAS else item["course_id"]


def _slot(cfg: Config, item: dict) -> dt.time:
    if item.get("kind") == CONCEPT:
        return dt.time.fromisoformat(cfg.concept_time())
    if item.get("kind") == REEL:
        return dt.time.fromisoformat(cfg.reel_time())
    return dt.time.fromisoformat(cfg.course(item["course_id"])["post_time"])


def _post_parts(cfg: Config, item: dict, date: dt.date) -> tuple[list, list, str]:
    """Image paths, alt texts and caption for one post."""
    if item.get("kind") == CONCEPT:
        return ([batch_dir(date) / n for n in item["images"]], concept_alt_texts(item),
                item.get("caption") or build_concept_caption(cfg, item, date))
    alts = alt_texts(item)
    return ([batch_dir(date) / item["images"]["question"], batch_dir(date) / item["images"]["answer"]],
            [alts["question"], alts["answer"]], item.get("caption") or build_caption(cfg, item, date))


def publish_due(cfg: Config, date: dt.date | None = None, at: dt.time | None = None,
                dry_run: bool = False, strict: bool = False, limit: int | None = None) -> int:
    """Posts every approved MCQ whose time has come and that isn't posted yet. Returns an exit code."""
    from .hosting import urls_for, video_urls
    from .instagram import Instagram

    now = cfg.now()
    date = date or now.date()
    at = at or now.time()
    limit = limit or int(cfg.instagram.get("max_posts_per_run", 2))

    batch = B.load_batch(date)
    concept = B.load_concept(date)
    approved = batch and (cfg.review_mode in ("github_pr", "auto") or batch.get("approved"))
    if not approved:
        why = {"github_pr": "no batch on the main branch (the review PR isn't merged)",
               "auto": "no batch was prepared for this day"}.get(
            cfg.review_mode, "the batch isn't approved yet (run the approve command)")
        print(f"Nothing posted for {date}: {why}.")
        return 1 if strict else 0

    from .reel import problem as reel_problem

    posted = B.load_posted(date)
    reel = B.load_reel(date) if cfg.reels.get("enabled") else None
    if reel and not reel.get("error") and not reel.get("hold") and REEL not in posted:
        why = reel_problem(reel, batch)
        if why:                                  # follows its MCQ: held or changed means no post
            reel = {**reel, "hold": True, "hold_reason": why}
    items = list(batch["items"]) + ([concept] if concept else []) + ([reel] if reel else [])
    due = [it for it in items
           if _key(it) not in posted and not it.get("error") and not it.get("hold")
           and (it.get("images") or it.get("video")) and _slot(cfg, it) <= at]
    due.sort(key=lambda it: _slot(cfg, it))
    skipped = [_key(it) for it in items if it.get("error")]
    if skipped:
        print(f"Skipping, nothing was written: {', '.join(skipped)}")
    held = [f"{_key(it)} ({it.get('hold_reason', '')})" for it in items
            if it.get("hold") and _key(it) not in posted]
    if held:
        print(f"On hold, not posting: {'; '.join(held)}")
    if not due:
        print(f"Nothing due at {at.strftime('%H:%M')} on {date}.")
        return 0

    last_slot = max(_slot(cfg, it) for it in items)
    if at >= last_slot:
        limit = len(due)          # final run of the day: post everything still waiting
    ig = None if dry_run else Instagram.from_env(cfg.instagram)
    failures = 0
    for item in due[:limit]:
        cid = _key(item)
        is_reel = item.get("kind") == REEL
        if is_reel:
            video = batch_dir(date) / item["video"]
            paths, alts = [video], []
            caption = item.get("caption") or build_reel_caption(cfg, item, B.find_item(batch, item["course_id"]), date)
        else:
            paths, alts, caption = _post_parts(cfg, item, date)
        ref = post_ref(cid, date)
        if dry_run:
            print(f"[dry run] would post {cid}: {[p.name for p in paths]}\n---\n{caption}\n---")
            continue
        try:
            already = ig.find_by_ref(ref)
            if already:
                result = {"media_id": already["id"], "permalink": already.get("permalink", ""), "note": "found existing post"}
            elif is_reel:
                result = ig.post_reel(video_urls(video, cfg.instagram), caption, **reel_options(cfg))
            else:
                urls, host = urls_for(paths, cfg.instagram)
                result = ig.post_carousel(urls, caption, alts)
                result["image_host"] = host
            result["posted_at"] = cfg.now().isoformat(timespec="seconds")
            posted[cid] = result
            B.save_posted(date, posted)        # save after every post so a crash never double-posts
            print(f"  ✓ posted {cid}: {result.get('permalink')}")
        except Exception as exc:
            failures += 1
            traceback.print_exc()
            print(f"  ✗ {cid} failed: {exc}")
    left = len(due) - min(len(due), limit)
    if left:
        print(f"{left} more due; the next run will post them.")
    return 1 if failures else 0


def reel_options(cfg: Config) -> dict:
    """Instagram settings for the reel: a normal reel (feed + Reels tab) or a Trial Reel."""
    trial = cfg.reels.get("trial")
    return {"share_to_feed": not trial, "trial": "SS_PERFORMANCE" if trial else None,
            "audio_name": str(cfg.reels.get("audio_name") or "").strip()}


def reel_demo(cfg: Config, out_dir: Path, date: dt.date | None = None) -> list[dict]:
    """Demo reels from samples/sample_reel.json, one per presenter (with the voice if a voice key is
    set). Saved as <out_dir>/reel-<name>.mp4; nothing is posted."""
    from .reel import build

    date = date or cfg.today()
    with open(ROOT / "samples" / "sample_reel.json", encoding="utf-8") as fh:
        samples = json.load(fh)["items"]
    made = []
    with Renderer(cfg) as r:
        for src in samples:
            src = copy.deepcopy(src)
            _sign(cfg, src)
            name = (cfg.reels.get("presenters") or {}).get(src.get("author"), src["course_id"])
            item = build(cfg, r, src, date, out_dir, video=f"reel-{name}.mp4", cover=f"reel-{name}.jpg")
            if item is None:
                print(f"  ✗ {name}: the sample text doesn't fit a reel")
                continue
            voice = item.get("voice") or item.get("voice_note") or "no voice"
            print(f"  ✓ {out_dir / item['video']} ({sum(item['seconds'].values()):g} s, {voice})")
            made.append(item)
    return made
