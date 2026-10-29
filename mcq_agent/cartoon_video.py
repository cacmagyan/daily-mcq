"""Turns an explainer script (scenes with a voice line each) into a 1080 x 1920 reel: the free Kokoro
voice reads each line, the spoken word appears big at the top one word at a time, the scene pictures
pop in (props appear when their word is spoken), the elephant bobs and blinks, a soft plucked tune
plays under the voice, and the result is encoded for Instagram.
"""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

from . import cartoon_scenes as S
from .config import ROOT

W, H, FPS = 1080, 1920, 30
SR = 24000
CAPTION_Y = 520
FONTS = ROOT / "assets" / "fonts"
CAPTION_FONT = FONTS / "Poppins-ExtraBold.ttf"
TAG_FONT = FONTS / "Poppins-SemiBold.ttf"
LEAD, GAP, TAIL = 0.35, 0.22, 1.4      # seconds before the first line, between lines, after the last


class EngineError(RuntimeError):
    pass


# ── voice lines and caption words ───────────────────────────
TOKEN = re.compile(r"\{([^|}]+)\|([^}]+)\}|(\S+)")
_ACRONYM = re.compile(r"^([A-Z]{2,5})(s?)([,.!?:;]*)$")
_KEEP_CAPS = {"OR", "VS", "TRUE", "FALSE", "AND", "NOT", "NO", "YES", "OK", "NOTES", "NOTE", "SAVE", "FREE",
              "NOW", "NEW", "WAIT", "STOP", "WOW", "TIP", "TIPS", "LIKE", "SHARE", "FOLLOW"}
# letter names as phonemes, so NPV is said "en pee vee" (espeak alone may read it as a word)
_LETTERS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                    ["eɪ", "biː", "siː", "diː", "iː", "ɛf", "dʒiː", "eɪtʃ", "aɪ", "dʒeɪ", "keɪ", "ɛl", "ɛm", "ɛn",
                     "oʊ", "piː", "kjuː", "ɑːɹ", "ɛs", "tiː", "juː", "viː", "dˈʌbəljuː", "ɛks", "waɪ", "ziː"]))


def _speak_token(w: str) -> list[str]:
    """How the voice says one written token (amounts, % and acronyms spelt out)."""
    from .tts import speakable

    m = _ACRONYM.match(w)
    if m and m.group(1) not in _KEEP_CAPS:
        letters = [_LETTERS[c] for c in m.group(1)]
        ipa = "".join("ˌ" + x for x in letters[:-1]) + "ˈ" + letters[-1].replace("ˈ", "") + ("z" if m.group(2) else "")
        return [f"[[{ipa}]]{m.group(3)}"]
    if re.search(r"[\d₹%=÷×^/+]", w):
        tail = re.search(r"[,.!?:;]*$", w).group(0)
        core = w[: len(w) - len(tail)] if tail else w
        spoken = speakable(speakable(core)).split()
        return (spoken[:-1] + [spoken[-1] + tail]) if spoken else [w]
    return [w]


def tokens(say: str) -> list[tuple[str, list[str]]]:
    """[(caption word, [spoken words])] for 'Invest {₹1,000|one thousand rupees} at 10% a year.'"""
    say = say.replace("==", "").replace("!!", "")
    out = []
    for m in TOKEN.finditer(say):
        if m.group(1):
            out.append((m.group(1), m.group(2).split()))
            continue
        w = m.group(3)
        if out and re.fullmatch(r"[,.!?:;]+", w):          # punctuation after a {shown|spoken} group
            shown_w, spoken = out[-1]
            out[-1] = (shown_w + w, spoken[:-1] + [spoken[-1] + w])
            continue
        out.append((w, _speak_token(w)))
    return out


def spoken_text(say: str) -> str:
    return " ".join(w for _, sp in tokens(say) for w in sp)


def shown(word: str) -> str:
    return re.sub(r"[,.:;\"“”]+$", "", re.sub(r"^[\"“”]+", "", word.strip()))


def _weight(word: str, lang: str = "en-us") -> float:
    from .kokoro import phonemize

    if "[[" in word:
        ph = re.sub(r"[\[\],.!?:;]", "", word)
    elif lang.startswith("en"):
        ph = phonemize(re.sub(r"[^\w'’-]", " ", word)) or "x"
    else:                                     # e.g. Hindi: keep the vowel signs, drop punctuation only
        ph = phonemize(re.sub(r"[,.!?:;\"“”()।]", " ", word), lang) or "x"
    vowels = sum(1 for c in ph if c in "aeiouæɑɒɔəɛɜɪʊʌɐᵻɚ")
    return max(0.5, len(ph.replace("ˈ", "").replace("ˌ", "")) + 0.8 * vowels)


def _energy(a, win=240):
    import numpy as np
    return np.sqrt(np.convolve(a * a, np.ones(win) / win, mode="same"))


def voiced_span(a, thr=0.012) -> tuple[int, int]:
    import numpy as np
    idx = np.where(_energy(a) > thr)[0]
    return (int(idx[0]), int(idx[-1])) if len(idx) else (0, len(a))


def _pauses(a, lo, hi, thr=0.01, min_len=0.09):
    quiet = _energy(a)[lo:hi] < thr
    out, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if i - start >= min_len * SR:
                out.append((lo + start, lo + i))
            start = None
    return out


def word_times(say: str, audio, lang: str = "en-us") -> list[tuple[str, float, float]]:
    """(caption word, start, end) in seconds inside one voice clip: shared out by phoneme length,
    anchored at the pauses the punctuation makes."""
    toks = tokens(say)
    lo, hi = voiced_span(audio)
    groups, cur = [], []
    for k, (shown_w, spoken) in enumerate(toks):
        cur.append((shown_w, spoken))
        if re.search(r"[,.!?:;]$", spoken[-1]) and k < len(toks) - 1:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    weights = [[sum(_weight(w, lang) for w in sp) for _, sp in grp] for grp in groups]
    total = sum(sum(w) for w in weights) or 1
    gaps = _pauses(audio, lo, hi)
    # each punctuation break is matched to the pause nearest to where the words say it should be
    bounds, cum, prev = [lo], 0.0, lo
    for k in range(len(groups) - 1):
        cum += sum(weights[k])
        expected = lo + (hi - lo) * cum / total
        near = [g for g in gaps if g[0] > prev and abs((g[0] + g[1]) / 2 - expected) < 0.22 * (hi - lo)]
        if near:
            g = min(near, key=lambda g: abs((g[0] + g[1]) / 2 - expected))
            gaps.remove(g)
            bounds += [g[0], g[1]]
            prev = g[1]
        else:
            e = max(prev, int(expected))
            bounds += [e, e]
            prev = e
    bounds.append(hi)
    spans = [(bounds[2 * i], bounds[2 * i + 1]) for i in range(len(groups))]
    out = []
    for grp, ws, (a0, a1) in zip(groups, weights, spans):
        tot, t = sum(ws) or 1, a0
        for (shown_w, _), wgt in zip(grp, ws):
            d = (a1 - a0) * wgt / tot
            out.append((shown(shown_w), t / SR, (t + d) / SR))
            t += d
    return [w for w in out if re.search(r"[\w₹%]", w[0])]        # no caption for a lone dash


# ── pictures ────────────────────────────────────────────────
def _font_css() -> str:
    faces = []
    for weight, name in ((600, "SemiBold"), (700, "Bold"), (800, "ExtraBold")):
        faces.append(f"@font-face{{font-family:'Poppins';font-weight:{weight};"
                     f"src:url('{(FONTS / f'Poppins-{name}.ttf').as_uri()}')}}")
    if (FONTS / "Caveat.ttf").exists():
        faces.append(f"@font-face{{font-family:'Caveat';font-weight:400 700;src:url('{(FONTS / 'Caveat.ttf').as_uri()}')}}")
    return "".join(faces)


class Painter:
    """Draws SVG pictures with Chromium. The page is opened from a file so that it may load the font files
    in assets/fonts (a page made with set_content can't read files and would quietly use other fonts)."""

    def __init__(self, work: Path, width: int = W, height: int = H):
        self.work, self.w, self.h = work, width, height

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        page_file = self.work / "painter.html"
        page_file.write_text("<html><head><meta charset='utf-8'><style>" + _font_css()
                             + "html,body{margin:0;background:transparent}</style></head><body><div id='c'></div>"
                             "</body></html>", encoding="utf-8")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self.page = self._browser.new_page(viewport={"width": self.w, "height": self.h})
        self.page.goto(page_file.as_uri(), wait_until="load")
        return self

    def draw(self, svg_body: str, path: Path):
        """The picture as a transparent RGBA image (also saved at `path`)."""
        from PIL import Image

        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
               f'viewBox="0 0 {self.w} {self.h}">{svg_body}</svg>')
        self.page.evaluate("s => { document.getElementById('c').innerHTML = s; return document.fonts.ready.then(() => 1); }", svg)
        self.page.screenshot(path=str(path), omit_background=True)
        return Image.open(path).convert("RGBA")

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()


def render_layers(all_layers: list[list[dict]], work: Path) -> None:
    """Draws every layer once (and its blink copy) as a transparent picture, cropped to its content."""
    with Painter(work) as painter:
        for si, layers in enumerate(all_layers):
            for li, lay in enumerate(layers):
                path = work / f"s{si:02d}_{li}.png"
                im = painter.draw(lay["svg"], path)
                box = im.getbbox() or (0, 0, 1, 1)
                lay["img"], lay["off"] = im.crop(box), box[:2]
                if lay.get("alt"):
                    lay["alt_img"] = painter.draw(lay["alt"], path).crop(box)


def background(tag: str, tag_color: str = "#1F2D52"):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * 0.52) / H) ** 2)
    k = np.clip(1 - d * 1.9, 0, 1)[..., None]
    arr = np.array([241, 228, 208], float) * (1 - k) + np.array([250, 243, 231], float) * k
    img = Image.fromarray(arr.astype(np.uint8))
    dr = ImageDraw.Draw(img, "RGBA")
    for x in range(0, W, 54):                       # faint notebook grid
        dr.line([(x, 0), (x, H)], fill=(120, 150, 190, 16), width=2)
    for y in range(0, H, 54):
        dr.line([(0, y), (W, y)], fill=(120, 150, 190, 16), width=2)
    if tag:
        f = ImageFont.truetype(str(TAG_FONT), 34)
        tw = dr.textlength(tag, font=f)
        x0, y0 = (W - tw) / 2 - 30, 270
        rgb = tuple(int(tag_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        dr.rounded_rectangle([x0, y0, x0 + tw + 60, y0 + 64], radius=32, fill=rgb + (240,))
        dr.text((W / 2, y0 + 32), tag, font=f, fill=(255, 255, 255), anchor="mm")
    return img


def caption_img(word: str):
    """The spoken word in big yellow letters with a dark outline; 'x^n' raises n."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    if "^" in word:
        base, sup = word.split("^", 1)
        a, b = caption_img(base), caption_img(sup)
        b = b.resize((int(b.width * 0.62), int(b.height * 0.62)), Image.LANCZOS)
        out = Image.new("RGBA", (a.width + b.width - 50, a.height), (0, 0, 0, 0))
        out.alpha_composite(a, (0, 0))
        out.alpha_composite(b, (a.width - 62, 0))
        return out
    size = 104 if len(word) <= 9 else max(60, int(104 * 9 / len(word)))
    f = ImageFont.truetype(str(CAPTION_FONT), size)
    pad = 40
    l, t, r, b = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), word, font=f, stroke_width=12)
    w, h = r - l + 2 * pad, b - t + 2 * pad
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((pad - l, pad - t + 8), word, font=f, fill=(20, 24, 40, 150), stroke_width=12,
                            stroke_fill=(20, 24, 40, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    d = ImageDraw.Draw(img)
    d.text((pad - l, pad - t), word, font=f, fill="#1B2238", stroke_width=12, stroke_fill="#1B2238")
    d.text((pad - l, pad - t), word, font=f, fill="#FFC81E")
    return img


# ── motion ──────────────────────────────────────────────────
def _ease_back(x):
    return 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2


def layer_state(lay, t):
    """(scale, alpha, dx, dy) of a layer t seconds after its scene starts, or None before it appears."""
    t -= lay["delay"]
    if t < 0:
        return None
    s, a, dx, dy = 1.0, 1.0, 0.0, 0.0
    anim = lay["anim"]
    if anim == "pop":
        s, a = 0.86 + 0.14 * _ease_back(min(1, t / 0.32)), min(1, t / 0.14)
    elif anim == "fade":
        a = min(1, t / 0.3)
    elif anim == "drop":
        dy, a = -90 * (1 - _ease_back(min(1, t / 0.4))), min(1, t / 0.15)
    elif anim == "stamp":
        s, a = 1.7 - 0.7 * min(1, t / 0.18), min(1, t / 0.08)
    if lay["bob"]:
        dy += math.sin(2 * math.pi * t / 1.8) * 5
    ddx, ddy = lay["drift"]
    if ddx or ddy:
        k = min(1, t / 3.0)
        dx, dy = dx + ddx * k, dy + ddy * k
    return s, a, dx, dy


def _blinking(t: float) -> bool:
    return t > 1.6 and ((t - 1.6) % 3.2) < 0.13


def _paste(frame, lay, st, fade=1.0, t=None):
    from PIL import Image

    s, a, dx, dy = st
    a *= fade
    if a <= 0.01:
        return
    im, (ox, oy) = lay["img"], lay["off"]
    if t is not None and lay.get("alt_img") is not None and _blinking(t - lay["delay"]):
        im = lay["alt_img"]
    w, h = im.size
    cx, cy = ox + w / 2, oy + h / 2
    if abs(s - 1) > 0.003:
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)
    if a < 0.995:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    frame.alpha_composite(im, (int(round(cx + (ox - cx) * s + dx)), int(round(cy + (oy - cy) * s + dy))))


# ── sound ───────────────────────────────────────────────────
def _pluck(freq, dur, seed):
    import numpy as np

    n = int(SR / freq)
    buf = np.random.default_rng(seed).uniform(-1, 1, n)
    out = np.empty(int(dur * SR))
    for i in range(len(out)):                    # Karplus-Strong plucked string
        out[i] = buf[i % n]
        buf[i % n] = 0.498 * (buf[i % n] + buf[(i + 1) % n])
    return out


def music(total: float):
    """A quiet plucked arpeggio (C G Am F) that loops under the voice."""
    import numpy as np

    step = 60 / 96 / 2
    chords = [[60, 64, 67, 72], [55, 62, 67, 71], [57, 60, 64, 69], [53, 60, 65, 69]]
    pattern = [0, 1, 2, 3, 2, 1, 2, 1]
    out = np.zeros(int((total + 2) * SR))
    cache, t, i = {}, 0.0, 0
    env = np.exp(-np.linspace(0, 5, int(1.2 * SR)))
    while t < total:
        bar = int(t / (step * 8)) % 4
        note = chords[bar][pattern[i % 8]]
        if note not in cache:
            cache[note] = _pluck(440 * 2 ** ((note - 69) / 12), 1.2, note) * env
        s = int(t * SR)
        seg = cache[note][: len(out) - s]
        out[s: s + len(seg)] += seg * (0.9 if i % 8 == 0 else 0.6)
        if i % 8 == 0:
            tt = np.arange(int(1.6 * SR)) / SR
            bass = np.sin(2 * np.pi * 440 * 2 ** ((chords[bar][0] - 81) / 12) * tt) * np.exp(-tt * 2.2)
            seg = bass[: len(out) - s]
            out[s: s + len(seg)] += seg * 0.5
        t += step
        i += 1
    out = out[: int(total * SR)]
    return out / (abs(out).max() + 1e-9)


def _pop():
    import numpy as np

    tt = np.arange(int(0.09 * SR)) / SR
    return np.sin(2 * np.pi * np.cumsum(900 * np.exp(-tt * 18) + 260) / SR) * np.exp(-tt * 40) * 0.5


# ── the whole reel ──────────────────────────────────────────
def render(script: dict, out: Path, cover: Path, voice: str = "af_heart", speed: float = 1.05,
           tag: str = "", handle: str = "", logo: Path | None = None, with_music: bool = True,
           crf: int = 28, lang: str = "en-us", cta: str = "") -> dict:
    """Makes the reel at `out` and its cover picture at `cover`. Returns timings and the words shown."""
    import numpy as np

    from .kokoro import Voice, save_wav
    from .video import ffmpeg_path

    scenes = script["scenes"]
    n = 0
    for sc in scenes:                              # number the mistakes in order
        if sc.get("template") == "mistake":
            n += 1
            sc["n"] = n
    v = Voice()
    clips = []
    for sc in scenes:
        a = v.synth(spoken_text(sc["say"]), voice, speed, lang)
        lo, hi = voiced_span(a)
        a = a[max(0, lo - int(0.03 * SR)): hi + int(0.06 * SR)]
        clips.append({"audio": a, "words": word_times(sc["say"], a, lang)})
    starts, t = [], LEAD
    for c in clips:
        starts.append(t)
        t += len(c["audio"]) / SR + GAP
    total = t - GAP + TAIL
    scene_start = [0.0] + [max(0.0, s - 0.12) for s in starts[1:]]
    scene_end = scene_start[1:] + [total]

    # sound: voice, a soft pop at each new picture, the tune ducked under the voice
    mix = np.zeros(int((total + 0.5) * SR))
    voiced = np.zeros_like(mix)
    for s, c in zip(starts, clips):
        i = int(s * SR)
        mix[i: i + len(c["audio"])] += c["audio"]
        voiced[i: i + len(c["audio"])] = 1
    for s in scene_start:
        p = _pop()
        i = int(s * SR)
        mix[i: i + len(p)] += p * 0.25
    if with_music:
        m = music(total + 0.5)[: len(mix)]
        duck = np.convolve(voiced, np.ones(4800) / 4800, mode="same")[: len(m)]
        mix[: len(m)] += m * (0.085 - 0.04 * duck)
    peak = abs(mix).max()
    if peak > 0.95:
        mix *= 0.95 / peak

    work = Path(tempfile.mkdtemp(prefix="explainer-"))
    wav = work / "mix.wav"
    save_wav(mix, wav)

    # pictures, with props timed to their words
    all_layers = []
    for k, sc in enumerate(scenes):
        offset = starts[k] - scene_start[k]
        words = [(w.lower().strip(".,!?"), a + offset) for w, a, _ in clips[k]["words"]]

        def when(word, words=words):
            word = str(word).lower().strip(".,!?")
            return next((a for w, a in words if w == word), None)
        all_layers.append(S.layers(sc, when, scene_end[k] - scene_start[k], handle, logo, cta))
    render_layers(all_layers, work)
    bg = background(tag).convert("RGBA")

    caption_words = [(w, s + a, s + b) for s, c in zip(starts, clips) for w, a, b in c["words"]]
    cache = {}
    cmd = [ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(wav),
           "-vf", "scale=1080:1920:out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", str(crf), "-profile:v", "high",
           "-level:v", "4.1", "-bf", "0", "-g", "60", "-r", str(FPS),
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
           "-af", "loudnorm=I=-15:TP=-1.5:LRA=11",
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
           "-t", f"{total:.3f}", "-movflags", "+faststart", "-use_editlist", "0", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    wi, cover_t = 0, min(1.2, scene_end[0] - 0.1)
    try:
        for fi in range(int(total * FPS)):
            t = fi / FPS
            frame = bg.copy()
            si = max(i for i, s in enumerate(scene_start) if s <= t)
            ts = t - scene_start[si]
            if si > 0 and ts < 0.16:              # the last picture fades out under the new one
                prev = scene_start[si] - scene_start[si - 1]
                for lay in all_layers[si - 1]:
                    st = layer_state(lay, prev + ts)
                    if st:
                        _paste(frame, lay, st, 1 - ts / 0.16)
            for lay in all_layers[si]:
                st = layer_state(lay, ts)
                if st:
                    _paste(frame, lay, st, t=ts)
            while wi + 1 < len(caption_words) and caption_words[wi + 1][1] <= t:
                wi += 1
            if caption_words:
                w, a, b = caption_words[wi]
                nxt = caption_words[wi + 1][1] if wi + 1 < len(caption_words) else total
                if a <= t and (t < b + 0.35 or t < nxt):
                    if w not in cache:
                        cache[w] = caption_img(w)
                    ci = cache[w]
                    s = 1.18 - 0.18 * min(1, (t - a) / 0.09)
                    im = ci.resize((int(ci.width * s), int(ci.height * s))) if s > 1.001 else ci
                    frame.alpha_composite(im, (int(W / 2 - im.width / 2), int(CAPTION_Y - im.height / 2)))
            if abs(t - cover_t) < 0.5 / FPS:
                frame.convert("RGB").save(cover, "JPEG", quality=88)
            proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait(timeout=600):
            raise EngineError(f"ffmpeg failed: {err.strip()[-300:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    return {"seconds": round(total, 2), "scene_start": [round(s, 2) for s in scene_start],
            "words": [[w, round(a, 2)] for w, a, _ in caption_words], "thumb_ms": int(cover_t * 1000)}
