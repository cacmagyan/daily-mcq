"""CA · CMA Daily News: a nightly carousel of the day's top stories for CA and CMA students
(ICAI / ICMAI, tax, GST, audit, frauds, SEBI, RBI ...).

Stories come only from the RSS feeds in config.yaml (news.feeds). Claude picks the most useful ones,
writes each story from the article's own text, and a second Claude call checks every line against
that text. A story that fails the check is replaced by the next one; if fewer than the planned
number pass, or anything is doubtful, the post is held for /approve news."""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from .config import Config, batch_dir

NEWS = "news"
UA = {"User-Agent": "Mozilla/5.0 (compatible; cacmagyan-news/1.0; +https://www.instagram.com/cacmagyan/)"}

DEFAULT_FEEDS = [
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/wealth/tax/rssfeeds/47119912.cms"},
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/small-biz/gst/rssfeeds/58475404.cms"},
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms"},
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/rssfeeds/13358259.cms"},
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/jobs/exams-results/rssfeeds/97860466.cms"},
    {"name": "Mint", "url": "https://www.livemint.com/rss/money"},
    {"name": "Mint", "url": "https://www.livemint.com/rss/companies"},
    {"name": "Mint", "url": "https://www.livemint.com/rss/education"},
    {"name": "TaxGuru", "url": "https://taxguru.in/feed/"},
]

# what makes a headline interesting for CA / CMA students (weight per match)
KEYWORDS = {
    3: ["icai", "icmai", "chartered accountant", "cost accountant", "ca exam", "cma exam", "ca final", "ca inter",
        "ca foundation", "cma inter", "cma final", "nfra", "auditor", "audit"],
    2: ["cbdt", "cbic", "gst", "income tax", "itr", "tds", "tcs", "fraud", "scam", "sebi", "rbi", "penalty",
        "accounting standard", "ind as", "mca", "companies act", "insolvency", "ibc", "nclt", "budget",
        "forensic", "misappropriation", "embezzlement", "money laundering", "enforcement directorate"],
    1: ["tax", "finance ministry", "bank", "compliance", "notification", "circular", "deadline", "due date",
        "return", "refund", "regulator", "listed", "disclosure", "balance sheet", "earnings", "results"],
}

TAG_COLORS = {"ICAI": "#1F5BA8", "ICMAI": "#6E3FA8", "Income Tax": "#C8372F", "GST": "#D9651A", "Audit": "#1F7A5A",
              "Fraud": "#8B1E1E", "SEBI": "#0F6E8C", "RBI": "#7A5A12", "Banking": "#2F4F9F", "Markets": "#2A7D2E",
              "Economy": "#455A64", "Budget": "#A8740A", "Corporate Law": "#5D4037", "Accounting": "#1F5566",
              "Exams": "#B03A6E"}
TAGS = ["ICAI", "ICMAI", "Income Tax", "GST", "Audit", "Fraud", "SEBI", "RBI", "Banking", "Markets", "Economy",
        "Budget", "Corporate Law", "Accounting", "Exams"]


def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


# ── storage ──────────────────────────────────────────────────
def path(date: dt.date):
    return batch_dir(date) / "news.json"


def load(date: dt.date) -> dict | None:
    p = path(date)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save(date: dt.date, item: dict) -> None:
    p = path(date)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(item, fh, ensure_ascii=False, indent=2)


def recent_titles(date: dt.date, days: int = 7) -> list[str]:
    """Headlines and source titles used in the last `days` days, so a story isn't repeated."""
    out = []
    for i in range(1, days + 1):
        old = load(date - dt.timedelta(days=i)) or {}
        for s in old.get("stories") or []:
            out += [s.get("headline", ""), s.get("source_title", "")]
    return [t for t in out if t]


# ── feeds ────────────────────────────────────────────────────
class _Text(HTMLParser):
    """Collects the text of <p> paragraphs (the article body on most news pages)."""

    def __init__(self):
        super().__init__()
        self.depth, self.skip, self.parts, self.cur = 0, 0, [], []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "figure", "aside", "nav", "footer"):
            self.skip += 1
        elif tag == "p":
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "figure", "aside", "nav", "footer"):
            self.skip = max(0, self.skip - 1)
        elif tag == "p" and self.depth:
            self.depth -= 1
            text = " ".join("".join(self.cur).split())
            if len(text) >= 40:
                self.parts.append(text)
            self.cur = []

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.cur.append(data)


def plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return " ".join(html.unescape(text).split())


def _date(text: str) -> dt.datetime | None:
    if not text:
        return None
    try:
        d = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def parse_feed(xml_text: str, source: str) -> list[dict]:
    """RSS <item> or Atom <entry> -> [{title, link, published, summary, source}]."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return []
    out = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        get = {c.tag.rsplit("}", 1)[-1]: c for c in el}
        title = plain((get.get("title").text if get.get("title") is not None else "") or "")
        link_el = get.get("link")
        link = ""
        if link_el is not None:
            link = (link_el.text or link_el.get("href") or "").strip()
        when = None
        for k in ("pubDate", "published", "updated", "date"):
            if get.get(k) is not None and get[k].text:
                when = _date(get[k].text)
                if when:
                    break
        summary = ""
        for k in ("encoded", "description", "summary", "content"):
            if get.get(k) is not None and (get[k].text or "").strip():
                summary = plain(get[k].text)
                break
        if title and link:
            out.append({"title": title, "link": link, "published": when.isoformat() if when else "",
                        "summary": summary[:1500], "source": source})
    return out


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 3}


def similar(a: str, b: str) -> bool:
    x, y = _words(a), _words(b)
    return bool(x and y) and len(x & y) / max(1, min(len(x), len(y))) >= 0.6


def score(item: dict) -> int:
    title, text = item["title"].lower(), item.get("summary", "").lower()
    total = 0
    for weight, words in KEYWORDS.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", title):
                total += 2 * weight
            elif re.search(rf"\b{re.escape(w)}\b", text):
                total += weight
    return total


def gather(cfg: Config, now: dt.datetime, used: list[str], get=None) -> list[dict]:
    """Recent, relevant, new candidate stories, best first."""
    import requests

    get = get or (lambda url: requests.get(url, headers=UA, timeout=20))
    hours = float(cfg.news.get("hours", 30))
    feeds = cfg.news.get("feeds") or DEFAULT_FEEDS
    items = []
    for f in feeds:
        try:
            r = get(f["url"])
            if getattr(r, "status_code", 200) != 200:
                print(f"  ! news feed {f['url']}: HTTP {r.status_code}")
                continue
            got = parse_feed(r.text, f.get("name", ""))
            print(f"  • {f.get('name', '')}: {len(got)} items")
            items += got
        except Exception as exc:                       # one broken feed never stops the post
            print(f"  ! news feed {f['url']}: {exc}")
    fresh = []
    for it in items:
        when = _date(it["published"])
        if when and (now - when).total_seconds() > hours * 3600:
            continue
        if any(similar(it["title"], u) for u in used):
            continue
        it["score"] = score(it)
        if it["score"] <= 0:
            continue
        if any(similar(it["title"], k["title"]) for k in fresh):
            continue
        fresh.append(it)
    fresh.sort(key=lambda it: (it["score"], it["published"]), reverse=True)
    for i, it in enumerate(fresh, 1):
        it["id"] = f"n{i}"
    return fresh[: int(cfg.news.get("candidates", 30))]


def article_text(url: str, get=None) -> str:
    import requests

    get = get or (lambda u: requests.get(u, headers=UA, timeout=20))
    try:
        r = get(url)
        if getattr(r, "status_code", 200) != 200:
            return ""
        p = _Text()
        p.feed(r.text)
        return " ".join(p.parts)[:5000]
    except Exception:
        return ""


# ── Claude ───────────────────────────────────────────────────
PICK_TOOL = {
    "name": "pick_news",
    "description": "Pick the stories for tonight's news carousel.",
    "input_schema": {"type": "object", "properties": {
        "picks": {"type": "array", "minItems": 1, "maxItems": 8, "items": _s("A candidate id, e.g. 'n3'"),
                  "description": "Best first: the most useful stories for Indian CA and CMA students, then backups."}},
        "required": ["picks"]},
}

PICK_SYSTEM = """You choose tonight's news for an Instagram page for Indian CA and CMA students (ICAI and ICMAI courses).
Pick up to 8 candidates, best first, from the list. Good: ICAI / ICMAI announcements, exams and results; income tax, GST, TDS changes, due dates and CBDT/CBIC notices; audit and accounting (NFRA, auditors, Ind AS); SEBI and RBI actions; corporate frauds, scams and penalties involving accounts or audit; company law and insolvency; budget and economy news students should know.
Avoid: stock tips and daily market moves, personal opinions and columns, celebrity or political news, ads and offers, and two candidates about the same event."""

WRITE_TOOL = {
    "name": "write_story",
    "description": "Write one news story for a slide.",
    "input_schema": {"type": "object", "properties": {
        "tag": {"type": "string", "enum": TAGS},
        "headline": _s("Plain headline in your own words, at most 70 characters"),
        "points": {"type": "array", "minItems": 2, "maxItems": 3,
                   "items": _s("What happened, one fact per point, at most 110 characters each")},
        "why_it_matters": _s("Why a CA / CMA student should care, at most 120 characters"),
        "usable": {"type": "boolean", "description": "False if the source text is too thin or not really news"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
        "required": ["tag", "headline", "points", "why_it_matters", "usable", "confidence"]},
}

WRITE_SYSTEM = """You write one news story for a slide in a nightly news carousel for Indian CA and CMA students.
Rules
1. Use ONLY facts stated in the source text. No outside facts, no guesses, no numbers, dates, names or amounts that are not in it.
2. Your own simple words: never copy sentences from the source.
3. Allegations stay allegations: write "alleged", "accused" or "according to <agency>" unless the source says a court convicted the person. Never call anyone guilty or a fraudster on your own.
4. Neutral news tone. No opinions, advice, hype, emoji or hashtags.
5. why_it_matters links the news to what a CA / CMA student studies or will do at work (taxation, audit, accounts, law, compliance, exams); keep it general and true.
6. If the source text is too thin to write three solid lines, set usable false."""

CHECK_TOOL = {
    "name": "check_story",
    "description": "Report problems in the news story.",
    "input_schema": {"type": "object", "properties": {
        "issues": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["none", "minor", "major"]}},
        "required": ["issues", "severity"]},
}

CHECK_SYSTEM = """You are a careful news editor. Compare the story with its source text line by line.
"major" if any fact, number, date, name or amount in the story is not supported by the source; if it states or implies guilt where the source reports only an allegation or investigation; if it copies sentences from the source; or if the headline misleads. "minor" for wording only. "none" if every line is supported."""


def _story_text(s: dict) -> str:
    return "\n".join([f"Tag: {s.get('tag', '')}", f"Headline: {s.get('headline', '')}"]
                     + [f"Point: {p}" for p in s.get("points") or []] + [f"Why it matters: {s.get('why_it_matters', '')}"])


def _source_block(c: dict) -> str:
    return (f"Source: {c['source']} ({c.get('published', '')[:10]})\nTitle: {c['title']}\n"
            f"Text: {c.get('text') or c.get('summary', '')}")


def problems(s: dict) -> list[str]:
    out = []
    if len(s.get("headline") or "") > 80:
        out.append("headline is longer than 70 characters")
    if not 2 <= len(s.get("points") or []) <= 3:
        out.append("needs 2-3 points")
    if any(len(p) > 125 for p in s.get("points") or []):
        out.append("a point is longer than 110 characters")
    if len(s.get("why_it_matters") or "") > 135:
        out.append("why_it_matters is longer than 120 characters")
    if s.get("tag") not in TAGS:
        out.append("tag must be one of the list")
    return out


def make(cfg: Config, date: dt.date, instruction: str = "", get=None) -> dict:
    """Gathers, writes and checks tonight's stories. Returns the news item (not yet drawn)."""
    from .generator import GenerationError, _call_claude, call_checker

    want = int(cfg.news.get("stories", 3))
    now = cfg.now()
    candidates = gather(cfg, now, recent_titles(date), get=get)
    item = {"kind": NEWS, "date": date.isoformat(), "stories": [], "notes": []}
    if len(candidates) < want:
        item.update(error=f"only {len(candidates)} relevant new stories in the feeds")
        return item
    model = cfg.models.get("writer", "claude-sonnet-5-5")
    listing = "\n".join(f"{c['id']} | {c['source']} | {c['published'][:16]} | {c['title']} | {c['summary'][:240]}"
                        for c in candidates)
    user = f"Date: {date.strftime('%d %B %Y')}\nCandidates (id | source | published | title | summary):\n{listing}\n"
    if instruction:
        user += f"\nReviewer's instruction: {instruction}\n"
    try:
        picks = _call_claude(model, PICK_SYSTEM, user, PICK_TOOL, max_tokens=600).get("picks") or []
    except GenerationError as exc:
        item.update(error=f"Claude couldn't pick the stories: {exc}")
        return item
    by_id = {c["id"]: c for c in candidates}
    order = [by_id[p] for p in picks if p in by_id] + [c for c in candidates if c["id"] not in picks]
    for c in order:
        if len(item["stories"]) >= want:
            break
        c["text"] = article_text(c["link"], get=get)
        if len(c["text"]) < 300 and len(c.get("summary", "")) < 200:
            item["notes"].append(f"skipped '{c['title'][:60]}': too little text to check")
            continue
        try:
            s = _call_claude(model, WRITE_SYSTEM, _source_block(c), WRITE_TOOL, max_tokens=900)
        except GenerationError as exc:
            item["notes"].append(f"couldn't write '{c['title'][:60]}': {exc}")
            continue
        if not s.get("usable", True) or problems(s):
            item["notes"].append(f"skipped '{c['title'][:60]}': " + ("; ".join(problems(s)) or "not usable"))
            continue
        check = call_checker(cfg, CHECK_SYSTEM, _source_block(c) + "\n\nSTORY\n" + _story_text(s), CHECK_TOOL,
                             max_tokens=900)
        if check.get("severity") == "major":
            item["notes"].append(f"dropped '{s['headline'][:60]}': " + "; ".join(check.get("issues", []))[:200])
            continue
        s.update(source=c["source"], source_title=c["title"], link=c["link"], published=c["published"],
                 check="minor" if check.get("severity") == "minor" else "ok",
                 check_notes=check.get("issues", []))
        item["stories"].append(s)
    n = len(item["stories"])
    if n == 0:
        item.update(error="no story passed the fact check")
        return item
    doubts = [s["headline"] for s in item["stories"] if s.get("confidence") == "low"]
    if n < want:
        item.update(hold=True, hold_reason=f"only {n} of {want} stories passed the fact check")
    elif doubts:
        item.update(hold=True, hold_reason="the writer was unsure about: " + "; ".join(doubts))
    else:
        item.update(hold=False, hold_reason="")
    item["caption"] = caption(cfg, item, date)
    return item


# ── caption ──────────────────────────────────────────────────
NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]


def caption(cfg: Config, item: dict, date: dt.date) -> str:
    from .caption import post_ref

    handle = cfg.brand.get("handle", "").strip()
    lines = [f"📰 CA · CMA Daily News · {date.strftime('%d %b %Y')}", ""]
    for i, s in enumerate(item.get("stories") or []):
        lines.append(f"{NUMS[i]} {s['headline']} ({s['source']})")
    sources = sorted({s["source"] for s in item.get("stories") or []})
    lines += ["", "Swipe for what happened and why it matters for your CA / CMA studies.",
              f"Summarised for students from {', '.join(sources)}. Read the full reports there.",
              "Save 🔖 and share with your study group."]
    if handle:
        lines += ["", f"Follow {handle} for daily MCQs, concept notes and news."]
    tags = cfg.news.get("hashtags") or ["#CANews", "#CMANews", "#ICAI", "#ICMAI", "#TaxNews"]
    lines += ["", " ".join(tags[: int(cfg.instagram.get("max_hashtags", 5))]), "", post_ref(NEWS, date)]
    return "\n".join(lines)[:2200]


def alt_texts(item: dict) -> list[str]:
    stories = item.get("stories") or []
    out = ["CA CMA Daily News. Top stories: " + "; ".join(s["headline"] for s in stories)]
    for s in stories:
        out.append(f"{s['tag']}: {s['headline']}. " + " ".join(s.get("points") or []) + f" Why it matters: {s['why_it_matters']}")
    out.append("That's today's news. Follow for daily MCQs, concept notes and news.")
    return [" ".join(t.split())[:900] for t in out]
