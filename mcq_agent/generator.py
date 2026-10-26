"""Writes one MCQ with Claude, re-does its arithmetic in code, and has a separate Claude call solve it
blind to catch wrong keys. Tax and law MCQs are solved by two different checkers."""

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
            "calculation": {"type": "string",
                            "description": "Numerical questions whose answer is one number: plain arithmetic that "
                                           "computes it from the question's data, one `name = expression` per "
                                           "line, last line `answer = ...` in the unit of the correct option "
                                           "(rupees, units, %, years). Only numbers, + - * / ** and sqrt, round, "
                                           "min, max, abs. Empty for theory questions or ratio answers."},
            "applicability": {"type": "string",
                              "description": "Law/standard basis for tax or law questions, at most 60 characters; empty otherwise"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reviewer_note": {"type": "string",
                              "description": "Anything the human reviewer should double-check; empty if nothing"},
        },
        "required": ["topic", "question", "options", "correct", "explanation", "working",
                     "why_not", "exam_tip", "calculation", "applicability", "confidence", "reviewer_note"],
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
5. Numerical questions: choose friendly numbers so the answer is exact; show each step in `working` (at most 6 rows, label at most 40 characters, value at most 14 characters and holding one figure only, never a calculation); the last row is the final answer on its own. Also fill `calculation`: the agent runs it, and the correct option must equal its result, so compute from the question's own data only.
6. Theory questions: leave `working` empty; make the options short and parallel in form.
7. Length limits are strict because the text must fit on a phone screen: question 300 characters, each option 70 (90 for theory), explanation 260, each why_not 90, exam tip 140, topic 40.
8. Law and tax: follow exactly this basis: {law_text}. Put a short form of it in `applicability` (at most 60 characters). Never invent a section number; if unsure of a number, describe the provision instead. Prefer concepts and treatments that stay the same from year to year; don't build a question on a rate, threshold, limit or due date unless the question states it or you are certain of it. Put anything a reviewer should verify in `reviewer_note`.
9. Accounting standards: Ind AS / AS as currently applicable. Costing: ICMAI/ICAI study-material terminology.
10. Plain, simple Indian classroom English. No filler, no motivational lines, no emoji.
{traps}"""

CHECKER_SYSTEM = """You are a strict examiner checking an MCQ written for {course} ({body}) students, paper: {paper}.
Solve it yourself from scratch before looking for problems. Then list problems: more than one defensible answer, no correct option, calculation errors, outdated or uncertain law, ambiguous wording, or wording that gives the answer away.
Severity: "major" if the key is wrong, if a needed fact is missing, or if any reasonable reading of the wording gives a different answer (for example, "interest" that could be charged or credited); "minor" for wording polish only; "none" otherwise.
{law_line}{traps}"""


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
                if isinstance(out, dict):
                    for k in required:          # a text field left out means "nothing to say"
                        if k not in out and schema.get("properties", {}).get(k, {}).get("type") == "string":
                            out[k] = ""
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


_checker_unavailable: set[str] = set()


def call_checker(cfg: Config, system: str, user: str, tool: dict, max_tokens: int = 1500,
                 model: str | None = None) -> dict:
    """Runs a check with the checker model; if that model can't be used, falls back to the writer model."""
    writer = cfg.models.get("writer", "claude-sonnet-5-5")
    model = model or cfg.models.get("checker", writer)
    if model != writer and model not in _checker_unavailable:
        try:
            return _call_claude(model, system, user, tool, max_tokens=max_tokens)
        except GenerationError as exc:
            if "token was refused" in str(exc):
                raise
            _checker_unavailable.add(model)
            print(f"  ! checker model {model} not available ({str(exc)[:120]}); using {writer} for checks")
    return _call_claude(writer, system, user, tool, max_tokens=max_tokens)


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
    if not problems and mcq.get("calculation") and mcq.get("correct") in LETTERS:
        from .safecalc import check_answer
        problems += check_answer(mcq["calculation"], opts, LETTERS.index(mcq["correct"]))
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
    for k in ("topic", "question", "explanation", "exam_tip", "calculation", "applicability", "reviewer_note"):
        mcq[k] = str(mcq.get(k) or "").strip()
    return mcq


# ── main entry ─────────────────────────────────────────────────────────────

def _solve(cfg: Config, course: dict, paper: dict, law_text: str, mcq: dict, model: str | None = None) -> dict:
    from . import traps
    return call_checker(
        cfg,
        CHECKER_SYSTEM.format(course=course["name"], body=course.get("body", ""), paper=cfg.paper_prompt(paper),
                              law_line=f"Law basis to apply: {law_text}." if law_text else "",
                              traps=traps.block(course, paper)),
        "Question: " + mcq["question"] + "\n" + "\n".join(f"{l}. {o}" for l, o in zip(LETTERS, mcq["options"])),
        CHECK_TOOL, max_tokens=1500, model=model)


def checker_for(cfg: Config, paper: dict, law_text: str) -> str | None:
    """The model that solves an MCQ blind. models.strong_checks: "law_tax_audit" keeps the strong checker
    for tax, law, audit and SM papers (where wording traps hide) and uses the writer model for the rest,
    whose arithmetic is re-done by code anyway; this roughly halves the Claude usage. None = the checker."""
    if str(cfg.models.get("strong_checks", "all")) != "law_tax_audit":
        return None
    if law_text or paper.get("law") or paper.get("author"):
        return None
    return cfg.models.get("writer", "claude-sonnet-5-5")


def _round(cfg: Config, course: dict, paper: dict, date: dt.date, system: str, base_user: str,
           attempts: int, rng: random.Random, target: str | None, law_text: str):
    """Up to `attempts` drafts. Returns (accepted MCQ or None, last draft, notes, feedback)."""
    writer_model = cfg.models.get("writer", "claude-sonnet-5-5")
    feedback, last, notes = "", None, []
    for attempt in range(1, attempts + 1):
        user = base_user + (f"\nYour previous draft was rejected:\n{feedback}\nWrite a new MCQ that fixes this.\n" if feedback else "")
        draft = tidy(_call_claude(writer_model, system, user, WRITE_TOOL))
        problems = validate(draft)
        if problems:
            feedback = "Problems: " + "; ".join(problems)
            last, notes = draft, [f"Format/calculation: {p}" for p in problems]
            continue
        mcq = shuffle_options(draft, rng, target)
        last = mcq
        checks = [_solve(cfg, course, paper, law_text, mcq, model=checker_for(cfg, paper, law_text))]
        if law_text:   # tax and law: a second, different solver must agree too
            checks.append(_solve(cfg, course, paper, law_text, mcq, model=writer_model))
        notes, wrong = [], []
        for n, check in enumerate(checks, 1):
            who = "Checker" if n == 1 else "Second checker"
            if check.get("answer") != mcq["correct"]:
                wrong.append(check.get("answer"))
                notes.append(f"{who} chose {check.get('answer')} (key is {mcq['correct']})")
            notes += [f"{who}: {i}" for i in check.get("issues", []) if i]
        major = any(c.get("severity") == "major" for c in checks)
        if not wrong and not major:
            mcq.update(attempts=attempt, check_notes=([f"Writer: {mcq['reviewer_note']}"] if mcq.get("reviewer_note") else []) + notes)
            return mcq, last, notes, feedback
        issues = [i for c in checks for i in c.get("issues", []) if i]
        feedback = (f"An independent examiner solved it and chose {', '.join(wrong)}, but your key was "
                    f"{mcq['correct']}. " if wrong else "") + ("Problems found: " + "; ".join(issues) if issues else "")
    return None, last, notes, feedback


def write_mcq(cfg: Config, course: dict, paper: dict, date: dt.date,
              recent: list[dict], instruction: str = "", link: dict | None = None) -> dict:
    """Returns the MCQ plus check results. If the first topic can't be confirmed, tries a fresh topic
    before giving up; only then is the MCQ marked serious (held). Raises GenerationError only if no
    usable MCQ came back."""
    from . import traps

    law_text = cfg.law_text(paper, date)
    difficulty = DIFFICULTY_BY_WEEKDAY[date.weekday()]
    rng = random.Random(f"{date.isoformat()}:{course['id']}:{instruction}")
    target = answer_letters(cfg.course_ids(), date).get(course["id"])
    system = WRITER_SYSTEM.format(body=course.get("body", ""),
                                  law_text=law_text or "not a law paper; leave applicability empty",
                                  traps=traps.block(course, paper))
    recent_lines = "\n".join(f"- {r.get('topic', '')}: {r.get('question', '')[:90]}" for r in recent[:40]) or "- none yet"
    base_user = (
        f"Course: {course['name']} ({course.get('body', '')})\n"
        f"Paper: {cfg.paper_prompt(paper)}\n"
        f"Difficulty: {difficulty}\n"
        f"Posting date: {date.strftime('%d %B %Y')}\n\n"
        f"Recently posted for this course (pick a different chapter or concept):\n{recent_lines}\n"
    )
    first_user = base_user
    if instruction:
        first_user += f"\nReviewer's instruction for this MCQ: {instruction}\n"
    elif link:
        points = "; ".join(p.replace("==", "").replace("!!", "") for p in link.get("key_points", [])[:4])
        first_user += (f"\nYesterday's concept note for this course was on: {link['topic']}. "
                       f"Key points: {points}. Write today's MCQ to test that concept (this overrides the "
                       "'different chapter' rule). Test understanding with a fresh situation; don't reuse the "
                       "note's wording.\n")

    attempts = int(cfg.models.get("max_attempts", 3))
    ok, last, notes, feedback = _round(cfg, course, paper, date, system, first_user, attempts, rng, target, law_text)
    switched = False
    if not ok and not instruction:
        # the first topic couldn't be confirmed: a fresh, core topic usually can
        retry_user = base_user + (f"\nA draft on '{(last or {}).get('topic', 'another topic')}' could not be verified. "
                                  "Choose a different, core, frequently examined topic of this paper whose answer is "
                                  "settled and unambiguous, and keep it simple.\n")
        try:
            ok2, last2, notes2, feedback2 = _round(cfg, course, paper, date, system, retry_user, 2, rng, target, law_text)
        except GenerationError as exc:          # e.g. the plan's usage limit: keep the first topic's result
            print(f"  ! topic switch failed: {exc}")
            ok2 = last2 = None
        if ok2 or last2:
            ok, last, notes, feedback, switched = ok2, last2 or last, notes2, feedback2, True
    if ok:
        ok.update(difficulty=difficulty, law_sensitive=bool(law_text), serious=False,
                  needs_check=bool(ok.get("confidence") == "low" or ok.get("reviewer_note") or ok.get("check_notes")))
        if switched:
            ok["check_notes"] = ["Switched to a new topic because the first one couldn't be verified"] + ok.get("check_notes", [])
            if link:
                ok["linked_concept_missed"] = link.get("topic", "")
        return ok

    if not last:
        raise GenerationError("Claude did not return a usable MCQ")
    if last.get("correct") not in LETTERS or len(last.get("options", [])) != 4:
        raise GenerationError("Claude kept returning badly formed MCQs: " + feedback)
    last.update(difficulty=difficulty, law_sensitive=bool(law_text), needs_check=True,
                check_notes=["Not confirmed, even after switching topic"] + notes, attempts=attempts,
                serious=True,
                serious_reason="The checker could not confirm the answer key" + (f" ({notes[0]})" if notes else ""))
    return last
