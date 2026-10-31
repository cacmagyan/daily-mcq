"""Concept of the day: a 4-slide handwritten-notebook carousel (concept, formula, study trick,
common mistakes), written by Claude and checked by a second Claude call before it can post."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Callable

from .config import Config

SLIDES = 4
SLIDE_NAMES = {1: "concept", 2: "formula", 3: "study trick", 4: "mistakes"}
SLIDE_FIELDS = {1: "simple_words, the definitions or the key points",
                2: "the formulas, their legends or the table",
                3: "the memory trick, the steps, the exam tip or the doubt answer",
                4: "the mistakes"}


def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


WRITE_TOOL = {
    "name": "submit_concept",
    "description": "Submit the finished concept note.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": _s("The one concept covered, at most 44 characters, e.g. 'Economic Order Quantity (EOQ)'"),
            "title": _s("Slide 1 title, first line, at most 22 characters"),
            "title_highlight": _s("Slide 1 title, second line shown in highlighter, at most 20 characters; may be empty"),
            "hook": _s("Short playful handwritten line beside the title, at most 40 characters, e.g. 'order the right qty!'"),
            "simple_words": _s("The idea in one line for a weak student, at most 120 characters"),
            "definitions": {"type": "array", "minItems": 1, "maxItems": 2, "description": "1-2 definition cards",
                            "items": {"type": "object", "properties": {
                                "term": _s("Term, at most 40 characters"),
                                "meaning": _s("Meaning, at most 170 characters"),
                                "note": _s("Optional red handwritten line, at most 70 characters; may be empty")},
                                "required": ["term", "meaning", "note"]}},
            "key_points": {"type": "array", "minItems": 2, "maxItems": 4, "items": _s("At most 100 characters each")},
            "formula_heading": _s("Slide 2 title, at most 24 characters, different from slide 1, e.g. 'The EOQ Formula' or 'The 5-Point Comparison'"),
            "formula_hook": _s("Short handwritten line for slide 2, at most 32 characters"),
            "formulas": {"type": "array", "maxItems": 3,
                         "description": "0-3 formulas. A fraction uses numerator + denominator (rhs empty); "
                                        "anything else uses rhs (numerator and denominator empty).",
                         "items": {"type": "object", "properties": {
                             "name": _s("Formula name, at most 40 characters"),
                             "lhs": _s("Left side, at most 24 characters, e.g. 'EOQ'"),
                             "rhs": _s("Right side when it is not a fraction, at most 70 characters; else empty"),
                             "numerator": _s("Top of the fraction, at most 40 characters; else empty"),
                             "denominator": _s("Bottom of the fraction, at most 32 characters; else empty"),
                             "square_root": {"type": "boolean", "description": "True if the whole fraction is under a square root"},
                             "suffix": _s("Text after the fraction, e.g. '× 100', at most 14 characters; else empty"),
                             "legend": _s("What each symbol means, at most 130 characters")},
                             "required": ["name", "lhs", "rhs", "numerator", "denominator", "square_root", "suffix", "legend"]}},
            "table": {"type": "object", "description": "Optional small table for theory/law topics; empty headers and rows if not used",
                      "properties": {
                          "headers": {"type": "array", "maxItems": 3, "items": _s("At most 20 characters")},
                          "rows": {"type": "array", "maxItems": 5,
                                   "items": {"type": "array", "minItems": 2, "maxItems": 3, "items": _s("At most 44 characters")}}},
                      "required": ["headers", "rows"]},
            "entries": {"type": "array", "maxItems": 3,
                        "description": "0-3 journal entries for slide 2, shown in the two-line journal form "
                                       "('Bank A/c ... Dr' then 'To Share Capital A/c'). Every journal entry of the note goes "
                                       "here, never in the table. Empty if the concept has no entries.",
                        "items": {"type": "object", "properties": {
                            "label": _s("When it is passed, at most 34 characters, e.g. 'On forfeiture'"),
                            "debit": {"type": "array", "minItems": 1, "maxItems": 3,
                                      "items": _s("An account debited, at most 34 characters, ending 'A/c', e.g. 'Equity Share Capital A/c'")},
                            "credit": {"type": "array", "minItems": 1, "maxItems": 3,
                                       "items": _s("An account credited, at most 34 characters, without 'To', e.g. 'Forfeited Shares A/c'")},
                            "narration": _s("Short narration without brackets, at most 70 characters, e.g. 'Being shares forfeited for non-payment of call'")},
                            "required": ["label", "debit", "credit", "narration"]}},
            "insight": {"type": "object", "description": "Key-insight callout at the bottom of slide 2",
                        "properties": {
                            "punchline": _s("Short punchline in red marker, at most 36 characters, e.g. 'Same machine, two treatments!'"),
                            "text": _s("One sentence that explains it, at most 120 characters")},
                        "required": ["punchline", "text"]},
            "trick_hook": _s("Short handwritten line for slide 3, at most 32 characters"),
            "memory_trick": {"type": "object", "properties": {
                "mnemonic": _s("The trick itself, at most 30 characters, e.g. 'Two Aunties Order Chai'"),
                "explanation": _s("How it maps to the concept, at most 170 characters")},
                "required": ["mnemonic", "explanation"]},
            "steps": {"type": "array", "minItems": 2, "maxItems": 5,
                      "items": _s("Order of working in the exam, at most 34 characters each")},
            "exam_tip": _s("One exam tip, at most 150 characters"),
            "doubt": {"type": "object", "properties": {
                "question": _s("A doubt students usually raise, at most 80 characters"),
                "answer": _s("Its answer, at most 170 characters")},
                "required": ["question", "answer"]},
            "mistakes_hook": _s("Short handwritten line for slide 4, at most 32 characters"),
            "mistakes": {"type": "array", "minItems": 2, "maxItems": 4,
                         "items": {"type": "object", "properties": {
                             "wrong": _s("What students wrongly do or write, at most 90 characters"),
                             "right": _s("The correct way, at most 110 characters")},
                             "required": ["wrong", "right"]}},
            "past_papers": {"type": "array", "maxItems": 3,
                            "description": "1-3 points from the past-paper list in the request that ask THIS concept "
                                           "(shown as 'Past exam radar' on slide 4). Empty only if no past-paper list was given "
                                           "or none of its questions is on this concept.",
                            "items": {"type": "object", "properties": {
                                "ref": _s("The question's ref exactly as in the list, e.g. '1-106'"),
                                "point": _s("What that question tested or the twist in it, in your own words, at most 100 "
                                            "characters, e.g. 'Allotment and call unpaid; only part of the shares reissued'")},
                                "required": ["ref", "point"]}},
            "applicability": _s("Law/standard basis for tax or law topics, at most 60 characters; empty otherwise"),
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reviewer_note": _s("Anything the human reviewer should double-check; empty if nothing"),
        },
        "required": ["topic", "title", "title_highlight", "hook", "simple_words", "definitions", "key_points",
                     "formula_heading", "formula_hook", "formulas", "table", "entries", "insight", "trick_hook", "memory_trick", "steps",
                     "exam_tip", "doubt", "mistakes_hook", "mistakes", "past_papers", "applicability", "confidence", "reviewer_note"],
    },
}

CHECK_TOOL = {
    "name": "submit_check",
    "description": "Submit the problems found in the concept note.",
    "input_schema": {
        "type": "object",
        "properties": {
            "issues": {"type": "array", "items": {"type": "string"},
                       "description": "Each problem with where it is and the correct version. Empty if none."},
            "severity": {"type": "string", "enum": ["none", "minor", "major"]},
        },
        "required": ["issues", "severity"],
    },
}

WRITER_SYSTEM = """You write "Concept of the day" notes for an Instagram page for Indian CA and CMA students; the note is signed by {author}, who teaches this paper. Each note is a 4-slide carousel in his handwritten cartoon notebook style:
  Slide 1 Concept: title, "In simple words" line, 1-2 definition cards, 2-4 key points.
  Slide 2 Formula: 1-3 formulas with symbol legends, or a small table for theory and law topics, and the journal entries if the concept has any, then a one-line key insight.
  Slide 3 Study trick: a memory trick, the order of working in the exam, an exam tip, a doubt buster.
  Slide 4 Common mistakes: 2-4 mistakes students make, each with the correct way, then a "Past exam radar" of 1-3 past-paper points when a past-paper list is given.

Rules
1. Choose ONE core concept from the given paper that is examined often and fits on 4 phone slides; never a whole chapter. Tomorrow's MCQ for this course will test it.
2. Short and simple: points, cards, formulas, tables. Prose at most 1-2 sentences in any field.
3. Simple, direct Indian classroom English. Never use filler such as "It is important to note", "Let's dive", "crucial", "pivotal", "in today's world", and no motivational lines. No emoji.
4. Explain formulas with symbols (A, O, C …) and a legend. No worked numerical examples. If a figure is unavoidable, use Indian formats (₹, lakh, crore).
5. Slide 2: formulas for numerical topics. For theory or law topics use a table instead (comparison, conditions, or a format with xxx), with a header row and at most 5 rows. At most 3 formulas, or 2 formulas plus a table of at most 3 rows.
6. Mark at most 3 key terms per slide with ==double equals== (yellow highlighter), and points where students lose marks with !!double exclamation marks!! (red ink). Never nest or leave a mark open.
7. The memory trick must be truly memorable (a mnemonic, a tiny story or a picture in words) and technically correct. Never a trick that could mislead.
8. Mistakes are real exam errors for this concept; every "right" text must be fully correct.
9. Law and tax: follow exactly this basis: {law_text}. Never invent a section number, rate or limit; if unsure, describe the provision without it. Put a short form of the basis in `applicability`. Put anything a reviewer should verify in `reviewer_note`.
10. Accounting standards: Ind AS / AS as currently applicable. Costing: ICMAI/ICAI study-material terminology.
11. Original wording. Never copy study material, RTPs, MTPs or past papers.
12. Length limits in the field descriptions are strict: the text must fit on phone slides.
13. Every table cell, sign (Add/Deduct, Dr/Cr, +/−), formula and "right" statement must be correct in every case the note covers. If a rule has an exception, say it or leave that case out.
14. Journal entries always go in `entries` (shown in the two-line journal form: the debit line "… A/c Dr", then "To … A/c"). Never write a journal entry in the table, and never make a table with Debit / Credit columns. With entries on slide 2, use at most 1 formula or a table of at most 3 rows.
15. If a past-paper list is given, prefer a concept those papers actually ask, and fill `past_papers` only with questions from that list that test this exact concept. Cite each by its ref; the point says what the question tested in your own words (no names or figures from the question). With past papers on slide 4, give at most 3 mistakes.
{traps}"""

CHECKER_SYSTEM = """You are a strict examiner checking a concept note for {course} ({body}) students, paper: {paper}.
Method: go through the note line by line. For every table cell, every sign or direction (Add/Deduct, Dr/Cr, +/−, increase/decrease), every formula and symbol legend, and every "correct way", first work out from your own knowledge what the correct entry is, and only then compare it with the note. Then check the definitions, key points, memory trick, steps, exam tip, doubt answer and mistakes against current ICAI/ICMAI study material.
Severity "major" if anything is wrong or misleading: a wrong table cell or sign, a wrong formula or legend, a wrong definition or rule, a "mistake" that is actually correct, a wrong "correct way", an invented or wrong section number, rate or limit, outdated law, or a memory trick that teaches something false. "minor" for wording polish only. "none" if it is all correct.
For each problem say where it is and give the correct version.
Journal entries: check every debit and credit account and its side. Past exam radar: each point must describe its source question correctly and the source question must be on this concept; if not, that is "major".
{law_line}{traps}"""

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")
LIMITS = {"topic": 44, "title": 22, "title_highlight": 20, "hook": 40, "simple_words": 120, "formula_heading": 24,
          "formula_hook": 32, "trick_hook": 32, "exam_tip": 150, "mistakes_hook": 32}
GRACE = 1.15    # length limits are checked with 15% grace; the slide fit check is the real test


def texts(c: dict) -> list[tuple[str, str]]:
    """Every visible text with a label, for checks and for the checker prompt."""
    out = [(k, str(c.get(k) or "")) for k in ("topic", "title", "title_highlight", "hook", "simple_words",
                                               "formula_heading", "formula_hook", "trick_hook", "exam_tip", "mistakes_hook")]
    for i, d in enumerate(c.get("definitions") or [], 1):
        out += [(f"definition {i} term", d.get("term", "")), (f"definition {i} meaning", d.get("meaning", "")),
                (f"definition {i} note", d.get("note", ""))]
    out += [(f"key point {i}", p) for i, p in enumerate(c.get("key_points") or [], 1)]
    for i, f in enumerate(c.get("formulas") or [], 1):
        out += [(f"formula {i} {k}", str(f.get(k) or "")) for k in ("name", "lhs", "rhs", "numerator", "denominator", "suffix", "legend")]
    table = c.get("table") or {}
    out += [("table header", " | ".join(table.get("headers") or []))]
    out += [(f"table row {i}", " | ".join(r)) for i, r in enumerate(table.get("rows") or [], 1)]
    insight = c.get("insight") or {}
    out += [("insight punchline", insight.get("punchline", "")), ("insight text", insight.get("text", ""))]
    trick = c.get("memory_trick") or {}
    out += [("memory trick", trick.get("mnemonic", "")), ("memory trick explanation", trick.get("explanation", ""))]
    out += [(f"step {i}", s) for i, s in enumerate(c.get("steps") or [], 1)]
    for i, e in enumerate(c.get("entries") or [], 1):
        out += [(f"journal entry {i}", f"{e.get('label', '')}: " + "; ".join(f"{a} Dr" for a in e.get("debit") or [])
                 + "; " + "; ".join(f"To {a}" for a in e.get("credit") or []) + f" ({e.get('narration', '')})")]
    doubt = c.get("doubt") or {}
    out += [("doubt question", doubt.get("question", "")), ("doubt answer", doubt.get("answer", ""))]
    for i, m in enumerate(c.get("mistakes") or [], 1):
        out += [(f"mistake {i} wrong", m.get("wrong", "")), (f"mistake {i} right", m.get("right", ""))]
    for i, p in enumerate(c.get("past_papers") or [], 1):
        out += [(f"past paper {i}", f"{p.get('papers') or p.get('ref', '')}: {p.get('point', '')}")]
    return out


def tidy(c: dict) -> dict:
    def clean(v):
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return [clean(x) for x in v]
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        return v
    c = clean(c)
    c["definitions"] = [d for d in c.get("definitions") or [] if d.get("term") and d.get("meaning")][:2]
    c["key_points"] = [p for p in c.get("key_points") or [] if p][:4]
    c["formulas"] = [f for f in c.get("formulas") or [] if f.get("rhs") or f.get("denominator")][:3]
    table = c.get("table") or {}
    headers = [h for h in table.get("headers") or [] if h][:3]
    rows = [r[:len(headers)] for r in table.get("rows") or [] if headers and any(r)][:5]
    c["table"] = {"headers": headers, "rows": [r + [""] * (len(headers) - len(r)) for r in rows]}
    entries = []
    for e in c.get("entries") or []:
        dr = [_acct(a) for a in e.get("debit") or [] if a][:3]
        cr = [_acct(re.sub(r"^(To|By)\s+", "", a, flags=re.I)) for a in e.get("credit") or [] if a][:3]
        if dr and cr:
            entries.append({"label": e.get("label", ""), "debit": dr, "credit": cr,
                            "narration": (e.get("narration") or "").strip("() ")})
    c["entries"] = entries[:3]
    c["past_papers"] = [p for p in c.get("past_papers") or [] if p.get("ref") and p.get("point")][:3]
    c["steps"] = [s for s in c.get("steps") or [] if s][:5]
    c["mistakes"] = [m for m in c.get("mistakes") or [] if m.get("wrong") and m.get("right")][:4]
    c["doubt"] = c.get("doubt") or {"question": "", "answer": ""}
    c["insight"] = c.get("insight") or {"punchline": "", "text": ""}
    c["memory_trick"] = c.get("memory_trick") or {"mnemonic": "", "explanation": ""}
    return c


def _acct(a: str) -> str:
    """'Bank A/c Dr' -> 'Bank A/c' (the template writes Dr and To itself)."""
    return re.sub(r"\s*(\.{2,}|…)?\s*\bDr\.?$", "", a.strip()).strip()


def validate(c: dict) -> list[str]:
    problems = []
    for key, limit in LIMITS.items():
        if len(str(c.get(key) or "")) > limit * GRACE:
            problems.append(f"{key} is longer than {limit} characters")
    for key in ("topic", "title", "simple_words", "exam_tip"):
        if not c.get(key):
            problems.append(f"{key} is empty")
    if not c.get("definitions"):
        problems.append("needs at least one definition card")
    if len(c.get("key_points") or []) < 2:
        problems.append("needs 2-4 key points")
    if len(c.get("steps") or []) < 2:
        problems.append("needs 2-5 steps")
    if len(c.get("mistakes") or []) < 2:
        problems.append("needs 2-4 mistakes")
    if not (c.get("memory_trick") or {}).get("mnemonic"):
        problems.append("the memory trick is empty")
    table = c.get("table") or {}
    if not c.get("formulas") and not table.get("rows") and not c.get("entries"):
        problems.append("slide 2 needs formulas, a table or journal entries")
    heads = " ".join(table.get("headers") or []).lower()
    if re.search(r"\b(debit|credit|dr|cr)\b", heads):
        problems.append("journal entries go in `entries` (two-line form), not in a table with Debit/Credit columns")
    for i, e in enumerate(c.get("entries") or [], 1):
        if any(len(a) > 34 * GRACE for a in e["debit"] + e["credit"]) or len(e.get("narration") or "") > 70 * GRACE:
            problems.append(f"journal entry {i} is too long (accounts 34, narration 70 characters)")
    if c.get("entries") and (len(c.get("formulas") or []) > 1 or len(table.get("rows") or []) > 3):
        problems.append("with journal entries use at most 1 formula or a table of at most 3 rows")
    for i, p in enumerate(c.get("past_papers") or [], 1):
        if len(p.get("point") or "") > 100 * GRACE:
            problems.append(f"past paper point {i} is longer than 100 characters")
    insight = c.get("insight") or {}
    if len(insight.get("punchline") or "") > 36 * GRACE or len(insight.get("text") or "") > 120 * GRACE:
        problems.append("the insight is too long (punchline 36, text 120 characters)")
    if table.get("rows") and len(table.get("headers") or []) < 2:
        problems.append("the table needs 2 or 3 headers")
    if len(c.get("formulas") or []) > 2 and table.get("rows"):
        problems.append("use at most 2 formulas when there is also a table")
    for f in c.get("formulas") or []:
        if f.get("denominator") and not f.get("numerator"):
            problems.append(f"formula '{f.get('name')}' has a denominator but no numerator")
    for label, text in texts(c):
        if text.count("==") % 2 or text.count("!!") % 2:
            problems.append(f"{label} has an unclosed ==highlight== or !!red ink!! mark")
        if _EMOJI.search(text):
            problems.append(f"{label} contains an emoji")
    return problems


def plain(c: dict) -> str:
    """The note as plain text, for the checker and for alt text."""
    lines = []
    for label, text in texts(c):
        text = text.replace("==", "").replace("!!", "")
        if text.strip():
            lines.append(f"{label}: {text}")
    for i, f in enumerate(c.get("formulas") or [], 1):
        if f.get("denominator"):
            expr = f"({f.get('numerator')}) / ({f.get('denominator')})"
            if f.get("square_root"):
                expr = f"square root of [{expr}]"
            lines.append(f"formula {i} as written: {f.get('lhs')} = {expr} {f.get('suffix') or ''}".rstrip())
    return "\n".join(lines)


def doodle(paper_name: str) -> str:
    """A cartoon ink doodle that suits the subject (factory, scales, calculator, book or bulb)."""
    p = paper_name.lower()
    if p.endswith(")") and "(" in p:           # a paper limited to one half: go by the half
        p = p[p.rindex("(") + 1:-1]
    if "cost" in p and "law" not in p:
        return DOODLES["factory"]
    if any(w in p for w in ("law", "tax", "gst", "audit", "ethic", "compliance")):
        return DOODLES["scales"]
    if any(w in p for w in ("financial management", "mathematic", "statistic", "economics", "valuation",
                            "strategic financial", "data analytics", "aptitude", "logical")):
        return DOODLES["calculator"]
    if any(w in p for w in ("accounting", "reporting")):
        return DOODLES["book"]
    return DOODLES["bulb"]


DOODLES = {
    "factory": '<svg width="150" height="130" viewBox="0 0 150 130"><rect class="ink-fill" x="104" y="20" width="18" height="40" fill="#FFFFFF"></rect><path class="thin" d="M113 16 C 106 10, 116 4, 123 9 C 131 5, 140 12, 132 16"></path><path class="ink-fill" d="M14 60 L14 118 L136 118 L136 50 L108 64 L108 50 L80 64 L80 50 L52 64 L52 50 L14 60 Z" fill="#DDF3E6"></path><circle class="dot" cx="62" cy="84" r="3"></circle><circle class="dot" cx="84" cy="84" r="3"></circle><path class="ink" d="M65 92 Q73 99 81 92"></path><rect class="ink-fill" x="24" y="96" width="20" height="22" fill="#FFF4C2"></rect><rect class="ink-fill" x="106" y="80" width="20" height="16" fill="#FFFFFF"></rect></svg>',
    "scales": '<svg width="150" height="150" viewBox="0 0 150 150"><path class="ink" d="M75 34 L75 132"></path><path class="ink-fill" d="M48 132 L102 132 L96 142 L54 142 Z" fill="#FFF4C2"></path><path class="ink" d="M22 46 L128 46"></path><circle class="ink-fill" cx="75" cy="26" r="10" fill="#FFE1C7"></circle><circle class="dot" cx="71" cy="25" r="1.8"></circle><circle class="dot" cx="79" cy="25" r="1.8"></circle><path class="thin" d="M71 30 Q75 33 79 30"></path><path class="thin" d="M22 46 L8 92"></path><path class="thin" d="M22 46 L36 92"></path><path class="ink-fill" d="M4 92 L40 92 Q22 112 4 92 Z" fill="#FFC2D1"></path><path class="thin" d="M128 46 L114 92"></path><path class="thin" d="M128 46 L142 92"></path><path class="ink-fill" d="M110 92 L146 92 Q128 112 110 92 Z" fill="#BDEBD2"></path></svg>',
    "calculator": '<svg width="130" height="150" viewBox="0 0 130 150"><rect class="ink-fill" x="22" y="8" width="86" height="134" rx="14" fill="#E1EEFF"></rect><rect class="ink-fill" x="34" y="20" width="62" height="38" rx="6" fill="#FFFFFF"></rect><circle class="dot" cx="54" cy="35" r="3"></circle><circle class="dot" cx="76" cy="35" r="3"></circle><path class="thin" d="M56 44 Q65 51 74 44"></path><rect class="thin-fill" x="34" y="70" width="16" height="14" rx="3" fill="#FFFFFF"></rect><rect class="thin-fill" x="57" y="70" width="16" height="14" rx="3" fill="#FFFFFF"></rect><rect class="thin-fill" x="80" y="70" width="16" height="14" rx="3" fill="#FFC2D1"></rect><rect class="thin-fill" x="34" y="93" width="16" height="14" rx="3" fill="#FFFFFF"></rect><rect class="thin-fill" x="57" y="93" width="16" height="14" rx="3" fill="#FFFFFF"></rect><rect class="thin-fill" x="80" y="93" width="16" height="14" rx="3" fill="#FFC2D1"></rect><rect class="thin-fill" x="34" y="116" width="16" height="14" rx="3" fill="#FFFFFF"></rect><rect class="thin-fill" x="57" y="116" width="16" height="14" rx="3" fill="#FFFFFF"></rect><rect class="thin-fill" x="80" y="116" width="16" height="14" rx="3" fill="#BDEBD2"></rect></svg>',
    "book": '<svg width="120" height="130" viewBox="0 0 120 130"><rect class="ink-fill" x="14" y="10" width="92" height="110" rx="8" fill="#FFFFFF"></rect><path class="ink" d="M30 10 L30 120"></path><path class="thin" d="M42 38 L94 38"></path><path class="thin" d="M42 54 L94 54"></path><path class="thin" d="M42 70 L86 70"></path><path class="thin" d="M42 86 L94 86"></path><path class="red" d="M42 103 L78 103"></path></svg>',
    "bulb": '<svg width="110" height="130" viewBox="-12 -10 58 64"><path class="ink-fill" d="M17 3 C 7 3, 3 11, 5 18 C 7 24, 11 25, 11 31 L23 31 C 23 25, 27 24, 29 18 C 31 11, 27 3, 17 3 Z" fill="#FFF4C2"></path><path class="ink" d="M12 36 L22 36"></path><path class="ink" d="M13 41 L21 41"></path><path class="red" d="M17 -6 L17 -2"></path><path class="red" d="M-6 12 L-2 13"></path><path class="red" d="M40 12 L36 13"></path></svg>',
}


def write_concept(cfg: Config, course: dict, paper: dict, date: dt.date, recent: list[str],
                  instruction: str = "", topic: str = "",
                  fit_check: Callable[[dict], list[str]] | None = None) -> dict:
    """Returns the checked concept note. `fit_check(draft)` returns problems if a slide doesn't fit.
    Raises GenerationError only if no usable note came back."""
    from . import pyq, traps
    from .generator import GenerationError, _call_claude, call_checker

    law_text = cfg.law_text(paper, date)
    writer_model = cfg.models.get("writer", "claude-sonnet-5-5")
    checker_model = cfg.models.get("checker", writer_model)
    trap_text = traps.block(course, paper)
    system = WRITER_SYSTEM.format(author=cfg.author_for(paper), traps=trap_text,
                                  law_text=law_text or "not a law paper; leave applicability empty")
    check_system = CHECKER_SYSTEM.format(course=course["name"], body=course.get("body", ""),
                                         paper=cfg.paper_prompt(paper), traps=trap_text,
                                         law_line=f"Law basis to apply: {law_text}." if law_text else "")
    recent_lines = "\n".join(f"- {t}" for t in recent[:80]) or "- none yet"
    base_user = (f"Course: {course['name']} ({course.get('body', '')})\n"
                 f"Paper: {cfg.paper_prompt(paper)}\n"
                 f"Posting date: {date.strftime('%d %B %Y')}\n\n")
    if topic:
        base_user += f"Write the note on this concept: {topic}\n"
    else:
        base_user += (f"Concepts already covered on the page, for this or another course (choose a "
                      f"different one):\n{recent_lines}\n")
    if instruction:
        base_user += f"\nReviewer's instruction for this note: {instruction}\n"
    bank = pyq.questions(course["id"], paper)
    shown = (pyq.relevant(bank, topic) if topic else bank) if bank else []
    near = pyq.relevant(bank, instruction, 30) if bank and instruction and not topic else []
    if shown:
        base_user += ("\nPast-paper questions from the question bank for this paper "
                      "(ref | papers · type | section | question extract):\n" + pyq.index_text(shown, keep=near) + "\n")
        if not topic:
            base_user += "\nSections past papers ask most:\n" + pyq.section_counts(bank) + "\n"

    def past_papers(draft: dict) -> list[str]:
        if not shown:
            draft["past_papers"] = []
            return []
        draft["past_papers"], problems = pyq.resolve(draft.get("past_papers"), shown)
        if not draft["past_papers"] and not topic:
            problems.append("past_papers is empty: cite 1-3 questions from the past-paper list that test this concept, "
                            "or choose a concept that past papers ask")
        return problems

    def for_checker(draft: dict) -> str:
        return "\n".join([plain(draft)] + pyq.source_lines(draft.get("past_papers") or [], shown))

    def attempt_round(user_base: str, attempts: int):
        feedback, last, notes, why = "", None, [], ""
        for attempt in range(1, attempts + 1):
            user = user_base + (f"\nYour previous draft was rejected:\n{feedback}\nWrite a corrected note.\n" if feedback else "")
            draft = tidy(_call_claude(writer_model, system, user, WRITE_TOOL, max_tokens=5000))
            last = draft
            problems = past_papers(draft) + validate(draft)
            if problems:
                why, feedback, notes = "format", "Format problems: " + "; ".join(problems), [f"Format: {p}" for p in problems]
                continue
            problems = fit_check(draft) if fit_check else []
            if problems:
                why, feedback, notes = "fit", "It doesn't fit the slides: " + "; ".join(problems), [f"Fit: {p}" for p in problems]
                continue
            # two independent examiners (the checker model and the writer model); both must pass it
            checks = [call_checker(cfg, check_system, for_checker(draft), CHECK_TOOL, max_tokens=2500),
                      call_checker(cfg, check_system, for_checker(draft), CHECK_TOOL, max_tokens=2500, model=writer_model)]
            notes = [f"Checker {n}: {i}" for n, c in enumerate(checks, 1) for i in c.get("issues", []) if i]
            if not any(c.get("severity") == "major" for c in checks):
                draft.update(law_sensitive=bool(law_text), attempts=attempt, serious=False,
                             needs_check=bool(draft.get("confidence") == "low" or draft.get("reviewer_note") or notes),
                             check_notes=([f"Writer: {draft['reviewer_note']}"] if draft.get("reviewer_note") else []) + notes)
                return draft, last, notes, why, feedback
            why = "check"
            feedback = "Independent examiners found these errors: " + "; ".join(
                i for c in checks if c.get("severity") == "major" for i in c.get("issues", []))
        return None, last, notes, why, feedback

    attempts = int(cfg.models.get("max_attempts", 3))
    ok, last, notes, why, feedback = attempt_round(base_user, attempts)
    if not ok and not topic and not instruction:
        # the first concept couldn't be confirmed: a fresh, core concept usually can
        retry = base_user + (f"\nA note on '{(last or {}).get('topic', 'another concept')}' could not be verified. "
                             "Choose a different, core, frequently examined concept of this paper whose rules are "
                             "settled, and keep it simple.\n")
        try:
            ok2, last2, notes2, why2, feedback2 = attempt_round(retry, 2)
        except GenerationError as exc:          # e.g. the plan's usage limit: keep the first concept's result
            print(f"  ! concept switch failed: {exc}")
            ok2 = last2 = None
        if ok2:
            ok2["check_notes"] = ["Switched to a new concept because the first one couldn't be verified"] + ok2.get("check_notes", [])
        if ok2 or last2:
            ok, last, notes, why, feedback = ok2, last2 or last, notes2, why2 or why, feedback2
    if ok:
        return ok

    if not last or why == "format":
        raise GenerationError("Claude kept returning concept notes that don't fit the format: " + feedback[:300])
    reason = ("The note stayed too long for the slides, so it wasn't checked" if why == "fit"
              else "The checkers found errors that weren't fixed")
    last.update(law_sensitive=bool(law_text), attempts=attempts, needs_check=True, serious=True,
                check_notes=[f"Not confirmed after {attempts} attempts"] + notes,
                serious_reason=reason + (f" ({notes[0][:160]})" if notes else ""))
    return last


def dump(c: dict) -> str:
    return json.dumps(c, ensure_ascii=False, indent=2)
