"""Story explainers: a short cartoon scene in a classroom. Two students ask, the elephant teacher explains
at the chalkboard, and each line is spoken in that character's own free Kokoro voice. Mouths move with
the voice, the board drawings appear as their words are said, short subtitles in a box (coloured by
who is speaking) sit where they don't cover faces, and the camera pushes in slowly on each shot.

A script is {"hook_label", "lines": [line, ...]} where a line is
    {"who": "teacher" | "girl" | "boy", "say": "...", "shot": "board" | "desk" | "close" | "follow",
     "pose": "...", "react": "...", "board": {...}}
`board` (only on teacher lines) puts a new drawing on the chalkboard (see story_sets.BOARD_KINDS);
it stays there until the next one.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import cartoon_scenes as CS
from . import cartoon_video as V
from . import elephant as M
from . import students as S
from . import story_sets as Z
from . import students_art as SA

W, H, FPS, SR = 1080, 1920, 30, 24000
CAST = {
    "teacher": {"voice": "af_heart", "speed": 1.05, "color": (255, 200, 30)},
    "girl": {"voice": "af_sarah", "speed": 1.08, "color": (255, 157, 181)},
    "boy": {"voice": "am_fenrir", "speed": 1.08, "color": (143, 216, 255)},
}
SHOTS = ("board", "desk", "close", "follow")
LEAD, TAIL = 0.3, 1.5
GAP_SAME, GAP_CHANGE = 0.16, 0.3
CAPTION_FONT = V.FONTS / "Poppins-ExtraBold.ttf"
CAPTION_Y = {"board": 1046, "follow": 1046, "desk": 470, "close": 470}

# where each character stands in each shot: (x centre, box top, scale)
PLACE = {
    "board": {"teacher": (810, 1030, 1.12), "girl_back": (190, 1390, 0.95), "boy_back": (470, 1430, 0.95)},
    "desk": {"girl": (290, 790, 1.06), "boy": (790, 790, 1.06)},
    "close": {"teacher": (540, 700, 1.45), "girl": (540, 640, 1.5), "boy": (540, 640, 1.5)},
}
# the students from the page's character sheets: (head x, eye line y or None = sit on the frame's
# bottom, distance between the eyes in pixels)
ART_PLACE = {
    "board": {"girl_back": (205, None, 128), "boy_back": (500, None, 128)},
    "desk": {"girl": (295, 1010, 134), "boy": (790, 1010, 134)},
    "close": {"girl": (540, None, 196), "boy": (540, None, 196)},
}
# script pose names -> the sheet's poses
ART_POSE = {
    "boy": {"talk": "listen", "listen": "listen", "ask": "ask", "think": "think", "shocked": "shocked",
            "worried": "worried", "happy": "happy", "excited": "cheer", "aha": "point", "point": "point",
            "nervous": "nervous", "wave": "wave", "doubt": "think2", "shrug": "ask"},
    "girl": {"talk": "neutral", "listen": "listen", "ask": "ask", "think": "think", "shocked": "shocked",
             "worried": "worried", "happy": "happy", "excited": "excited", "aha": "point", "point": "point",
             "nervous": "nervous", "wave": "wave", "doubt": "think2", "shrug": "ask"},
}
TEACHER_IDLE = {"face": "happy", "left": "hip", "right": "down"}
LOOK_AT = {"girl": (9, 2), "boy": (-9, 2)}            # a listener looks at the other student


class StoryError(RuntimeError):
    pass


# ── checking a script ───────────────────────────────────────
def check(script: dict) -> list[str]:
    lines = script.get("lines") or []
    out = []
    if not 8 <= len(lines) <= 18:
        out.append(f"{len(lines)} lines; write 8-18")
    for i, ln in enumerate(lines, 1):
        where = f"line {i}"
        who, shot = ln.get("who"), ln.get("shot")
        if who not in CAST:
            out.append(f"{where}: who must be one of {', '.join(CAST)}")
            continue
        if shot not in SHOTS:
            out.append(f"{where}: shot must be one of {', '.join(SHOTS)}")
        if not str(ln.get("say") or "").strip():
            out.append(f"{where}: say is empty")
        student_poses = ART_POSE["girl"] if SA.available() else S.POSES
        poses = M.POSES if who == "teacher" else student_poses
        if ln.get("pose") and ln["pose"] not in poses:
            out.append(f"{where}: pose '{ln['pose']}' is not one of {', '.join(poses)}")
        if ln.get("react") and ln["react"] not in student_poses:
            out.append(f"{where}: react '{ln['react']}' is not one of {', '.join(student_poses)}")
        if shot == "board" and who != "teacher" and i == 1:
            out.append(f"{where}: open on the students (desk or close), not the board")
        if ln.get("board"):
            if who != "teacher":
                out.append(f"{where}: only the teacher's lines change the board")
            out += Z.check_board(ln["board"], CS._words(ln.get("say", "")), where)
    if lines and lines[-1].get("shot") != "follow":
        out.append("the last line must use the follow shot")
    return out


# ── sound ───────────────────────────────────────────────────
def _mouths(audio) -> list[int]:
    """Mouth shape (0 shut, 1 half, 2 open) for each 1/15 s of a voice clip: louder opens wider, and the
    mouth half-closes as each syllable fades, so it moves with the rhythm of the words."""
    import numpy as np

    step = SR // 15
    n = max(1, len(audio) // step)
    rms = np.array([np.sqrt(np.mean(audio[i * step:(i + 1) * step] ** 2) + 1e-12) for i in range(n)])
    level = rms / (np.percentile(rms, 92) or 1)
    out = []
    for i, v in enumerate(level):
        m = 0 if v < 0.3 else 1 if v < 0.75 else 2
        if m and i and v < level[i - 1] * 0.93:          # fading: close a little
            m -= 1
        if m and len(out) >= 2 and out[-1] == out[-2] == m:  # never hold one shape for long
            m -= 1
        out.append(m)
    return out


WEAK = {"the", "a", "an", "to", "of", "for", "and", "in", "on", "at", "is", "with", "by", "or", "but", "so", "if",
        "it", "its", "your", "you", "we", "they", "this", "that", "be", "are", "was", "will"}


def _phrase_cost(g, whole: bool = False) -> float:
    text = " ".join(w for w, _, _ in g)
    cost = ((len(text) - 17) / 6) ** 2 + 1.5
    if len(g) == 1 and not whole:
        cost += 3
    if g[-1][0].lower().strip(",.!?") in WEAK and not re.search(r"[,.!?:;]$", g[-1][0]):
        cost += 4
    if len(text) > 28 or len(g) > 5:
        cost += 100
    return cost


def chunks(words: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """Caption phrases of a few words: each stretch between punctuation marks is cut where the phrases
    come out even, and a phrase doesn't end on a small word like 'the' or 'for'."""
    segs, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[,.!?:;]$", w[0]):
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    out = []
    for seg in segs:
        n = len(seg)
        best = [0.0] + [math.inf] * n          # best[j]: cheapest way to cut seg[:j]
        cut = [0] * (n + 1)
        for j in range(1, n + 1):
            for i in range(max(0, j - 6), j):
                c = best[i] + _phrase_cost(seg[i:j], i == 0 and j == n)
                if c < best[j]:
                    best[j], cut[j] = c, i
        groups, j = [], n
        while j > 0:
            groups.insert(0, seg[cut[j]:j])
            j = cut[j]
        out += [(" ".join(w for w, _, _ in g), g[0][1], g[-1][2]) for g in groups]
    return out


# ── captions ────────────────────────────────────────────────
def caption_img(text: str, color):
    from PIL import Image, ImageDraw, ImageFont

    text = re.sub(r"[,;:.\"“”]+$", "", re.sub(r"^[\"“”]+", "", text.upper()))
    size = 56
    font = ImageFont.truetype(str(CAPTION_FONT), size)
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    while d.textlength(text, font=font) > 880 and size > 36:
        size -= 2
        font = ImageFont.truetype(str(CAPTION_FONT), size)
    tw = d.textlength(text, font=font)
    w, h = int(tw + 70), int(size * 1.62)
    img = Image.new("RGBA", (w + 12, h + 14), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([6, 10, w + 6, h + 10], radius=22, fill=(10, 14, 28, 90))
    dr.rounded_rectangle([4, 4, w + 4, h + 4], radius=22, fill=(22, 28, 52, 236), outline=(255, 255, 255, 60), width=3)
    dr.text((4 + w / 2, 4 + h / 2 + 2), text, font=font, fill=color + (255,), anchor="mm")
    return img


# ── drawing the characters ──────────────────────────────────
def _put(svg: str, x, top, s) -> str:
    return f'<g transform="translate({x - 300 * s} {top}) scale({s})">{svg}</g>'


def _char_svg(who: str, pose, place, talk: int, blink: bool, uid: str) -> str:
    x, top, s = place
    if who == "teacher":
        p = dict(M.POSES[pose] if isinstance(pose, str) else pose)
        if p.get("face") in ("smug", "proud"):          # a warm teacher, not a smug one
            p["face"] = "happy"
        p["talk"], p["blink"] = talk, blink
        return _put(M.character(p, uid), x, top, s)
    if who.endswith("_back"):
        return _put(S.back_view(who[:-5], uid), x, top, s)
    return _put(S.character(who, pose, uid, talk, blink), x, top, s)


class Cast:
    """Draws and caches every character picture the video needs (each pose with its mouth shapes and
    a blink), all cropped to the same box so they can be swapped frame by frame."""

    def __init__(self, painter, work: Path):
        self.painter, self.work, self.cache, self.n = painter, work, {}, 0

    def get(self, who, pose, place, talking: bool, shot: str = "") -> dict:
        key = (who, repr(pose), place, talking, shot)
        if key in self.cache:
            return self.cache[key]
        if who != "teacher" and SA.available():
            lay = self._art(who, pose, shot, talking)
            self.cache[key] = lay
            return lay
        variants = {}
        states = [(t, b) for t in ((0, 1, 2) if talking else (0,)) for b in (False, True)]
        if who.endswith("_back"):
            states = [(0, False)]
        for talk, blink in states:
            self.n += 1
            variants[(talk, blink)] = self.painter.draw(_char_svg(who, pose, place, talk, blink, f"c{self.n}"),
                                                        self.work / "c.png")
        box = None
        for im in variants.values():
            b = im.getbbox() or (0, 0, 1, 1)
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        lay = {"off": box[:2], "v": {k: im.crop(box) for k, im in variants.items()},
               "head": (place[0], place[1] + 260 * place[2])}
        self.cache[key] = lay
        return lay


    def _art(self, who, pose, shot, talking) -> dict:
        """A student from the character sheets, placed for the shot."""
        base = who.replace("_back", "")
        name = "back" if who.endswith("_back") else ART_POSE[base].get(pose if isinstance(pose, str) else "listen", "listen")
        hx, ey, ed = ART_PLACE["board" if shot == "follow" else shot][who]
        meta = SA.POSES[f"{base}_{name}"]
        s = ed / meta["ed"]
        below = (meta["rect"][3] - meta["anchor"][1]) * s      # from the eyes down to the picture's bottom edge
        if ey is None:                           # stand on the bottom edge (a little below it)
            ey = H + 12 - below
        elif shot == "desk":                     # the picture's bottom edge must stay behind the desk
            ey = max(ey, Z.DESK_TOP + 24 - below)
        states = [(t, b) for t in ((0, 1, 2) if talking else (0,)) for b in (False, True)]
        if who.endswith("_back") or not meta.get("eyes"):
            states = [(t, False) for t in ((0, 1, 2) if talking and meta.get("mouth") else (0,))]
        variants, off = {}, None
        for talk, blink in states:
            im, off = SA.placed(base, name, hx, ey, ed, talk, blink)
            variants[(talk, blink)] = im
        return {"off": off, "v": variants, "head": (hx, ey)}

# ── one frame ───────────────────────────────────────────────
def _blink(t: float, phase: float) -> bool:
    return ((t + phase) % 3.6) < 0.12


def _camera(frame, zoom: float, focus):
    from PIL import Image

    if zoom <= 1.001:
        return frame
    cw, ch = W / zoom, H / zoom
    fx, fy = focus
    x0 = min(max(0, fx - cw / 2), W - cw)
    y0 = min(max(0, fy - ch * 0.45), H - ch)
    return frame.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))


def render(script: dict, out: Path, cover: Path, tag: str = "", handle: str = "", logo: Path | None = None,
           cta: str = "", speed: float = 1.05, with_music: bool = True, crf: int = 28,
           stills: list[float] | None = None) -> dict:
    """Makes the story reel at `out` and its cover at `cover`. Returns timings."""
    import numpy as np
    from PIL import Image, ImageFilter

    from .kokoro import Voice, save_wav, SR as KSR
    from .video import ffmpeg_path

    problems = check(script)
    if problems:
        raise StoryError("; ".join(problems[:6]))
    lines = script["lines"]
    voice = Voice()
    clips = []
    for ln in lines:
        a = voice.synth(V.spoken_text(ln["say"]), CAST[ln["who"]]["voice"], CAST[ln["who"]]["speed"] * speed / 1.05)
        lo, hi = V.voiced_span(a)
        a = a[max(0, lo - int(0.03 * KSR)): hi + int(0.06 * KSR)]
        env = np.sqrt(np.convolve(a * a, np.ones(2400) / 2400, mode="same"))
        loud = a[env > 0.02]
        if len(loud):                             # every voice at the same loudness
            a = a * min(3.0, 0.09 / float(np.sqrt(np.mean(loud ** 2))))
        words = V.word_times(ln["say"], a)
        raw = [w for w, _ in V.tokens(ln["say"]) if re.search(r"[\w₹%]", V.shown(w))]
        if len(raw) == len(words):            # keep the punctuation, so phrases break at commas and full stops
            words = [(r, a0, b0) for r, (_, a0, b0) in zip(raw, words)]
        clips.append({"audio": a, "words": words, "mouth": _mouths(a)})
    starts, t = [], LEAD
    for i, c in enumerate(clips):
        if i:
            t += GAP_SAME if lines[i]["who"] == lines[i - 1]["who"] else GAP_CHANGE
        starts.append(t)
        t += len(c["audio"]) / SR
    total = t + TAIL
    line_start = [0.0] + [max(0.0, s - 0.1) for s in starts[1:]]
    line_end = line_start[1:] + [total]

    # board drawings: which drawing is up during each line, and when each piece appears
    boards, current = [], None
    for i, ln in enumerate(lines):
        if ln.get("board"):
            words = [(w.lower().strip(".,!?;:"), a) for w, a, _ in clips[i]["words"]]

            def when(word, words=words, off=starts[i] - line_start[i]):
                word = str(word or "").lower().strip(".,!?")
                hit = next((a for w, a in words if w == word), None)
                return None if hit is None else hit + off
            pieces = []
            dur = line_end[i] - line_start[i]
            for svg, key in Z.board_layers(ln["board"]):
                if isinstance(key, str):
                    delay = CS._at(when, ln["board"].get(key), 0.5 * dur, dur)
                else:
                    delay = 0.05 + key
                pieces.append({"svg": svg, "t0": line_start[i] + delay})
            current = {"pieces": pieces, "t0": line_start[i]}
        boards.append(current)
    if lines[-1]["shot"] == "follow":
        card = f'<g transform="translate(0 -190)">{CS.follow_card(handle, logo, cta)}</g>'
        boards[-1] = {"pieces": [{"svg": card, "t0": line_start[-1] + 0.1}], "t0": line_start[-1]}

    # sound: voices, a soft pop for each board drawing and the stamp, the tune under the voices
    mix = np.zeros(int((total + 0.5) * SR))
    voiced = np.zeros_like(mix)
    for s, c in zip(starts, clips):
        i = int(s * SR)
        mix[i: i + len(c["audio"])] += c["audio"]
        voiced[i: i + len(c["audio"])] = 1
    pops = sorted({round(p["t0"], 2) for b in boards if b for p in b["pieces"]})
    if script.get("hook_label"):
        pops.append(0.2)
    for s in pops:
        p = V._pop()
        i = int(s * SR)
        mix[i: i + len(p)] += p * 0.22
    if with_music:
        m = V.music(total + 0.5)[: len(mix)]
        duck = np.convolve(voiced, np.ones(4800) / 4800, mode="same")[: len(m)]
        mix[: len(m)] += m * (0.08 - 0.04 * duck)
    peak = abs(mix).max()
    if peak > 0.95:
        mix *= 0.95 / peak

    work = Path(tempfile.mkdtemp(prefix="story-"))
    wav = work / "mix.wav"
    save_wav(mix, wav)
    try:
        with V.Painter(work) as painter:
            # places
            bg = {"board": painter.draw(Z.classroom(tag), work / "bg.png").convert("RGB"),
                  "desk": painter.draw(Z.study_room(), work / "bg.png").convert("RGB")}
            bg["follow"] = bg["board"]
            bg["close_students"] = bg["desk"].filter(ImageFilter.GaussianBlur(9))
            bg["close_teacher"] = bg["board"].filter(ImageFilter.GaussianBlur(9))
            desk = painter.draw(Z.desk(), work / "desk.png")
            dbox = desk.getbbox()
            desk_lay = (desk.crop(dbox), dbox[:2])
            stamp = None
            if script.get("hook_label"):
                lab = script["hook_label"]
                im = painter.draw(Z.at(CS.P.label(lab, CS.P.RED, CS._fit(lab, 88, 820, 0.66)), 540, 690), work / "st.png")
                b = im.getbbox()
                stamp = {"img": im.crop(b), "off": b[:2], "anim": "stamp", "delay": 0.15, "bob": False, "drift": (0, 0)}
            for b in boards:
                for p in (b or {}).get("pieces", []):
                    if "img" not in p:
                        im = painter.draw(p["svg"], work / "bd.png")
                        box = im.getbbox() or (0, 0, 1, 1)
                        p.update(img=im.crop(box), off=box[:2], anim="pop", delay=0.0, bob=False, drift=(0, 0))
            # who is on screen in each line, in which pose
            cast = Cast(painter, work)
            plan = []
            for i, ln in enumerate(lines):
                who, shot = ln["who"], ln["shot"]
                people = []
                if shot in ("board", "follow"):
                    tp = (ln.get("pose") or "explain") if who == "teacher" else TEACHER_IDLE
                    if shot == "follow":
                        tp = "wink"
                    people = [("girl_back", None), ("boy_back", None), ("teacher", tp)]
                    place = PLACE["board"]
                elif shot == "desk":
                    place = PLACE["desk"]
                    for st in ("girl", "boy"):
                        if st == who:
                            people.append((st, ln.get("pose") or "talk"))
                        elif SA.available():
                            people.append((st, ln.get("react") or "listen"))
                        else:
                            react = dict(S.POSES[ln.get("react") or "listen"])
                            react.setdefault("look", (0, -9) if who == "teacher" else LOOK_AT[st])
                            people.append((st, react))
                else:                                            # close-up of the speaker
                    place = PLACE["close"]
                    people = [(who, ln.get("pose") or ("explain" if who == "teacher" else "talk"))]
                layers = []
                for name, pose in people:
                    pl = place[name]
                    layers.append((name, cast.get(name, pose, pl, name == who, shot)))
                plan.append({"layers": layers, "shot": shot,
                             "bg": bg["close_teacher" if who == "teacher" else "close_students"] if shot == "close" else bg[shot]})
        # camera runs: consecutive lines with the same shot (and speaker, for close-ups) share one push-in
        runs, r0 = [], 0
        for i in range(1, len(lines) + 1):
            if i == len(lines) or lines[i]["shot"] != lines[r0]["shot"] or (
                    lines[i]["shot"] == "close" and lines[i]["who"] != lines[r0]["who"]):
                runs.append((r0, i - 1))
                r0 = i
        run_of = {i: r for r in runs for i in range(r[0], r[1] + 1)}
        captions = []
        for i, c in enumerate(clips):
            col = CAST[lines[i]["who"]]["color"]
            for text, a, b in chunks(c["words"]):
                captions.append((text, starts[i] + a, starts[i] + b, col, CAPTION_Y[lines[i]["shot"]], i))
        cap_cache = {}
        phases = {"teacher": 0.0, "girl": 1.3, "boy": 2.4}
        cover_t = min(1.3, line_end[0] - 0.1)

        def frame_at(t: float):
            li = max(i for i, s in enumerate(line_start) if s <= t)
            ln, pl = lines[li], plan[li]
            frame = pl["bg"].convert("RGBA")
            if pl["shot"] in ("board", "follow") and boards[li]:
                bd = boards[li]
                prev = boards[li - 1] if li else None
                if prev and prev is not bd and t - bd["t0"] < 0.18 and lines[li - 1]["shot"] in ("board", "follow"):
                    for p in prev["pieces"]:
                        V._paste(frame, p, (1, 1, 0, 0), 1 - (t - bd["t0"]) / 0.18)
                for p in bd["pieces"]:
                    st = V.layer_state(p, t - p["t0"]) if t >= p["t0"] else None
                    if st:
                        V._paste(frame, p, st)
            for name, lay in pl["layers"]:
                base = name.replace("_back", "")
                talk = 0
                if name == ln["who"]:
                    k = int((t - starts[li]) * 15)
                    mouth = clips[li]["mouth"]
                    talk = mouth[k] if 0 <= k < len(mouth) else 0
                blink = _blink(t, phases.get(base, 0)) and abs(t - cover_t) > 0.3     # eyes open on the cover
                im = lay["v"].get((talk, blink)) or lay["v"].get((talk, False)) or lay["v"][(0, False)]
                speaking = name == ln["who"] and starts[li] <= t <= starts[li] + len(clips[li]["audio"]) / SR
                dy = math.sin(2 * math.pi * t / (1.7 if speaking else 2.8) + phases.get(base, 0)) * (5 if speaking else 3)
                frame.alpha_composite(im, (int(lay["off"][0]), int(lay["off"][1] + dy)))
            if pl["shot"] == "desk":
                frame.alpha_composite(desk_lay[0], desk_lay[1])
            if li == 0 and stamp:                           # the hook's stamp, over everyone
                st = V.layer_state(stamp, t)
                if st:
                    V._paste(frame, stamp, st)
            # camera: a slow push-in on the speaker over each run of lines
            r0, r1 = run_of[li]
            span = max(0.5, line_end[r1] - line_start[r0])
            k = min(1.0, (t - line_start[r0]) / span)
            zoom = 1 + (0.06 if pl["shot"] == "close" else 0.035) * (k * k * (3 - 2 * k))
            spk = next((lay for name, lay in pl["layers"] if name == ln["who"]), None)
            focus = spk["head"] if spk else (W / 2, H * 0.45)
            frame = _camera(frame.convert("RGB"), zoom, focus).convert("RGBA")
            ci = max((i for i, c in enumerate(captions) if c[1] <= t), default=None)
            if ci is not None:
                text, a, b, col, y, cl = captions[ci]
                nxt = captions[ci + 1][1] if ci + 1 < len(captions) else total
                if t < min(nxt, b + 0.5) and cl == li:          # never carried into the next shot
                    key = (text, col)
                    if key not in cap_cache:
                        cap_cache[key] = caption_img(text, col)
                    im = cap_cache[key]
                    sc = 1.06 - 0.06 * min(1, (t - a) / 0.08)
                    if sc > 1.001:
                        im = im.resize((int(im.width * sc), int(im.height * sc)))
                    frame.alpha_composite(im, (int(W / 2 - im.width / 2), int(y - im.height / 2)))
            return frame.convert("RGB")

        if stills:                                   # look at a few moments without making the video
            for t in stills:
                frame_at(min(t, total - 0.01)).save(out.parent / f"still_{t:05.2f}.jpg", quality=90)
            return {"seconds": round(total, 2), "line_start": [round(x, 2) for x in line_start]}

        cmd = [ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(wav),
               "-vf", "scale=1080:1920:out_color_matrix=bt709:out_range=tv,format=yuv420p",
               "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", str(crf), "-profile:v", "high",
               "-level:v", "4.1", "-bf", "0", "-g", "60", "-r", str(FPS),
               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
               "-af", "loudnorm=I=-15:TP=-1.5:LRA=11",
               "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
               "-t", f"{total:.3f}", "-movflags", "+faststart", "-use_editlist", "0"]
        tmp_out = out.with_name(out.stem + ".part.mp4")
        proc = subprocess.Popen(cmd + [str(tmp_out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for fi in range(int(total * FPS)):
                t = fi / FPS
                rgb = frame_at(t)
                if abs(t - cover_t) < 0.5 / FPS:
                    rgb.save(cover, "JPEG", quality=88)
                proc.stdin.write(rgb.tobytes())
            proc.stdin.close()
            err = proc.stderr.read().decode(errors="replace")
            if proc.wait(timeout=600):
                raise StoryError(f"ffmpeg failed: {err.strip()[-300:]}")
        finally:
            if proc.poll() is None:
                proc.kill()
        tmp_out.replace(out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"seconds": round(total, 2), "line_start": [round(x, 2) for x in line_start],
            "captions": [[c[0], round(c[1], 2)] for c in captions], "thumb_ms": int(min(1.3, line_end[0] - 0.1) * 1000)}
