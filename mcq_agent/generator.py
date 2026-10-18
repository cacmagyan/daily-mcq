"""Writes one MCQ with Claude, then has a second Claude call solve it blind to catch wrong keys."""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import time

import requests

from .config import LETTERS, Config

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

DIFFICULTY_BY_WEEKDAY = ["easy", "medium", "medium", "hard", "medium", "easy", "hard"]  # Mon..Sun

WRITE_TOOL = {
    "name": "submit_mcq",
    "description": "Submit the finished multiple-choice question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Chapter or topic, at most 40 characters"},
            "question": {"type": "string", "description": "Question stem, at most 300 characters"},
            "options": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 4,
                        "description": "Exactly four options, A to D in order"},
            "correct": {"type": "string", "enum": LETTERS},
            "explanation": {"type": "string", "description": "Why the answer is right, at most 260 characters"},
            "working": {
                "type": "array", "maxItems": 5,
                "description": "Calculation steps for numerical questions; empty for theory. Last row = final answer.",
                "items": {"type": "object",
                          "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                          "required": ["label", "value"]},
            },
            "why_not": {
                "type": "object",
                "description": "For each WRONG option letter, the student mistake it represents (at most 90 characters).",
                "properties": {l: {"type": "string"} for l in LETTERS},
            },
            "exam_tip": {"type": "string", "description": "One memorable tip, at most 140 characters"},
            "applicability": {"type": "string",
                              "description": "Law/standard basis for tax or law questions, at most 60 characters; empty otherwise"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reviewer_note": {"type": "string",
                              "description": "Anything the human reviewer should double-check; empty if nothing"},
        },
        "required": ["topic", "question", "options", "correct", "explanation", "working",
                     "why_not", "exam_tip", "applicability", "confidence", "reviewer_note"],
    },
}

CHECK_TOOL = {
    "name": "submit_check",
    "description": "Submit your independent solution and any problems found.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "enum": LETTERS, "description": "The option you believe is correct"},
            "reasoning": {"type": "string", "description": "Your short working"},
            "issues": {"type": "array", "items": {"type": "string"},
                       "description": "Problems: ambiguity, two defensible answers, wrong calculation, outdated law, "
                                      "giveaway wording. Empty if none."},
            "severity": {"type": "string", "enum": ["none", "minor", "major"]},
        },
        "required": ["answer", "reasoning", "issues", "severity"],
    },
}

WRITER_SYSTEM = """You are a senior faculty member who writes exam-standard MCQs for Indian professional accountancy students. Each MCQ is posted on Instagram as two images: the question, then the answer with explanation.

Rules
1. Write an original question in the style of {body} exam MCQs. Never copy a question from study material, RTPs, MTPs or past papers.
2. Exactly one option is correct. The other three are mistakes real students make; for each wrong option, why_not names that mistake.
3. Use Indian formats: ₹ with Indian commas (₹1,45,800), lakh and crore, dates like 31 March 2026, FY 2025-26.
4. Options are shuffled after you write them. So no option may refer to another ("All of the above", "Both (a) and (b)", "None of these"), and the explanation, working, why_not texts and exam tip must never mention option letters.
5. Numerical questions: choose friendly numbers so the answer is exact; show each step in `working` (at most 5 rows, label at most 40 characters, value at most 14 characters); the last row is the final answer.
6. Theory questions: leave `working` empty; make the options short and parallel in form.
7. Length limits are strict because the text must fit on a phone screen: question 300 characters, each option 70 (90 for theory), explanation 260, each why_not 90, exam tip 140, topic 40.
8. Law and tax: follow exactly this basis: {law_text}. Put a short form of it in `applicability` (at most 60 characters). Never invent a section number; if unsure of a number, describe the provision instead. Avoid rates and limits that changed recently unless you are certain. Put anything a reviewer should verify in `reviewer_note`.
9. Accounting standards: Ind AS / AS as currently applicable. Costing: ICMAI/ICAI study-material terminology.
10. Plain, simple Indian classroom English. No filler, no motivational lines, no emoji.
"""

CHECKER_SYSTEM = """You are a strict examiner checking an MCQ written for {course} ({body}) students, paper: {paper}.
Solve it yourself from scratch before looking for problems. Then list problems: more than one defensible answer, no correct option, calculation errors, outdated or uncertain law, ambiguous wording, or wording that gives the answer away.
Severity: "major" if a student could fairly dispute the key or the answer is wrong; "minor" for wording polish; "none" otherwise.
{law_line}"""


class GenerationError(RuntimeError):
    pass


def _call_claude(model: str, system: str, user: str, tool: dict, max_tokens: int = 2000) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise GenerationError("ANTHROPIC_API_KEY is not set. Add it as a GitHub secret or in your .env file.")
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
    }
    headers = {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"}
    for attempt in range(5):
        try:
            r = requests.post(API_URL, headers=headers, json=body, timeout=180)
        except requests.RequestException as exc:
            err = f"network error: {exc}"
        else:
            if r.status_code == 200:
                data = r.json()
                for block in data.get("content", []):
                    if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
                        return block["input"]
                if data.get("stop_reason") == "max_tokens":
                    body["max_tokens"] = int(body["max_tokens"] * 1.6)
                    continue
                raise GenerationError(f"Claude returned no {tool['name']} result: {json.dumps(data)[:300]}")
            err = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code in (400, 401, 403, 404):
                raise GenerationError(f"Claude API refused the request ({err}). Check the API key and model name in config.yaml.")
        time.sleep(min(60, 5 * 2 ** attempt))
    raise GenerationError(f"Claude API kept failing: {err}")


# ── validation and shuffling ────────────────────────────────────────────────

_CROSS_REF = re.compile(r"\b(all of the above|none of the above|none of these|both)\b|\([a-dA-D]\)|\boption [a-dA-D]\b", re.I)


def validate(mcq: dict) -> list[str]:
    problems = []
    opts = [str(o).strip() for o in mcq.get("options", [])]
    if len(opts) != 4:
        problems.append("needs exactly 4 options")
    if len({o.lower() for o in opts}) != len(opts):
        problems.append("two options are identical")
    if mcq.get("correct") not in LETTERS:
        problems.append("correct must be A, B, C or D")
    if len(mcq.get("question", "")) > 380:
        problems.append("question is too long")
    texts = {"explanation": mcq.get("explanation", ""), "exam_tip": mcq.get("exam_tip", ""),
             "why_not": " ".join((mcq.get("why_not") or {}).values())}
    for field, text in texts.items():
        if re.search(r"\b[Oo]ption\s*(\([a-dA-D]\)|[A-D]\b)", text):
            problems.append(f"{field} mentions an option letter")
    return problems


def shuffle_options(mcq: dict, rng: random.Random) -> dict:
    """Moves the correct answer to a random position. Skips MCQs whose options refer to each other."""
    if any(_CROSS_REF.search(o) for o in mcq["options"]):
        return mcq
    order = list(range(4))
    rng.shuffle(order)                      # new position i holds old option order[i]
    old_letter = {LETTERS[new]: LETTERS[old] for new, old in enumerate(order)}
    new_of_old = {v: k for k, v in old_letter.items()}
    out = dict(mcq)
    out["options"] = [mcq["options"][old] for old in order]
    out["correct"] = new_of_old[mcq["correct"]]
    out["why_not"] = {new_of_old[l]: txt for l, txt in (mcq.get("why_not") or {}).items()
                      if l in new_of_old and l != mcq["correct"]}
    return out


def tidy(mcq: dict) -> dict:
    mcq["options"] = [str(o).strip() for o in mcq["options"]]
    mcq["working"] = [w for w in (mcq.get("working") or []) if w.get("label") or w.get("value")][:5]
    mcq["why_not"] = {l: t.strip() for l, t in (mcq.get("why_not") or {}).items()
                      if l in LETTERS and l != mcq["correct"] and t and t.strip()}
    for k in ("topic", "question", "explanation", "exam_tip", "applicability", "reviewer_note"):
        mcq[k] = str(mcq.get(k) or "").strip()
    return mcq


# ── main entry ─────────────────────────────────────────────────────────────

def write_mcq(cfg: Config, course: dict, paper: dict, date: dt.date,
              recent: list[dict], instruction: str = "") -> dict:
    """Returns the MCQ plus check results. Raises GenerationError only if no usable MCQ came back."""
    law_text = cfg.law_text(paper, date)
    difficulty = DIFFICULTY_BY_WEEKDAY[date.weekday()]
    rng = random.Random(f"{date.isoformat()}:{course['id']}:{instruction}")
    writer_model = cfg.models.get("writer", "claude-sonnet-5-5")
    checker_model = cfg.models.get("checker", writer_model)

    system = WRITER_SYSTEM.format(
        body=course.get("body", ""),
        law_text=law_text or "not a law paper; leave applicability empty",
    )
    recent_lines = "\n".join(f"- {r.get('topic', '')}: {r.get('question', '')[:90]}" for r in recent[:40]) or "- none yet"
    base_user = (
        f"Course: {course['name']} ({course.get('body', '')})\n"
        f"Paper: {paper['code']}: {paper['name']}\n"
        f"Difficulty: {difficulty}\n"
        f"Posting date: {date.strftime('%d %B %Y')}\n\n"
        f"Recently posted for this course (pick a different chapter or concept):\n{recent_lines}\n"
    )
    if instruction:
        base_user += f"\nReviewer's instruction for this MCQ: {instruction}\n"

    feedback, last, notes = "", None, []
    attempts = int(cfg.models.get("max_attempts", 3))
    for attempt in range(1, attempts + 1):
        user = base_user + (f"\nYour previous draft was rejected:\n{feedback}\nWrite a new MCQ that fixes this.\n" if feedback else "")
        draft = tidy(_call_claude(writer_model, system, user, WRITE_TOOL))
        problems = validate(draft)
        if problems:
            feedback = "Format problems: " + "; ".join(problems)
            last = draft
            continue
        mcq = shuffle_options(draft, rng)

        check = _call_claude(
            checker_model,
            CHECKER_SYSTEM.format(course=course["name"], body=course.get("body", ""),
                                  paper=f"{paper['code']} {paper['name']}",
                                  law_line=f"Law basis to apply: {law_text}." if law_text else ""),
            "Question: " + mcq["question"] + "\n" +
            "\n".join(f"{l}. {o}" for l, o in zip(LETTERS, mcq["options"])),
            CHECK_TOOL, max_tokens=1500,
        )
        agrees = check.get("answer") == mcq["correct"]
        last = mcq
        notes = [f"Checker chose {check.get('answer')} (key is {mcq['correct']})"] if not agrees else []
        notes += [f"Checker: {i}" for i in check.get("issues", []) if i]
        if agrees and check.get("severity") != "major":
            mcq.update(
                difficulty=difficulty,
                law_sensitive=bool(law_text),
                needs_check=bool(mcq.get("confidence") == "low" or mcq.get("reviewer_note")),
                check_notes=([f"Writer: {mcq['reviewer_note']}"] if mcq.get("reviewer_note") else []) + notes,
                attempts=attempt,
            )
            return mcq
        feedback = (f"An independent examiner solved it and chose {check.get('answer')}, "
                    f"but your key was {mcq['correct']}. " if not agrees else "") + \
                   ("Problems found: " + "; ".join(check.get("issues", [])) if check.get("issues") else "")

    if not last:
        raise GenerationError("Claude did not return a usable MCQ")
    if last.get("correct") not in LETTERS or len(last.get("options", [])) != 4:
        raise GenerationError("Claude kept returning badly formed MCQs: " + feedback)
    last.update(difficulty=difficulty, law_sensitive=bool(law_text), needs_check=True,
                check_notes=[f"Not confirmed after {attempts} attempts"] + notes, attempts=attempts)
    return last
