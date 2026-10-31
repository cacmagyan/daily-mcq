"""Weekly performance report: how each kind of post did last week (views, reach, saves, shares,
watch time, follows), the best and worst posts, follower growth, and a short note from Claude on
what worked and what to try next. Posted every Sunday evening as a GitHub issue (workflow 7).
The numbers are kept in stats/ so later weeks can be compared.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import batch as B
from .config import ROOT, Config

STATS = ROOT / "stats"
REEL_METRICS = ["views", "reach", "saved", "shares", "likes", "comments", "total_interactions",
                "ig_reels_avg_watch_time"]
FEED_METRICS = ["views", "reach", "saved", "shares", "likes", "comments", "total_interactions", "follows",
                "profile_visits"]
KIND_NAMES = {"explainer": "🎬 Cartoon explainer", "reel": "🎬 MCQ reel", "concept": "📒 Concept note", "mcq": "📝 MCQ post",
              "news": "📰 News"}


def week_range(today: dt.date) -> tuple[dt.date, dt.date]:
    """The 7 days ending yesterday."""
    end = today - dt.timedelta(days=1)
    return end - dt.timedelta(days=6), end


def posts_between(start: dt.date, end: dt.date) -> list[dict]:
    """Every post the agent made in the range, from queue/<date>/posted.json."""
    out = []
    d = start
    while d <= end:
        posted = B.load_posted(d)
        batch = B.load_batch(d) or {"items": []}
        for key, rec in posted.items():
            if ":" in key or not rec.get("media_id"):
                continue                                     # Stories have no lasting numbers
            concept = B.load_concept(d, "2" if key.endswith("2") else "") or {}
            if key == "news":
                from .news import load as load_news
                kind, course = "news", ""
                topic = " · ".join(s.get("tag", "") for s in (load_news(d) or {}).get("stories") or [])
            elif key in ("explainer", "reel", "concept", "explainer2", "concept2"):
                kind = key.rstrip("2")
                topic = concept.get("topic", "") if kind in ("explainer", "concept") else ""
                if key == "reel":
                    topic = (B.load_reel(d) or {}).get("topic", "")
                course = concept.get("course_id", "") if key != "reel" else (B.load_reel(d) or {}).get("course_id", "")
            else:
                kind, course = "mcq", key
                topic = (B.find_item(batch, key) or {}).get("topic", "")
            out.append({"date": d.isoformat(), "key": key, "kind": kind, "course_id": course, "topic": topic,
                        "media_id": rec["media_id"], "permalink": rec.get("permalink", "")})
        d += dt.timedelta(days=1)
    return out


def collect(cfg: Config, ig, start: dt.date, end: dt.date) -> dict:
    posts = posts_between(start, end)
    for p in posts:
        metrics = REEL_METRICS if p["kind"] in ("explainer", "reel") else FEED_METRICS
        try:
            p["m"] = ig.media_insights(p["media_id"], metrics)
        except Exception as exc:  # noqa: BLE001 - one post's numbers missing shouldn't stop the report
            p["m"], p["error"] = {}, str(exc)[:200]
    followers = None
    try:
        followers = ig.followers()
    except Exception as exc:  # noqa: BLE001
        print(f"  ! follower count not available: {str(exc)[:160]}")
    return {"start": start.isoformat(), "end": end.isoformat(), "followers": followers, "posts": posts}


def _avg(rows, key):
    vals = [r["m"][key] for r in rows if key in r.get("m", {})]
    return sum(vals) / len(vals) if vals else None


def _fmt(v, unit=""):
    if v is None:
        return "–"
    if unit == "s":
        return f"{v / 1000:.1f} s"
    return f"{v:,.0f}" if v >= 10 else f"{v:.1f}"


def previous_followers(before: dt.date) -> tuple[int | None, str]:
    best = None
    for f in sorted(STATS.glob("week-*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("end", "") < before.isoformat() and data.get("followers") is not None:
            best = (data["followers"], data["end"])
    return best if best else (None, "")


def summary_with_claude(cfg: Config, data: dict, table: str) -> str:
    """4-6 short lines from Claude: what worked, what didn't, what to try next week."""
    from .generator import _call_claude

    tool = {"name": "submit_notes", "description": "Submit the notes.",
            "input_schema": {"type": "object", "properties": {
                "notes": {"type": "array", "minItems": 3, "maxItems": 6,
                          "items": {"type": "string", "description": "One short, concrete line"}}},
                "required": ["notes"]}}
    system = ("You are the social media analyst for an Instagram page that teaches Indian CA and CMA students "
              "(daily MCQ carousels per course, a concept-of-the-day carousel, and a 40-second cartoon explainer "
              "reel). From last week's numbers, write 3-6 short, concrete lines: what worked, what didn't, and "
              "one or two things to try next week. Base every line on the numbers given; say when a sample is "
              "too small to conclude. Plain English, no hype, no emoji.")
    rows = "\n".join(f"{p['date']} {p['kind']} {p['course_id']} '{p['topic']}': "
                     + ", ".join(f"{k}={v}" for k, v in p.get("m", {}).items()) for p in data["posts"])
    user = f"Summary table:\n{table}\n\nEvery post:\n{rows}\n\nFollowers now: {data.get('followers')}"
    out = _call_claude(cfg.models.get("writer", "claude-sonnet-5-5"), system, user, tool, max_tokens=1200)
    return "\n".join(f"- {n.strip()}" for n in out.get("notes", []) if n.strip())


def report(cfg: Config, data: dict, with_summary: bool = True) -> str:
    start, end = dt.date.fromisoformat(data["start"]), dt.date.fromisoformat(data["end"])
    posts = data["posts"]
    lines = [f"## Weekly report: {start.strftime('%d %b')} – {end.strftime('%d %b %Y')}", ""]
    prev, prev_end = previous_followers(start)
    if data.get("followers") is not None:
        change = f" ({data['followers'] - prev:+,} since {prev_end})" if prev is not None else ""
        lines += [f"**Followers:** {data['followers']:,}{change}", ""]
    measured = [p for p in posts if p.get("m")]
    if not measured:
        why = posts[0].get("error", "") if posts else "no posts were recorded"
        return "\n".join(lines + [f"No numbers came back from Instagram ({why}).",
                                  "The token needs the **instagram_business_manage_insights** permission "
                                  "(README, 'Weekly report')."])
    kinds = ["| Kind | Posts | Avg views | Avg reach | Avg saves | Avg shares | Avg likes | Watch time |",
             "|---|---|---|---|---|---|---|---|"]
    for kind in ("explainer", "reel", "concept", "mcq", "news"):
        rows = [p for p in measured if p["kind"] == kind]
        if rows:
            kinds.append(f"| {KIND_NAMES[kind]} | {len(rows)} | {_fmt(_avg(rows, 'views'))} | {_fmt(_avg(rows, 'reach'))} | "
                         f"{_fmt(_avg(rows, 'saved'))} | {_fmt(_avg(rows, 'shares'))} | {_fmt(_avg(rows, 'likes'))} | "
                         f"{_fmt(_avg(rows, 'ig_reels_avg_watch_time'), 's') if kind in ('explainer', 'reel') else '–'} |")
    lines += kinds
    table = "\n".join(kinds)
    mcqs = [p for p in measured if p["kind"] == "mcq"]
    if mcqs:
        lines += ["", "**MCQ posts by course**", "", "| Course | Posts | Avg reach | Avg saves | Avg shares |", "|---|---|---|---|---|"]
        for c in cfg.course_ids():
            rows = [p for p in mcqs if p["course_id"] == c]
            if rows:
                lines.append(f"| {cfg.course(c)['name']} | {len(rows)} | {_fmt(_avg(rows, 'reach'))} | "
                             f"{_fmt(_avg(rows, 'saved'))} | {_fmt(_avg(rows, 'shares'))} |")

    def score(p):
        m = p["m"]
        return m.get("views", m.get("reach", 0)) + 10 * m.get("saved", 0) + 15 * m.get("shares", 0)

    ranked = sorted(measured, key=score, reverse=True)
    def row(p):
        m = p["m"]
        name = cfg.course(p["course_id"])["name"] if p.get("course_id") else ""
        return (f"| [{p['date'][5:]} {KIND_NAMES[p['kind']]}]({p['permalink']}) | {name} | {p['topic'][:40]} | "
                f"{_fmt(m.get('views'))} | {_fmt(m.get('saved'))} | {_fmt(m.get('shares'))} |")
    lines += ["", "**Best posts**", "", "| Post | Course | Topic | Views | Saves | Shares |", "|---|---|---|---|---|---|"]
    lines += [row(p) for p in ranked[:5]]
    if len(ranked) > 8:
        lines += ["", "**Weakest posts**", "", "| Post | Course | Topic | Views | Saves | Shares |", "|---|---|---|---|---|---|"]
        lines += [row(p) for p in ranked[-3:]]
    if with_summary:
        try:
            notes = summary_with_claude(cfg, data, table)
            if notes:
                lines += ["", "### What the numbers say", "", notes]
        except Exception as exc:  # noqa: BLE001 - the numbers are still worth posting
            lines += ["", f"_Claude's notes are missing this week ({str(exc)[:120]})._"]
    missing = [p for p in posts if not p.get("m")]
    if missing:
        lines += ["", f"_{len(missing)} posts had no numbers from Instagram._"]
    lines += ["", "_Views and reach keep growing for a few days, so the last days of the week look smaller._"]
    return "\n".join(lines)


def save(data: dict) -> Path:
    STATS.mkdir(exist_ok=True)
    p = STATS / f"week-{data['end']}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def weekly(cfg: Config, today: dt.date | None = None, ig=None, with_summary: bool = True) -> str:
    from .instagram import Instagram

    start, end = week_range(today or cfg.today())
    ig = ig or Instagram.from_env(cfg.instagram)
    data = collect(cfg, ig, start, end)
    text = report(cfg, data, with_summary and bool((cfg.raw.get("weekly_report") or {}).get("summary", True)))
    save(data)
    return text
