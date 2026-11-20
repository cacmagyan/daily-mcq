"""QT trap reel in 3D: the same script as qt_video.py (hook -> trap -> question -> options -> pause ->
reveal -> steps -> shortcut -> your turn), drawn as lit 3D objects with soft shadows and a moving camera
(three.js in headless Chromium, assets/qt3d/stage.js), with HTML cards and word-by-word captions on top.

Python does the timing and the sound: the voice for every line (Azure's natural Indian-English voice when
AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are set, else the free offline Kokoro voice), the moments each
option and working row appears, and the sound effects that go with them. The page is then stepped one
frame at a time (seek(t)) and each frame is piped to ffmpeg.
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from .config import ROOT

W, H, FPS = 1080, 1920, 30
SR = 48000
STAGE = ROOT / "assets" / "qt3d" / "stage.html"
LEAD, GAP, TAIL = 0.3, 0.16, 1.8
COUNTDOWN = 3.0
AZURE_VOICE = "en-IN-PrabhatNeural"      # default; config pyq.azure_voice (or QT3D_VOICE) picks another
AZURE_SPEED = 1.12
KOKORO_VOICE = "am_michael"
KOKORO_SPEED = 1.12
CHROME_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
               "--allow-file-access-from-files", "--disable-web-security"]


class QT3DError(RuntimeError):
    pass


def azure_ready() -> bool:
    return bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))


# ── voice ───────────────────────────────────────────────────
def _wav_to_float(data: bytes):
    import numpy as np

    with wave.open(io.BytesIO(data)) as w:
        rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        raise QT3DError("unexpected voice audio format")
    a = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return resample(a, rate, SR)


def resample(a, src: int, dst: int):
    import numpy as np

    if src == dst or len(a) == 0:
        return np.asarray(a, np.float32)
    n = int(round(len(a) * dst / src))
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)


def _trim(a, thr=0.008, pad=0.03):
    import numpy as np

    idx = np.where(np.abs(a) > thr)[0]
    if not len(idx):
        return a
    lo = max(0, idx[0] - int(pad * SR))
    hi = min(len(a), idx[-1] + int(pad * SR * 2))
    return a[lo:hi]


def estimate_words(say: str, dur: float):
    ws = [w for w in say.split() if re.search(r"[\w₹%]", w)]
    weights = [max(2, len(re.sub(r"\W", "", w))) + (4 if re.search(r"[,.!?:;]$", w) else 0) for w in ws]
    tot, t, out = sum(weights) or 1, 0.0, []
    for w, k in zip(ws, weights):
        d = dur * k / tot
        out.append((w, t, t + d))
        t += d
    return out


def voice_lines(script: dict, silent: bool = False, azure_voice: str | None = None) -> tuple[list, str]:
    """[(audio at SR or None, seconds, [(word, start, end)])] per line, and which voice was used."""
    azure_voice = azure_voice or os.environ.get("QT3D_VOICE") or AZURE_VOICE
    import numpy as np

    lines = script["lines"]
    if silent:
        out = []
        for ln in lines:
            say = re.sub(r"\{([^|}]+)\|[^}]+\}", r"\1", ln["say"])
            dur = max(1.2, len(say.split()) / 2.6 + 0.25)
            out.append((None, dur, estimate_words(say, dur)))
        return out, "none (preview)"

    from .cartoon_video import SR as KSR, spoken_text, tokens, word_times

    def words_for(say, a):
        a24 = resample(a, SR, KSR)
        try:
            ws = word_times(say, a24)
        except Exception:                                  # no phonemizer: share the time out by letters
            ws = estimate_words(re.sub(r"\{([^|}]+)\|[^}]+\}", r"\1", say), len(a) / SR)
        raw = [w for w, _ in tokens(say) if re.search(r"[\w₹%]", w)]
        if len(raw) == len(ws):                            # keep "due." so a caption phrase ends at the full stop
            ws = [(r, s, e) for r, (_, s, e) in zip(raw, ws)]
        return ws

    out = []
    if azure_ready():
        from . import tts

        try:
            for ln in lines:
                text = tts.speakable(spoken_text(ln["say"]))
                a = _trim(_wav_to_float(tts._azure(text, azure_voice, AZURE_SPEED, tight=True)))
                out.append((a, len(a) / SR, words_for(ln["say"], a)))
            return out, f"{azure_voice} (Azure)"
        except Exception as exc:                           # fall back to the free voice, never fail the reel
            out = []
            print(f"Azure voice failed, using Kokoro: {str(exc)[:160]}")
    from .kokoro import Voice

    v = Voice()
    for ln in lines:
        a = _trim(resample(np.asarray(v.synth(spoken_text(ln["say"]), KOKORO_VOICE, KOKORO_SPEED), np.float32), KSR, SR))
        out.append((a, len(a) / SR, words_for(ln["say"], a)))
    return out, f"{KOKORO_VOICE} (Kokoro)"


# ── timeline ────────────────────────────────────────────────
def _group(card: dict) -> str | None:
    k = (card or {}).get("kind")
    if k in ("question", "pause", "reveal"):
        return "q"
    if k == "hook":
        return f"hook:{card.get('small', '')}|{card.get('big', '')}"
    if k == "trap":
        return "trap"
    if k == "attempt":
        return "attempt"
    if k in ("step", "shortcut", "your_turn"):
        return f"{k}:{card.get('title', '')}"
    return None


def _norm(w: str) -> str:
    return re.sub(r"[^\w₹.%]", "", w.lower()).strip(".")


def _option_times(ev: dict, options: list[str]) -> list[float]:
    """When each option is read out in "Is it A, B, C, or D?" (falls back to an even spread)."""
    words = ev["words"]
    toks = [_norm(w[0]) for w in words]
    out, j = [], 0
    for opt in options:
        first = _norm(opt.split()[0]) if opt.split() else ""
        hit = None
        for i in range(j, len(toks)):
            if first and (toks[i] == first or toks[i].startswith(first) or first.startswith(toks[i]) and len(toks[i]) > 2):
                hit = i
                break
        if hit is None:
            out = []
            break
        out.append(words[hit][1])
        j = hit + 1
    if len(out) != len(options):
        out = [ev["start"] + ev["dur"] * (0.08 + 0.22 * i) for i in range(len(options))]
    return out


def timeline(script: dict, vl: list) -> tuple[list[dict], float]:
    t = LEAD
    events = []
    for ln, (audio, dur, words) in zip(script["lines"], vl):
        ev = {"line": ln, "start": round(t, 4), "dur": round(dur, 4), "audio": audio,
              "words": [[w, round(t + a, 4), round(t + b, 4)] for w, a, b in words]}
        events.append(ev)
        t += dur + GAP
        if (ln.get("card") or {}).get("kind") == "pause":
            ev["countdown"] = [round(t, 4), round(t + COUNTDOWN, 4)]
            t += COUNTDOWN
    return events, t + TAIL


def _phrases(words: list, size: int = 3) -> list[list[int]]:
    out, a = [], 0
    for i, (w, _, _) in enumerate(words):
        if i - a + 1 >= size or re.search(r"[,.!?:;]$", w) or i == len(words) - 1:
            out.append([a, i])
            a = i + 1
    return out


def _trap_index(script: dict) -> int | None:
    if isinstance(script.get("trap"), int):
        return script["trap"]
    for ln in script["lines"]:
        c = ln.get("card") or {}
        if c.get("kind") == "trap":
            big = re.sub(r"[×✕x\s]+$", "", str(c.get("big", ""))).strip()
            for i, o in enumerate(script.get("options", [])):
                if big and (_norm(big) == _norm(o) or _norm(o) in _norm(big)):
                    return i
    return None


LOGO = ROOT / "assets" / "brand" / "logo.png"


def make_plan(script: dict, events: list[dict], total: float, handle: str, logo: Path | None = None) -> dict:
    states, cur = [], dict(script.get("scene") or {"type": "board", "lines": []})
    for ev in events:
        prev = dict(cur)
        upd = ev["line"].get("scene")
        if upd:
            cur = dict(upd) if upd.get("type") and upd.get("type") != cur.get("type") else {**cur, **upd}
        states.append((prev, dict(cur)))

    out, g_start, last_group, rows_seen = [], 0.0, None, {}
    opt_times, reveal_at = None, None
    for i, ev in enumerate(events):
        card = ev["line"].get("card") or {}
        g = _group(card)
        if g != last_group:
            g_start = ev["start"]
            rows_seen.setdefault(g, [])
        last_group = g
        pe = {"start": ev["start"], "dur": ev["dur"], "card": card, "group": g, "gStart": g_start,
              "words": ev["words"], "phrases": _phrases(ev["words"]),
              "prev": None if i == 0 else states[i][0], "cur": states[i][1]}
        if ev.get("countdown"):
            pe["countdown"] = ev["countdown"]
        if card.get("kind") == "question" and card.get("options") and opt_times is None:
            opt_times = _option_times(ev, script.get("options", []))
        if card.get("kind") == "reveal" and reveal_at is None:
            reveal_at = ev["start"]
        if card.get("kind") in ("step", "shortcut", "your_turn"):
            rows = card.get("rows") or []
            known = rows_seen[g]
            times = []
            for r_i in range(len(rows)):
                if r_i < len(known):
                    times.append(known[r_i])
                    continue
                new_i = r_i - len(known)
                n_new = len(rows) - len(known)
                if card.get("all") or n_new <= 1:
                    at = ev["start"] + (0.12 if r_i else 0.2) + 0.3 * new_i
                else:
                    at = ev["start"] + 0.15 + ev["dur"] * 0.85 * new_i / n_new
                times.append(round(at, 4))
            rows_seen[g] = times
            pe["rowTimes"] = times
            if card.get("kind") == "your_turn" and card.get("all"):
                pe["ctaAt"] = round(ev["start"] + 0.4, 4)
        out.append(pe)
    yt = [e for e in out if (e["card"] or {}).get("kind") == "your_turn"]
    if yt and not any("ctaAt" in e for e in yt):
        yt[-1]["ctaAt"] = round(yt[-1]["start"] + 0.4, 4)
    for e in yt:                                            # the call-to-action stays once it is up
        e.setdefault("ctaAt", max([x.get("ctaAt", 1e9) for x in yt]))
    badge = script.get("badge") or {}
    logo = logo if logo is not None else LOGO
    last = out[-1] if out else None
    end_at = round(last["start"] + 0.5, 4) if last and (last["card"] or {}).get("kind") == "your_turn" else None
    return {"W": W, "H": H, "total": round(total, 3), "theme": script.get("theme", "green"),
            "logo": Path(logo).resolve().as_uri() if logo and Path(logo).exists() else "", "endAt": end_at,
            "badge": {"tag": badge.get("tag", "CA FOUNDATION"), "text": badge.get("text", "")},
            "handle": handle, "header": script.get("header", ""), "question": script.get("question", ""),
            "options": script.get("options", []), "answer": script.get("answer"), "trap": _trap_index(script),
            "optTimes": opt_times or [], "revealAt": reveal_at, "events": out}


# ── sound ───────────────────────────────────────────────────
def _env(n, a=0.005, r=0.1):
    import numpy as np

    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(r, 1e-4))


def _noise(n, seed):
    import numpy as np

    return np.random.default_rng(seed).uniform(-1, 1, n).astype(np.float32)


def _lowpass(x, cut):
    """One-pole low-pass; cut may be an array (a sweep)."""
    import numpy as np

    cut = np.broadcast_to(np.asarray(cut, np.float32), x.shape)
    a = 1 - np.exp(-2 * np.pi * cut / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def sfx_bank() -> dict:
    import numpy as np

    def tone(f, d, decay, amp=1.0, f_end=None):
        n = int(d * SR)
        t = np.arange(n) / SR
        ff = f if f_end is None else f * (f_end / f) ** (t / d)
        ph = 2 * np.pi * np.cumsum(ff) / SR
        return (amp * np.sin(ph) * np.exp(-t * decay) * np.minimum(1, t / 0.002)).astype(np.float32)

    def mixa(*xs):
        out = np.zeros(max(len(x) for x in xs), np.float32)
        for x in xs:
            out[:len(x)] += x
        return out

    n = int(0.42 * SR)
    t = np.arange(n) / SR
    sweep = 300 + 5200 * np.sin(np.pi * t / 0.42) ** 2
    whoosh = _lowpass(_noise(n, 1), sweep) * (np.sin(np.pi * t / 0.42) ** 1.5) * 1.6
    whoosh = whoosh - _lowpass(whoosh, 180)
    pop = mixa(tone(520, 0.16, 26, 0.9, 980), tone(1040, 0.08, 40, 0.25))
    tick = mixa(tone(1800, 0.05, 90, 0.55), _lowpass(_noise(int(0.02 * SR), 3), 6000) * _env(int(0.02 * SR), 0.001, 0.004) * 0.5)
    tick = np.concatenate([tick, np.zeros(max(0, int(0.05 * SR) - len(tick)), np.float32)])[: int(0.05 * SR)]
    click = tone(1300, 0.06, 70, 0.4, 900)
    ding = np.zeros(int(1.4 * SR), np.float32)
    for f, dl, amp in ((1046.5, 0.0, 0.5), (1318.5, 0.09, 0.45), (1568.0, 0.18, 0.5)):
        s = mixa(tone(f, 1.2, 3.2, amp), tone(f * 2.01, 0.6, 6, amp * 0.25), tone(f * 3.0, 0.3, 10, amp * 0.1))
        i = int(dl * SR)
        ding[i:i + len(s)] += s[: len(ding) - i]
    m = int(0.2 * SR)
    sq = lambda f, d: (np.sign(np.sin(2 * np.pi * f * np.arange(int(d * SR)) / SR)) * 0.5).astype(np.float32)
    buzz = np.concatenate([_lowpass(sq(233, 0.17), 1400) * _env(int(0.17 * SR), 0.004, 0.2),
                           np.zeros(int(0.03 * SR), np.float32),
                           _lowpass(sq(175, 0.32), 1200) * _env(int(0.32 * SR), 0.004, 0.25)]) * 1.4
    thud = tone(90, 0.5, 8, 1.0, 45) + _lowpass(_noise(int(0.5 * SR), 5), 400) * _env(int(0.5 * SR), 0.002, 0.06) * 0.8
    impact = thud * 0.9
    rise_n = int(0.6 * SR)
    rt = np.arange(rise_n) / SR
    rise = _lowpass(_noise(rise_n, 9), 400 + 6000 * (rt / 0.6) ** 2) * (rt / 0.6) ** 2 * 0.9
    chime = mixa(tone(1318.5, 0.9, 4, 0.45), tone(1975.5, 0.7, 5, 0.3))
    return {"whoosh": whoosh, "pop": pop, "tick": tick, "click": click, "ding": ding, "buzz": buzz,
            "thud": thud, "impact": impact, "rise": rise, "chime": chime}


def _music(total: float):
    """A soft plucked loop (the explainer reels' tune), at SR."""
    import numpy as np

    from .cartoon_video import SR as KSR, music

    try:
        m = music(total)
    except Exception:
        return np.zeros(int(total * SR), np.float32)
    return resample(np.asarray(m, np.float32), KSR, SR)


def mix(events: list[dict], plan: dict, total: float, with_music: bool = True):
    import numpy as np

    n = int((total + 0.5) * SR)
    voice = np.zeros(n, np.float32)
    fx = np.zeros(n, np.float32)

    def add(buf, sig, at, gain=1.0):
        s = int(max(0.0, at) * SR)
        if s >= n:
            return
        seg = sig[: n - s]
        buf[s:s + len(seg)] += seg * gain

    for ev in events:
        if ev["audio"] is not None:
            add(voice, ev["audio"], ev["start"])
    B = sfx_bank()
    pe = plan["events"]
    for i, e in enumerate(pe):
        kind = (e["card"] or {}).get("kind")
        if e["group"] and (i == 0 or pe[i - 1]["group"] != e["group"]):
            add(fx, B["impact"] if i == 0 else B["whoosh"], e["start"] - (0 if i == 0 else 0.12), 0.5 if i == 0 else 0.33)
        if kind == "attempt":
            add(fx, B["thud"], e["start"] + 0.35, 0.4)
        if kind == "trap":
            add(fx, B["thud"], e["start"] + 0.06, 0.5)
            add(fx, B["buzz"], e["start"] + 0.1, 0.22)
        if kind == "reveal":
            add(fx, B["rise"], e["start"] - 0.6, 0.25)
            add(fx, B["ding"], e["start"] + 0.12, 0.42)
        for r_i, at in enumerate(e.get("rowTimes") or []):
            if at > e["start"] + 0.15 and (i == 0 or at not in (pe[i - 1].get("rowTimes") or [])):
                add(fx, B["click"], at, 0.3)
        if e.get("countdown"):
            a, b = e["countdown"]
            for k in range(3):
                add(fx, B["tick"], a + k * (b - a) / 3, 0.45)
        if e.get("ctaAt") and (i == 0 or pe[i - 1].get("ctaAt") != e["ctaAt"]) and e["ctaAt"] < e["start"] + e["dur"]:
            add(fx, B["chime"], e["ctaAt"], 0.3)
        if e.get("prev") and e.get("cur") and e["prev"] != e["cur"]:
            add(fx, B["pop"], e["start"] + 0.35, 0.16)
    if plan.get("endAt") and plan.get("logo"):
        add(fx, B["whoosh"], plan["endAt"] - 0.1, 0.3)
        add(fx, B["chime"], plan["endAt"] + 0.15, 0.3)
    for k, at in enumerate(plan.get("optTimes") or []):
        add(fx, resample(B["pop"], SR, int(SR / (1 + 0.08 * k))), at, 0.3)

    out = voice * 1.0 + fx
    if with_music:
        mus = _music(total)[:n]
        mus = np.concatenate([mus, np.zeros(n - len(mus), np.float32)])
        env = np.sqrt(np.convolve(voice ** 2, np.ones(4800) / 4800, mode="same"))
        duck = 1 - 0.55 * np.clip(env / 0.05, 0, 1)
        fade = np.minimum(1, np.arange(n) / (0.6 * SR)) * np.minimum(1, (n - np.arange(n)) / (1.5 * SR))
        out += mus * 0.075 * duck * fade
    peak = float(np.abs(out).max()) or 1.0
    return np.clip(out / max(peak / 0.94, 1.0), -1, 1)


def write_wav(path: Path, a) -> None:
    import numpy as np

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())


# ── frames ──────────────────────────────────────────────────
QUALITY = "?scale=0.65&aa=0&sh=1024"   # 3D layer at 65% scaled up (2.4x faster, looks the same); text stays sharp


def _open_stage(p, plan: dict, errors: list):
    browser = p.chromium.launch(args=CHROME_ARGS)
    page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(STAGE.as_uri() + QUALITY)
    page.wait_for_function("window.ready === true", timeout=60000)
    page.evaluate("plan => window.load(plan)", plan)
    if errors:
        raise QT3DError("stage error: " + errors[0][:300])
    cdp = page.context.new_cdp_session(page)

    def shot(t: float, q: int = 93) -> bytes:
        import base64
        page.evaluate("t => window.seek(t)", t)
        r = cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": q, "optimizeForSpeed": True})
        return base64.b64decode(r["data"])
    return browser, shot


def _render_range(job: tuple) -> str:
    """One worker: frames n0..n1-1 of the plan into a silent H.264 file."""
    from playwright.sync_api import sync_playwright

    from .video import ffmpeg_path

    plan_path, n0, n1, out = job
    plan = json.loads(Path(plan_path).read_text())
    cmd = [ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg",
           "-framerate", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
           "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)]
    errors: list[str] = []
    with sync_playwright() as p:
        browser, shot = _open_stage(p, plan, errors)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for fi in range(n0, n1):
                proc.stdin.write(shot(fi / FPS))
                if errors:
                    raise QT3DError("stage error: " + errors[0][:300])
        finally:
            proc.stdin.close()
            proc.wait()
            browser.close()
    if proc.returncode:
        raise QT3DError("ffmpeg failed on a part of the reel")
    return str(out)


def workers() -> int:
    env = os.environ.get("QT3D_WORKERS")
    return max(1, int(env)) if env else max(1, min(4, (os.cpu_count() or 2)))


def render(script: dict, out: Path, cover: Path | None = None, handle: str = "", silent: bool = False,
           music: bool = True, frames: tuple[float, float] | None = None, n_workers: int | None = None,
           logo: Path | None = None, voice: str | None = None) -> dict:
    """Make the reel at `out`. silent=True skips the voice (timing estimated) for quick previews;
    frames=(t0, t1) renders only that stretch (for checking a scene)."""
    from playwright.sync_api import sync_playwright

    from .video import ffmpeg_path

    vl, voice_used = voice_lines(script, silent=silent, azure_voice=voice)
    events, total = timeline(script, vl)
    plan = make_plan(script, events, total, handle, logo)
    work = Path(tempfile.mkdtemp(prefix="qt3d_"))
    wav = work / "sound.wav"
    write_wav(wav, mix(events, plan, total, with_music=music))
    plan_path = work / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False))

    t0, t1 = frames or (0.0, total)
    n0, n1 = int(t0 * FPS), int(min(t1, total) * FPS)
    k = max(1, min(n_workers or workers(), (n1 - n0) // 60 or 1))
    cuts = [n0 + (n1 - n0) * i // k for i in range(k + 1)]
    jobs = [(str(plan_path), cuts[i], cuts[i + 1], str(work / f"part{i:02d}.mp4")) for i in range(k)]
    if k == 1:
        parts = [_render_range(jobs[0])]
    else:                                  # each part in its own Python process (python -m mcq_agent.qt3d part ...)
        procs = [subprocess.Popen([sys.executable, "-m", "mcq_agent.qt3d", "part", *map(str, j)], cwd=str(ROOT),
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for j in jobs]
        logs = [p.communicate()[0] for p in procs]
        bad = [(i, lg) for i, (p, lg) in enumerate(zip(procs, logs)) if p.returncode]
        if bad:
            raise QT3DError(f"part {bad[0][0]} failed: {bad[0][1][-400:]}")
        parts = [j[3] for j in jobs]
    lst = work / "parts.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    res = subprocess.run([ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                          "-i", str(lst), "-ss", f"{n0 / FPS:.3f}", "-i", str(wav), "-c:v", "copy", "-c:a", "aac",
                          "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    if res.returncode:
        raise QT3DError("ffmpeg could not join the reel: " + res.stderr[-200:])

    cover_t = next((e["start"] + 0.9 for e in plan["events"] if (e["card"] or {}).get("kind") == "trap"), None)
    if cover is not None and cover_t is not None:
        errors: list[str] = []
        with sync_playwright() as p:
            browser, shot = _open_stage(p, plan, errors)
            try:
                Path(cover).write_bytes(shot(cover_t, 92))
            finally:
                browser.close()
    return {"seconds": round(total, 1), "lines": len(events), "cover_ms": int(cover_t * 1000) if cover_t else None,
            "voice": voice_used}


if __name__ == "__main__":                 # a worker: python -m mcq_agent.qt3d part PLAN N0 N1 OUT
    if len(sys.argv) == 6 and sys.argv[1] == "part":
        _render_range((sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]))
    else:
        raise SystemExit("usage: python -m mcq_agent.qt3d part PLAN N0 N1 OUT")
