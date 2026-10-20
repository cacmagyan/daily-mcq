"""Known traps (traps.yaml): mistakes found before, given to the writer and the checker every time."""

from __future__ import annotations

import re

import yaml

from .config import ROOT

TRAPS_FILE = ROOT / "traps.yaml"


def load() -> list[dict]:
    if not TRAPS_FILE.exists():
        return []
    with open(TRAPS_FILE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or []
    return [t for t in data if isinstance(t, dict) and t.get("text")]


def _has(name: str, phrase: str) -> bool:
    return re.search(r"\b" + re.escape(phrase.lower()) + r"\b", name) is not None


def traps_for(course: dict, paper: dict) -> list[str]:
    """The traps whose `papers` phrases appear in the paper name ("*" matches every paper), minus `not`."""
    name = " ".join([paper.get("name", ""), paper.get("part", "") or ""]).lower()
    out = []
    for t in load():
        words = [str(w) for w in t.get("papers") or ["*"]]
        if any(_has(name, w) for w in t.get("not") or []):
            continue
        if "*" in words or any(_has(name, w) for w in words):
            out.append(" ".join(str(t["text"]).split()))
    return out


def block(course: dict, paper: dict) -> str:
    """Text to add to a prompt; empty if no trap matches."""
    items = traps_for(course, paper)
    if not items:
        return ""
    return ("\nKnown traps (mistakes found before; never repeat them):\n" +
            "\n".join(f"- {t}" for t in items) + "\n")
