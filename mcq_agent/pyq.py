"""Past-paper questions from the question banks in pyq/*.json, so a concept note can say where its
concept was asked before (PY = ICMAI past paper, MQP = ICMAI model question paper)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent
MAX_LINES = 140          # past-paper lines shown to the writer when it chooses its own concept
TOPIC_LINES = 40         # lines shown when the concept is already decided
# Papers that share a syllabus with a paper that has a bank: their notes use that bank, and the
# radar names the exam it came from ("CMA Inter PY D24").
SHARED = {
    ("cma_cat", "Paper 1A"): [("cma_inter", "Paper 6", "")],
    ("cma_cat", "Paper 2A"): [("cma_inter", "Paper 6", ""), ("cma_inter", "Paper 10", "Corporate Accounting")],
}
EXAM = {"cma_inter": "CMA Inter", "cma_cat": "CMA CAT", "cma_final": "CMA Final",
        "ca_foundation": "CA Foundation", "ca_inter": "CA Inter", "ca_final": "CA Final"}
_STOP = set("a an and the of to in on for by with from as at or is are its into vs v under per its".split())


@lru_cache(maxsize=None)
def _banks() -> tuple[dict, ...]:
    out = []
    for f in sorted(DIR.glob("*.json")) if DIR.is_dir() else []:
        try:
            with open(f, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, ValueError) as exc:
            print(f"  ! question bank {f.name} unreadable: {exc}")
    return tuple(out)


def _ref(q: dict) -> str:
    return (f"{q['rp']}-" if q.get("rp") else "") + f"{q['chapter']}-{q['q']}"


def questions(course_id: str, paper: dict) -> list[dict]:
    """The bank's past-paper questions for this course and paper (and half of a paper, if it has `part`)."""
    wanted = [(course_id, paper.get("code"), paper.get("part") or "")]
    wanted += SHARED.get((course_id, paper.get("code")), [])
    out = []
    for cid, code, part in wanted:
        for b in _banks():
            if not isinstance(b, dict) or b.get("course") != cid or b.get("paper_code") != code:
                continue
            for q in b.get("questions", []):
                if part and q.get("part") and q["part"].lower() != part.lower():
                    continue
                out.append(q if cid == course_id else
                           dict(q, via=EXAM.get(cid, cid), rp="P" + re.sub(r"\D", "", code)))
    return out


def _when(tag: str) -> tuple[int, int]:
    """'PY D24' -> (2024, 12); used to put the latest papers first."""
    m = re.search(r"\b([JD])(\d\d)\b", tag)
    return (2000 + int(m.group(2)), 12 if m.group(1) == "D" else 6) if m else (0, 0)


def _rank(q: dict) -> tuple:
    py = [t for t in q["papers"] if t.startswith("PY")]
    latest = max((_when(t) for t in q["papers"]), default=(0, 0))
    return (1 if py else 0, latest, len(q["papers"]))


def label(q: dict) -> str:
    """'PY D24 · 7 marks' / 'PY J19 · MCQ' / 'MQP D25 S1, MQP J26 S2 · MCQ'."""
    tags = sorted(q["papers"], key=_when, reverse=True)
    what = "MCQ" if q["kind"] in ("mcq", "tf") else (f"{q['marks']} marks" if q.get("marks") else
                                                    "theory" if q["kind"] == "theory" else "practical")
    via = f"{q['via']} " if q.get("via") else ""
    return f"{via}{', '.join(tags[:3])} · {what}"


def _words(s: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", s.lower().replace("-", ""))
    return {w[:6] if len(w) > 6 else w.rstrip("s") for w in words if w not in _STOP and len(w) > 2}


def relevant(qs: list[dict], topic: str, n: int = TOPIC_LINES) -> list[dict]:
    want = _words(topic)
    if not want:
        return []
    import math
    docs = [(_words(q["text"]), _words(q["section"])) for q in qs]
    idf = {w: math.log((len(qs) + 1) / (1 + sum(1 for t, _ in docs if w in t))) for w in want}
    scored = []
    for q, (text, sec) in zip(qs, docs):
        hit = sum(idf[w] for w in want & text) + 0.3 * sum(idf[w] for w in want & sec)
        if hit > 0.5:
            scored.append((round(hit, 2), _rank(q), q))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [q for _, _, q in scored[:n]]


def index_text(qs: list[dict], limit: int = MAX_LINES, keep: list[dict] | None = None) -> str:
    """One line per question for the writer: ref, paper tags, section, a short extract.
    `keep` (e.g. the questions on a concept the reviewer asked for) are always listed."""
    keep = keep or []
    seen = {_ref(q) for q in keep}
    best = keep + [q for q in sorted(qs, key=_rank, reverse=True) if _ref(q) not in seen][:max(limit - len(keep), 0)]
    best.sort(key=lambda q: (q["chapter"], q["q"]))
    lines = []
    for q in best:
        text = q["text"]
        if q["kind"] == "mcq":
            text = text.split("(a)")[0].strip()
        ans = f" [answer {q['answer']}]" if q.get("answer") else ""
        lines.append(f"{_ref(q)} | {label(q)} | {q['section'][:48]} | {text[:150]}{ans}")
    return "\n".join(lines)


def section_counts(qs: list[dict], n: int = 25) -> str:
    """Which sections past papers ask most, to steer the choice of concept."""
    count: dict[str, int] = {}
    for q in qs:
        if any(t.startswith("PY") for t in q["papers"]):
            key = f"Ch {q['chapter']} {q['section'] or q['chapter_title']}"
            count[key] = count.get(key, 0) + 1
    top = sorted(count.items(), key=lambda x: -x[1])[:n]
    return "\n".join(f"- {k}: {v} past-paper questions" for k, v in top)


def by_ref(qs: list[dict]) -> dict[str, dict]:
    return {_ref(q): q for q in qs}


def resolve(items: list[dict], qs: list[dict]) -> tuple[list[dict], list[str]]:
    """Keeps the writer's past-paper points whose ref is a real bank question and adds its tags."""
    refs, out, problems = by_ref(qs), [], []
    for it in items or []:
        ref = str(it.get("ref") or "").strip()
        point = str(it.get("point") or "").strip()
        if not point:
            continue
        q = refs.get(ref)
        if not q:
            problems.append(f"past paper ref '{ref}' is not in the past-paper list")
            continue
        out.append({"ref": ref, "papers": label(q), "point": point, **({"via": q["via"]} if q.get("via") else {})})
    return out[:3], problems


def source_lines(items: list[dict], qs: list[dict]) -> list[str]:
    """The cited questions in full, for the examiner who checks the note."""
    refs = by_ref(qs)
    return [f"past paper {i} source ({it['papers']}): {refs[it['ref']]['text'][:500]}"
            + (f" [answer {refs[it['ref']]['answer']}]" if refs[it['ref']].get("answer") else "")
            for i, it in enumerate(items, 1) if it.get("ref") in refs]
