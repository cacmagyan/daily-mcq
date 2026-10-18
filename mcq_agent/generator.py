"""Writes one MCQ with Claude, then has a second Claude call solve it blind to catch wrong keys."""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

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
                "type": "array", "maxItems": 6,
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
5. Numerical questions: choose friendly numbers so the answer is exact; show each step in `working` (at most 6 rows, label at most 40 characters, value at most 14 characters and holding one figure only, never a calculation); the last row is the final answer on its own.
6. Theory questions: leave `working` empty; make the options short and parallel in form.
7. Length limits are strict because the text must fit on a phone screen: question 300 characters, each option 70 (90 for theory), explanation 260, each why_not 90, exam tip 140, topic 40.
8. Law and tax: follow exactly this basis: {law_text}. Put a short form of it in `applicability` (at most 60 characters). Never invent a section number; if unsure of a number, describe the provision instead. Avoid rates and limits that changed recently unless you are certain. Put anything a reviewer should verify in `reviewer_note`.
9. Accounting standards: Ind AS / AS as currently applicable. Costing: ICMAI/ICAI study-material terminology.
10. Plain, simple Indian classroom English. No filler, no motivational lines, no emoji.
"""

CHECKER_SYSTEM = """You are a strict examiner checking an MCQ written for {course} ({body}) students, paper: {paper}.
Solve it yourself from scratch before looking for problems. Then list problems: more than one defensible answer, no correct option, calculation errors, outdated or uncertain law, ambiguous wording, or wording that gives the answer away.
Severity: "major" if the key is wrong, if a needed fact is missing, or if any reasonable reading of the wording gives a different answer (for example, "interest" that could be charged or credited); "minor" for wording polish only; "none" otherwise.
{law_line}"""


class GenerationError(RuntimeError):
    pass


def auth_mode() -> str:
    """Which way Claude is reached: your Claude subscription (Claude Code token) or a paid API key."""
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return "subscription"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api_key"
    return "none"


def _call_claude(model: str, system: str, user: str, tool: dict, max_tokens: int = 2000) -> dict:
    """Asks Claude for one structured answer. Uses the subscription token first, the API key as backup."""
    mode = auth_mode()
    if mode == "none":
        raise GenerationError("No Claude login found. Add the CLAUDE_CODE_OAUTH_TOKEN secret (your Claude "
                              "subscription) or the ANTHROPIC_API_KEY secret (paid API).")
    if mode == "subscription":
        try:
            return _call_claude_code(model, system, user, tool)
        except GenerationError as exc:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise
            print(f"  ! Claude subscription call failed ({exc}); using the API key instead")
    return _call_api(model, system, user, tool, max_tokens)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        out = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return out if isinstance(out, dict) else None


def _call_claude_code(model: str, system: str, user: str, tool: dict) -> dict:
    """Runs Claude Code in print mode with the subscription token (CLAUDE_CODE_OAUTH_TOKEN)."""
    exe = shutil.which("claude")
    if not exe:
        raise GenerationError("Claude Code isn't installed on this machine (needed for the subscription token).")
    schema = tool["input_schema"]
    required = schema.get("required", [])
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # an API key would take precedence
    # a token copied from a narrow Terminal window can carry a line break; tokens never contain whitespace
    env["CLAUDE_CODE_OAUTH_TOKEN"] = "".join(env.get("CLAUDE_CODE_OAUTH_TOKEN", "").split())
    err = "no response"
    with tempfile.TemporaryDirectory() as tmp:                                   # empty folder: nothing to read
        sys_file = Path(tmp) / "system.txt"
        sys_file.write_text(system + "\n\nAnswer only with the structured output. Don't use files, the shell "
                            "or the web.", encoding="utf-8")
        cmd = [exe, "-p", "--output-format", "json", "--model", model,
               "--system-prompt-file", str(sys_file), "--json-schema", json.dumps(schema),
               "--max-turns", "6", "--no-session-persistence",
               # no built-in or connector tools: keeps each call ~3k tokens instead of ~40k
               "--tools", "", "--disallowedTools", "mcp__*"]
        for attempt in range(3):
            try:
                r = subprocess.run(cmd, input=user, capture_output=True, text=True, cwd=tmp, env=env, timeout=480)
            except subprocess.TimeoutExpired:
                err = "timed out"
                continue
            data = None
            try:
                data = json.loads(r.stdout)
            except ValueError:
                pass
            if isinstance(data, list):                                           # some versions print every message
                data = next((m for m in reversed(data) if isinstance(m, dict) and m.get("type") == "result"), None)
            if isinstance(data, dict):
                out = data.get("structured_output")
                if not isinstance(out, dict):
                    out = _extract_json(str(data.get("result") or ""))
                if isinstance(out, dict) and all(k in out for k in required):
                    return out
                err = f"{data.get('subtype', 'error')}: {str(data.get('result') or '')[:200]}"
            else:
                err = (r.stderr or r.stdout or f"exit code {r.returncode}").strip()[-300:]
            low = err.lower()
            if any(w in low for w in ("invalid bearer", "authentication", "unauthorized", "401", "oauth")):
                raise GenerationError(f"The Claude subscription token was refused: {err}")
            time.sleep(20 * (attempt + 1) if ("limit" in low or "overloaded" in low) else 5)
    raise GenerationError(f"Claude Code didn't return a usable answer: {err}")


def _call_api(model: str, system: str, user: str, tool: dict, max_tokens: int = 2000) -> dict:
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
    for w in mcq.get("working") or []:
        if len(str(w.get("value", ""))) > 18 or "=" in str(w.get("value", "")):
            problems.append(f"working value '{w.get('value')}' must be one short figure; put the step in the label")
        if len(str(w.get("label", ""))) > 52:
            problems.append(f"working label '{w.get('label')}' is too long")
    texts = {"explanation": mcq.get("explanation", ""), "exam_tip": mcq.get("exam_tip", ""),
             "why_not": " ".join((mcq.get("why_not") or {}).values())}
    for field, text in texts.items():
        if re.search(r"\b[Oo]ption\s*(\([a-dA-D]\)|[A-D]\b)", text):
            problems.append(f"{field} mentions an option letter")
    return problems


def answer_letters(course_ids: list[str], date: dt.date) -> dict:
    """Spreads a day's answer keys over A-D: every letter used, none more than twice."""
    rng = random.Random(f"keys:{date.isoformat()}")
    letters = (LETTERS * ((len(course_ids) + 3) // 4))[:len(course_ids)]
    rng.shuffle(letters)
    return dict(zip(course_ids, letters))


def shuffle_options(mcq: dict, rng: random.Random, target: str | None = None) -> dict:
    """Moves the correct answer to `target` (or a random position) and shuffles the rest.
    Skips MCQs whose options refer to each other."""
    if any(_CROSS_REF.search(o) for o in mcq["options"]):
        return mcq
    old_correct = LETTERS.index(mcq["correct"])
    others = [i for i in range(4) if i != old_correct]
    rng.shuffle(others)
    pos = LETTERS.index(target) if target in LETTERS else rng.randrange(4)
    order = others[:pos] + [old_correct] + others[pos:]   # new position i holds old option order[i]
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
    mcq["working"] = [w for w in (mcq.get("working") or []) if w.get("label") or w.get("value")][:6]
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
    target = answer_letters(cfg.course_ids(), date).get(course["id"])
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
        mcq = shuffle_options(draft, rng, target)

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
                needs_check=bool(mcq.get("confidence") == "low" or mcq.get("reviewer_note") or notes),
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
