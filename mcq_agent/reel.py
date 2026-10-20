"""MCQ Reel of the day: one of the day's MCQs as a short vertical video.

The question shows with a countdown clock, then the answer is filled in like an OMR bubble with
the reason underneath. It reuses an MCQ that has already passed every check, so no new text is
written; the reel only posts while that MCQ is unchanged and not on hold.
Files: queue/DATE/reel.json, reel.mp4 and reel_cover.jpg (the first frame, for the report).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image

from .config import LETTERS, Config, batch_dir

REEL = "reel"
VIDEO, COVER = "reel.mp4", "reel_cover.jpg"
FPS = 10                 # clock frames a second (the video itself is 30 fps)
MIN_SCALE = 0.72         # below this the text is too small on a phone: shorten the reason, or use another MCQ


class ReelError(RuntimeError):
    pass


def source_hash(item: dict) -> str:
    """Fingerprint of what the reel shows, so an edited MCQ never posts with an old video."""
    keys = ("question", "options", "correct", "explanation", "applicability", "paper_code", "paper_name", "topic", "author")
    blob = json.dumps({k: item.get(k) for k in keys}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def usable(item: dict | None) -> bool:
    return bool(item and item.get("question") and item.get("images") and not item.get("error") and not item.get("hold"))


def candidates(cfg: Config, batch: dict, date: dt.date) -> list[dict]:
    """The day's usable MCQs, starting with the course whose turn it is (reels.courses order)."""
    ids = cfg.reel_courses()
    start = cfg.reel_course_index(date)
    order = ids[start:] + ids[:start]
    by_id = {it["course_id"]: it for it in batch.get("items", [])}
    return [by_id[c] for c in order if usable(by_id.get(c))]


def short_reason(text: str, limit: int = 170) -> str:
    """The first sentence or two of the explanation, at most `limit` characters where possible."""
    text = " ".join((text or "").split())
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z(₹0-9])", text)
    out = sentences[0]
    for s in sentences[1:]:
        if len(out) + 1 + len(s) > limit:
            break
        out += " " + s
    return out


POSES = {"think": ("think", "thinking"), "answer": ("point", "pointing"), "thumbs": ("thumbs", "thumbsup", "thumbs-up")}
OUTRO = 2.5              # seconds at the end: thumbs-up, "send this to a friend", "Follow" (longer with a voice)


def _clean_pose(src: Path) -> Path:
    """A trimmed, solid copy of a pose picture, at most 900 px tall (made once per picture)."""
    data = src.read_bytes()
    dest = Path(tempfile.gettempdir()) / "mcq-presenters" / (hashlib.sha1(data).hexdigest()[:16] + ".png")
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGBA")
        alpha = im.getchannel("A").point(lambda a: 0 if a < 8 else 255 if a > 245 else a)   # no see-through body
        im.putalpha(alpha)
        box = alpha.getbbox()
        if box:
            im = im.crop(box)
        if im.height > 900:
            im = im.resize((round(im.width * 900 / im.height), 900), Image.LANCZOS)
        im.save(dest, "PNG", optimize=True)
    return dest


def presenter(cfg: Config, author: str) -> dict | None:
    """The author's pose pictures (assets/brand/<name>-think.png, -point.png and -thumbs.png) as
    file URIs: {"think": ..., "answer": ..., "thumbs": ... or None}. None if there are no pictures, and
    the reel is drawn without a presenter."""
    from .config import ROOT

    name = (cfg.reels.get("presenters") or {}).get(author)
    if not name:
        return None
    base = ROOT / "assets" / "brand"
    found = {}
    for pose, words in POSES.items():
        for word in words:
            path = base / f"{name}-{word}.png"
            if path.exists():
                found[pose] = _clean_pose(path).as_uri()
                break
    if not (found.get("think") or found.get("answer")):
        return None
    return {"think": found.get("think") or found["answer"], "answer": found.get("answer") or found["think"],
            "thumbs": found.get("thumbs")}


def _cover(frame: Path, dest: Path) -> None:
    with Image.open(frame) as im:
        im.convert("RGB").save(dest, "JPEG", quality=88, optimize=True)


def share_option(src: dict, date: dt.date) -> str:
    """A wrong option for "send this to a friend who'd pick option X" (changes from day to day)."""
    wrong = [l for l in LETTERS[: len(src.get("options", LETTERS))] if l != src.get("correct")]
    return wrong[date.toordinal() % len(wrong)] if wrong else ""


def voice_lines(cfg: Config, src: dict, why: str, think: int, share: str) -> dict:
    """What the presenter says: a hook while the clock runs, the answer and reason, the share line."""
    course = cfg.course(src["course_id"])["name"]
    right = src["options"][LETTERS.index(src["correct"])]
    lines = {"hook": f"{course} question. Can you answer it in {think} seconds?",
             "answer": f"The answer is option {src['correct']}. {right}. {why}"}
    if share:
        lines["outro"] = f"Send this to a friend who'd pick option {share}!"
    return lines


def _voice(cfg: Config, src: dict, why: str, think: int, share: str, work: Path) -> tuple[dict, str, str]:
    """({part: (wav, seconds)}, voice used, note). No voice key or a voice failure gives no clips."""
    from . import tts

    if not tts.provider(cfg):
        return {}, "", "" if not (cfg.reels.get("voice") or {}).get("enabled") else "no voice key yet (see README)"
    author = src.get("author") or cfg.brand.get("name", "")
    clips, used = {}, ""
    try:
        for part, text in voice_lines(cfg, src, why, think, share).items():
            wav, used = tts.synthesize(cfg, text, author, work / f"voice_{part}.wav")
            clips[part] = (wav, tts.seconds(wav))
    except Exception as exc:  # noqa: BLE001 - a reel without a voice is better than no reel
        return {}, "", f"voice failed, so this reel has none: {str(exc)[:160]}"
    return clips, used, ""


def build(cfg: Config, renderer, src: dict, date: dt.date, out_dir: Path, video: str = VIDEO,
          cover: str = COVER) -> dict | None:
    """Draws and encodes one reel for the MCQ `src`. None if its text doesn't fit a reel."""
    from .video import encode, make_sound

    think, answer_total = cfg.reel_seconds()
    share = share_option(src, date)
    reasons = [src.get("explanation", "")]
    short = short_reason(reasons[0])
    if short and short != reasons[0]:
        reasons.append(short)
    # with the presenter if he has pictures and the text still fits beside him, else without
    guy = [True, False] if presenter(cfg, src.get("author") or cfg.brand.get("name", "")) else [False]
    for with_guy, why in [(g, w) for g in guy for w in reasons]:
        fit = renderer.reel_frames(src, date, why, think, answer_total, FPS, None, with_guy, OUTRO, share)["fit"]
        if not fit["overflow"] and fit["scale"] >= MIN_SCALE:
            break
    else:
        return None
    work = Path(tempfile.mkdtemp(prefix="reel-"))
    try:
        clips, voice, note = _voice(cfg, src, why, think, share, work)
        hold = max(1.5, answer_total - OUTRO)
        outro = OUTRO
        timeline = []
        if "hook" in clips and clips["hook"][1] <= think - 1.0:
            timeline.append((0.35, clips["hook"][0]))
        if "answer" in clips:
            hold = max(hold, 0.7 + clips["answer"][1] + 0.6)
            timeline.append((think + 0.7, clips["answer"][0]))
        if "outro" in clips:
            outro = max(outro, 0.3 + clips["outro"][1] + 0.6)
            timeline.append((think + hold + 0.3, clips["outro"][0]))
        total = think + hold + outro
        res = renderer.reel_frames(src, date, why, think, hold, FPS, work / "frames", with_guy, outro, share)
        sound = make_sound(work / "sound.wav", think, total, timeline)
        out_dir.mkdir(parents=True, exist_ok=True)
        encode(res["frames"], sound, out_dir / video, total)
        _cover(res["frames"][0][0], out_dir / cover)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    item = {
        "kind": REEL, "course_id": src["course_id"], "paper_code": src.get("paper_code", ""),
        "paper_name": src.get("paper_name", ""), "topic": src.get("topic", ""), "author": src.get("author", ""),
        "correct": src.get("correct", ""), "source": source_hash(src), "video": video, "cover": cover,
        "seconds": {"think": think, "answer": round(hold + outro, 2)}, "scale": res["fit"]["scale"],
        "short_reason": why != src.get("explanation", ""), "presenter": with_guy, "share_option": share,
        "voice": voice,
    }
    if note:
        item["voice_note"] = note
    return item


def make_reel(cfg: Config, renderer, batch: dict, date: dt.date, out_dir: Path | None = None) -> dict:
    """Draws and encodes the reel for the day's batch; returns the reel record (not yet saved)."""
    from .caption import build_reel_caption

    out_dir = out_dir or batch_dir(date)
    tried = []
    for src in candidates(cfg, batch, date):
        item = build(cfg, renderer, src, date, out_dir)
        if item is None:
            tried.append(f"{src['course_id']} (text too long for a reel)")
            continue
        if tried:
            item["note"] = "Used " + src["course_id"] + " instead of " + ", ".join(tried)
        item["caption"] = build_reel_caption(cfg, item, src, date)
        return item
    if tried:
        raise ReelError("No MCQ fits a reel today: " + "; ".join(tried))
    raise ReelError("No MCQ is ready for a reel today (all failed or are on hold)")


def problem(item: dict, batch: dict | None) -> str:
    """Why the reel must not post now (empty if it can)."""
    from .batch import find_item

    src = find_item(batch or {"items": []}, item.get("course_id", ""))
    if not src or src.get("error"):
        return f"its MCQ ({item.get('course_id')}) is missing"
    if src.get("hold"):
        return f"its MCQ ({item.get('course_id')}) is on hold"
    if source_hash(src) != item.get("source"):
        return f"its MCQ ({item.get('course_id')}) was changed after the video was made; redraw the day"
    return ""


def alt_text(item: dict, src: dict) -> str:
    opts = "; ".join(f"{l}) {o}" for l, o in zip(LETTERS, src.get("options", [])))
    return f"MCQ reel. {src.get('question', '')} Options: {opts}. Answer: option {item.get('correct', '')}."[:900]
