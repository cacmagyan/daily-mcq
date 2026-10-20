"""Re-does the arithmetic of a numerical MCQ, so a wrong answer key can't come from a calculation slip.

Claude writes its working as a tiny program of plain assignments ending with `answer = ...`.
It is evaluated here with a locked-down evaluator: numbers, + - * / // % **, a few maths
functions and variable names only. No imports, attributes, loops or anything else.
"""

from __future__ import annotations

import ast
import math
import operator
import re

FUNCS = {
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "exp": math.exp,
    "round": round, "min": min, "max": max, "abs": abs, "ceil": math.ceil, "floor": math.floor,
}
BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
LIMIT = 1e15


class CalcError(ValueError):
    pass


def _num(v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CalcError("only numbers are allowed")
    if v != v or abs(v) > LIMIT:
        raise CalcError("a number is too large or not a number")
    return v


def _eval(node, names: dict):
    if isinstance(node, ast.Constant):
        return _num(node.value)
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise CalcError(f"'{node.id}' is used before it is given a value")
        return names[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in BINOPS:
        left, right = _eval(node.left, names), _eval(node.right, names)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise CalcError("power is too large")
        try:
            return _num(BINOPS[type(node.op)](left, right))
        except (ZeroDivisionError, OverflowError) as exc:
            raise CalcError(str(exc)) from None
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
        return _num(UNARY[type(node.op)](_eval(node.operand, names)))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS and not node.keywords:
        args = [_eval(a, names) for a in node.args]
        try:
            return _num(FUNCS[node.func.id](*args))
        except (ValueError, TypeError, OverflowError) as exc:
            raise CalcError(f"{node.func.id}: {exc}") from None
    raise CalcError(f"'{ast.dump(node)[:40]}' is not allowed; use plain arithmetic only")


def evaluate(program: str) -> float:
    """Runs `name = expression` lines and returns the value of `answer`."""
    program = (program or "").strip()
    if not program:
        raise CalcError("empty calculation")
    if len(program) > 2000:
        raise CalcError("calculation is too long")
    try:
        tree = ast.parse(program.replace(";", "\n"), mode="exec")
    except SyntaxError as exc:
        raise CalcError(f"syntax error: {exc.msg}") from None
    if len(tree.body) > 40:
        raise CalcError("too many lines")
    names: dict = {}
    for stmt in tree.body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)):
            raise CalcError("each line must be `name = expression`")
        target = stmt.targets[0].id
        if target in FUNCS:
            raise CalcError(f"'{target}' is a function name")
        names[target] = _eval(stmt.value, names)
    if "answer" not in names:
        raise CalcError("the last line must set `answer`")
    return float(names["answer"])


# ── reading the numbers in an option ─────────────────────────────────────────

_SCALE = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7,
          "thousand": 1e3, "million": 1e6}
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:\s*(lakhs?|lacs?|crores?|cr|thousand|million)\b)?", re.I)


def numbers_in(text: str) -> list[tuple[float, int]]:
    """Each number in the text with its count of decimal places: '₹1,45,800' -> (145800, 0),
    '12.5%' -> (12.5, 1), '₹2.5 lakh' -> (250000, 0). Ratios like '3:2' give both numbers."""
    out = []
    for m in _NUMBER.finditer(text or ""):
        raw = m.group(0)
        scale_word = (m.group(1) or "").lower()
        digits = raw[: m.start(1) - m.start(0)].strip() if m.group(1) else raw
        digits = digits.replace(",", "")
        try:
            value = float(digits)
        except ValueError:
            continue
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        if scale_word:
            value *= _SCALE[scale_word]
            decimals = 0
        out.append((value, decimals))
    return out


def matches(value: float, number: tuple[float, int]) -> bool:
    """True if the computed value rounds to the number as written in the option."""
    target, decimals = number
    tolerance = max(0.5 * 10 ** (-decimals) + 1e-9, 0.001 * abs(target))
    return abs(value - target) <= tolerance


_SIGN_WORDS = re.compile(r"\b(loss|losses|deficit|decrease|negative|unfavourable|unfavorable|adverse|"
                         r"overdraft|outflow|shortfall|dr|debit|reduce|reduces|reduction|less)\b|−|-\s*₹|\(₹", re.I)


def _words(text: str) -> str:
    """The option without its numbers, to tell 'Profit ₹5,000' from 'Loss ₹5,000'."""
    return re.sub(r"[^a-z]+", " ", _NUMBER.sub(" ", (text or "").lower())).strip()


def check_answer(program: str, options: list[str], correct_index: int) -> list[str]:
    """Problems with a numerical MCQ's key, found by re-doing its calculation. Empty if it agrees."""
    if not (program or "").strip():
        return []
    try:
        value = evaluate(program)
    except CalcError as exc:
        return [f"the calculation can't be run ({exc}); write plain arithmetic lines ending with answer = ..."]
    shown = f"{value:,.4f}".rstrip("0").rstrip(".")
    nums = numbers_in(options[correct_index])
    if not nums:
        return [f"the calculation gives {shown}, but the correct option has no number in it"]
    signed_in_words = bool(_SIGN_WORDS.search(options[correct_index]))   # 'Loss ₹5,000' for -5000
    if not any(matches(value, n) or (signed_in_words and matches(abs(value), (abs(n[0]), n[1]))) for n in nums):
        return [f"your own calculation gives {shown}, but the correct option says '{options[correct_index]}'; "
                "fix the calculation or the key"]
    for i, opt in enumerate(options):
        if i != correct_index:
            other = numbers_in(opt)
            same_words = _words(opt) == _words(options[correct_index])
            if len(other) == 1 and same_words and (matches(value, other[0]) or matches(abs(value), (abs(other[0][0]), other[0][1]))):
                return [f"option '{opt}' also equals the calculated answer {shown}; each wrong option must differ"]
    return []
