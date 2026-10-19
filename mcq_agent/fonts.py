"""The three handwriting fonts of the concept notes (Permanent Marker, Patrick Hand, Caveat).

GitHub downloads them the first time a concept note is drawn and saves them in
assets/fonts/handwriting/, so later runs don't need the internet for them. Licences:
Permanent Marker (Apache 2.0), Patrick Hand and Caveat (SIL Open Font License); all allow
use and redistribution.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import requests

from .config import ROOT

FONT_DIR = ROOT / "assets" / "fonts" / "handwriting"
_GF = "https://raw.githubusercontent.com/google/fonts/main"

# file name -> (CSS family, weight, sources tried in order; "css:" = Google Fonts service)
FONTS = {
    "PermanentMarker-Regular.ttf": ("Permanent Marker", 400, [
        f"{_GF}/apache/permanentmarker/PermanentMarker-Regular.ttf", "css:Permanent+Marker"]),
    "PatrickHand-Regular.ttf": ("Patrick Hand", 400, [
        f"{_GF}/ofl/patrickhand/PatrickHand-Regular.ttf", "css:Patrick+Hand"]),
    "Caveat-Bold.ttf": ("Caveat", 700, [
        f"{_GF}/ofl/caveat/static/Caveat-Bold.ttf", "css:Caveat:wght@700"]),
}
LICENCES = {
    "PermanentMarker-LICENSE.txt": f"{_GF}/apache/permanentmarker/LICENSE.txt",
    "PatrickHand-OFL.txt": f"{_GF}/ofl/patrickhand/OFL.txt",
    "Caveat-OFL.txt": f"{_GF}/ofl/caveat/OFL.txt",
}
FAMILIES = [spec[0] for spec in FONTS.values()]

# Local test drawings only (MCQ_FONT_FALLBACK=1): stand-ins at least as wide as the real fonts,
# so a slide that fits here also fits with the real fonts. Never used on GitHub.
_FALLBACK = {
    "Permanent Marker": "local('DejaVu Sans Bold')",
    "Patrick Hand": f"url('{(ROOT / 'assets/fonts/texgyreheroscn-regular.otf').as_uri()}')",
    "Caveat": f"url('{(ROOT / 'assets/fonts/texgyreheroscn-bold.otf').as_uri()}')",
}


class FontError(RuntimeError):
    pass


def fallback_allowed() -> bool:
    return os.environ.get("MCQ_FONT_FALLBACK") == "1" and not os.environ.get("GITHUB_ACTIONS")


def _is_font(data: bytes) -> bool:
    return len(data) > 10_000 and data[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO")


def _download(src: str) -> bytes:
    if src.startswith("css:"):
        # an old browser name makes the service answer with plain TrueType files
        css = requests.get(f"https://fonts.googleapis.com/css2?family={src[4:]}",
                           headers={"User-Agent": "Mozilla/4.0"}, timeout=30)
        css.raise_for_status()
        m = re.search(r"url\((https://[^)]+)\)", css.text)
        if not m:
            raise FontError("Google Fonts answered without a font address")
        src = m.group(1)
    r = requests.get(src, timeout=60)
    r.raise_for_status()
    return r.content


def ensure_fonts() -> bool:
    """Makes sure the three font files exist. Returns False only in local fallback mode."""
    missing = [name for name in FONTS if not (FONT_DIR / name).exists()]
    if not missing:
        return True
    errors = []
    for name in missing:
        for src in FONTS[name][2]:
            try:
                data = _download(src)
            except (requests.RequestException, FontError) as exc:
                errors.append(f"{name} from {src}: {exc}")
                continue
            if _is_font(data):
                FONT_DIR.mkdir(parents=True, exist_ok=True)
                (FONT_DIR / name).write_bytes(data)
                break
            errors.append(f"{name} from {src}: not a font file")
    for name, url in LICENCES.items():
        dest = FONT_DIR / "licenses" / name
        if not dest.exists():
            try:
                r = requests.get(url, timeout=30)
                if r.ok:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(r.text, encoding="utf-8")
            except requests.RequestException:
                pass
    still = [name for name in FONTS if not (FONT_DIR / name).exists()]
    if not still:
        return True
    if fallback_allowed():
        return False
    raise FontError("Couldn't download the handwriting fonts (" + "; ".join(errors[-3:]) + "). "
                    "Concept notes are never drawn without them.")


def font_face_css(real: bool) -> str:
    rules = []
    for name, (family, weight, _) in FONTS.items():
        src = f"url('{(FONT_DIR / name).as_uri()}')" if real else _FALLBACK[family]
        rules.append(f"@font-face {{ font-family: '{family}'; src: {src}; font-weight: {weight}; "
                     f"font-style: normal; font-display: block; }}")
    return "\n".join(rules)
