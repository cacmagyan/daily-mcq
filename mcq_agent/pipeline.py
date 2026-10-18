"""The four jobs: prepare a day's batch, re-render it, regenerate one MCQ, publish what's due."""

from __future__ import annotations

import copy
import datetime as dt
import json
import traceback

from . import batch as B
from .caption import alt_texts, build_caption, post_ref
from .config import ROOT, Config, batch_dir
from .render import Renderer, contact_sheet


def _new_item(cfg: Config, course: dict, date: dt.date) -> dict:
    paper = cfg.paper_for(course, date)
    return {"course_id": course["id"], "paper_code": paper["code"], "paper_name": paper["name"]}


def _fill_item(cfg: Config, course: dict, date: dt.date, instruction: str = "") -> dict:
    from .generator import write_mcq

    paper = cfg.paper_for(course, date)
    item = _new_item(cfg, course, date)
    mcq = write_mcq(cfg, course, paper, date, B.recent_items(course["id"], date), instruction)
    item.update(mcq)
    return item


def _finish(cfg: Config, renderer: Renderer, item: dict, date: dt.date) -> None:
    out = batch_dir(date)
    res = renderer.render_item(item, date, out)
    item["images"] = res["images"]
    item["fit_notes"] = res["fit_notes"]
    item["caption"] = build_caption(cfg, item, date)


def prepare(cfg: Config, date: dt.date, course_ids: list[str] | None = None, sample: bool = False) -> dict:
    """Writes queue/DATE/mcqs.json and both images for each course."""
    ids = course_ids or cfg.course_ids()
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
    _preview(date, batch)
    return batch


def rerender(cfg: Config, date: dt.date, course_ids: list[str] | None = None) -> dict:
    """Use after hand-editing mcqs.json: redraws the images and refreshes captions."""
    batch = B.load_batch(date)
    if not batch:
        raise SystemExit(f"No batch for {date}")
    with Renderer(cfg) as r:
        for item in batch["items"]:
            if item.get("error") or (course_ids and item["course_id"] not in course_ids):
                continue
            _finish(cfg, r, item, date)
            print(f"  ✓ re-rendered {item['course_id']}")
    B.save_batch(date, batch)
    _preview(date, batch)
    return batch


def regenerate(cfg: Config, date: dt.date, course_id: str, instruction: str = "") -> dict:
    batch = B.load_batch(date)
    if not batch:
        raise SystemExit(f"No batch for {date}")
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
    return item


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

def _slot(cfg: Config, item: dict) -> dt.time:
    return dt.time.fromisoformat(cfg.course(item["course_id"])["post_time"])


def publish_due(cfg: Config, date: dt.date | None = None, at: dt.time | None = None,
                dry_run: bool = False, strict: bool = False, limit: int | None = None) -> int:
    """Posts every approved MCQ whose time has come and that isn't posted yet. Returns an exit code."""
    from .hosting import urls_for
    from .instagram import Instagram

    now = cfg.now()
    date = date or now.date()
    at = at or now.time()
    limit = limit or int(cfg.instagram.get("max_posts_per_run", 2))

    batch = B.load_batch(date)
    approved = batch and (cfg.review_mode == "github_pr" or batch.get("approved"))
    if not approved:
        why = "no batch on the main branch (the review PR isn't merged)" if cfg.review_mode == "github_pr" \
            else "the batch isn't approved yet (run the approve command)"
        print(f"Nothing posted for {date}: {why}.")
        return 1 if strict else 0

    posted = B.load_posted(date)
    due = [it for it in batch["items"]
           if it["course_id"] not in posted and not it.get("error") and it.get("images") and _slot(cfg, it) <= at]
    due.sort(key=lambda it: _slot(cfg, it))
    skipped = [it["course_id"] for it in batch["items"] if it.get("error")]
    if skipped:
        print(f"Skipping courses with no MCQ: {', '.join(skipped)}")
    if not due:
        print(f"Nothing due at {at.strftime('%H:%M')} on {date}.")
        return 0

    last_slot = max(dt.time.fromisoformat(c["post_time"]) for c in cfg.courses)
    if at >= last_slot:
        limit = len(due)          # final run of the day: post everything still waiting
    ig = None if dry_run else Instagram.from_env(cfg.instagram)
    failures = 0
    for item in due[:limit]:
        cid = item["course_id"]
        paths = [batch_dir(date) / item["images"]["question"], batch_dir(date) / item["images"]["answer"]]
        alts = alt_texts(item)
        caption = item.get("caption") or build_caption(cfg, item, date)
        ref = post_ref(cid, date)
        if dry_run:
            print(f"[dry run] would post {cid}: {[p.name for p in paths]}\n---\n{caption}\n---")
            continue
        try:
            already = ig.find_by_ref(ref)
            if already:
                result = {"media_id": already["id"], "permalink": already.get("permalink", ""), "note": "found existing post"}
            else:
                urls, host = urls_for(paths, cfg.instagram)
                result = ig.post_carousel(urls, caption, [alts["question"], alts["answer"]])
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
