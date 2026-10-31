"""Comment NOTES → automatic DM. The explainer reel and the concept post ask students to comment
NOTES; this sends each of them the day's full concept note as a PDF link by DM (an Instagram
"private reply"), then answers the comment publicly ("Sent! Check your DMs 📩") so others see it works.

It keeps no list of its own: a comment that already has our public reply is done. Instagram allows
one DM per comment, within 7 days of it. Runs every 30 minutes (workflow 8).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from . import batch as B
from .config import Config, batch_dir

REF = re.compile(r"\bref ([a-z][a-z0-9-]*?)-(\d{6})\b")


def settings(cfg: Config) -> dict:
    return cfg.raw.get("comment_dm") or {}


def cta(cfg: Config) -> str:
    """The line captions and the explainer use to invite comments ('' when switched off)."""
    s = settings(cfg)
    if not s.get("enabled"):
        return ""
    word = (s.get("keywords") or ["NOTES"])[0].upper()
    return f"💬 Comment {word} and we'll DM you the full concept note (PDF)."


def concept_pdf(date: dt.date, slot: str = "") -> Path | None:
    """queue/DATE/concept.pdf (concept2.pdf for the second note) from the note's slides, made once.
    None if there is no note."""
    from PIL import Image

    c = B.load_concept(date, slot)
    if not c or c.get("error") or not c.get("images"):
        return None
    out = batch_dir(date) / f"concept{slot}.pdf"
    if out.exists():
        return out
    pages = [Image.open(batch_dir(date) / n).convert("RGB") for n in c["images"] if (batch_dir(date) / n).exists()]
    if not pages:
        return None
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return out


def make_pdfs(cfg: Config, days: int = 8) -> list[Path]:
    """PDFs for the concept notes of the last `days` days and tomorrow (so DM links work at once)."""
    today = cfg.today()
    made = []
    for k in range(-days, 2):
        d = today + dt.timedelta(days=k)
        for slot in ("", "2"):
            before = (batch_dir(d) / f"concept{slot}.pdf").exists()
            p = concept_pdf(d, slot)
            if p and not before:
                made.append(p)
    return made


def wants_notes(text: str, keywords: list[str]) -> bool:
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return any(k.lower() in words for k in keywords)


def _post_date(caption: str) -> tuple[str, dt.date] | None:
    m = REF.search(caption or "")
    if not m:
        return None
    try:
        return m.group(1), dt.datetime.strptime(m.group(2), "%y%m%d").date()
    except ValueError:
        return None


def dm_text(cfg: Config, concept: dict, url: str, username: str) -> str:
    course = cfg.course(concept["course_id"])["name"]
    handle = cfg.brand.get("handle", "").strip()
    return (f"Hi {username}! 📒 Here's the full concept note: {concept.get('topic', '')} ({course}).\n\n"
            f"{url}\n\nSave it for revision. One new concept every day on {handle} 🐘").strip()


def run(cfg: Config, ig=None, dry_run: bool = False) -> dict:
    """Answers new NOTES comments on recent explainer and concept posts. Returns counts."""
    from .hosting import public_url
    from .instagram import Instagram, InstagramError

    s = settings(cfg)
    counts = {"sent": 0, "skipped": 0, "failed": 0}
    if not s.get("enabled"):
        print("Comment DMs are switched off (comment_dm: enabled in config.yaml).")
        return counts
    keywords = [k for k in s.get("keywords") or ["notes", "note", "pdf"]]
    kinds = set(s.get("posts") or ["explainer", "concept", "explainer2", "concept2"])
    window = dt.timedelta(days=min(7, int(s.get("days", 7))))
    ig = ig or Instagram.from_env(cfg.instagram)
    me = (ig.account().get("username") or "").lower()
    now = dt.datetime.now(dt.timezone.utc)
    media = ig.media_list(int(s.get("look_back_posts", 30)))
    print(f"Checking {len(media)} recent posts for {', '.join(keywords)} comments")
    for m in media:
        ref = _post_date(m.get("caption") or "")
        if not ref or ref[0] not in kinds:
            continue
        print(f"  • {ref[0]} {ref[1]}: {m.get('comments_count', 0)} comments")
        if not m.get("comments_count"):
            continue
        try:
            posted = dt.datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        except (KeyError, ValueError):
            continue
        if now - posted > window + dt.timedelta(days=1):
            continue
        slot = "2" if ref[0].endswith("2") else ""
        concept = B.load_concept(ref[1], slot)
        pdf = concept_pdf(ref[1], slot) if concept else None
        if not pdf:
            print("    no concept note PDF for that day")
            continue
        url = public_url(s.get("host", "jsdelivr"), pdf, cfg.instagram)
        done_users = set()
        comments = ig.comments(m["id"])
        asking = sum(1 for c in comments if wants_notes(c.get("text", ""), keywords))
        print(f"    {len(comments)} comments readable, {asking} ask for the note")
        for c in comments:                          # who already got our answer on this post
            if any((r.get("username") or "").lower() == me for r in (c.get("replies") or {}).get("data", [])):
                done_users.add((c.get("username") or "").lower())
        for c in comments:
            user = (c.get("username") or "").lower()
            if not wants_notes(c.get("text", ""), keywords):
                continue
            if not user or user == me or user in done_users:
                why = "no username (Instagram hid it)" if not user else "our own account" if user == me else "already answered"
                print(f"    skipped one: {why}")
                continue
            try:
                when = dt.datetime.strptime(c["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            except (KeyError, ValueError):
                when = now
            if now - when > window:
                counts["skipped"] += 1
                continue
            if dry_run:
                print(f"[dry run] would DM @{user} the {ref[1]} note: {url}")
                done_users.add(user)
                continue
            try:
                ig.private_reply(c["id"], dm_text(cfg, concept, url, c.get("username") or ""))
                print(f"  ✓ DM sent to @{user} ({ref[1]} note)")
                counts["sent"] += 1
            except InstagramError as exc:
                msg = str(exc).lower()
                if not any(w in msg for w in ("already", "only one", "one message")):
                    counts["failed"] += 1
                    print(f"  ✗ DM to @{user} failed: {str(exc)[:200]}")
                    if exc.code in (10, 190, 200) or "permission" in msg:
                        print("  ! Stopping: the token needs the instagram_business_manage_comments and "
                              "instagram_business_manage_messages permissions (README, 'Comment NOTES').")
                        return counts
                    continue
            done_users.add(user)
            try:
                ig.reply_to_comment(c["id"], s.get("public_reply") or "Sent! Check your DMs 📩")
            except InstagramError as exc:
                print(f"  ! public reply to @{user} not posted: {str(exc)[:160]}")
    print(f"Comment DMs: {counts['sent']} sent, {counts['failed']} failed, {counts['skipped']} too old.")
    return counts
