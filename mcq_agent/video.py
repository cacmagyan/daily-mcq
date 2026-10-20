"""Turns the reel's frames into an Instagram-ready MP4: H.264 + AAC, 1080x1920, 30 fps.

The sound is made here too (no music licences needed): a soft tick on every second of the
countdown, higher for the last three, and a short chime when the answer shows.
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

RATE = 48000


class VideoError(RuntimeError):
    pass


def ffmpeg_path() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:                                  # optional pip fallback: imageio-ffmpeg ships its own ffmpeg
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                     # noqa: BLE001 - any failure means "not available"
        raise VideoError("ffmpeg is not installed, so the reel video can't be made "
                         "(on GitHub the workflow installs it; locally: sudo apt install ffmpeg)") from None


# ── sound ───────────────────────────────────────────────────────────────────

def _tick(buf: list[float], at: float, freq: float, amp: float) -> None:
    """A short wood-block style tick: a sine with a fast decay."""
    start, n = int(at * RATE), int(0.07 * RATE)
    for i in range(n):
        j = start + i
        if j >= len(buf):
            break
        t = i / RATE
        env = math.exp(-t / 0.011)
        buf[j] += amp * env * (math.sin(2 * math.pi * freq * t) + 0.35 * math.sin(2 * math.pi * freq * 0.5 * t))


def _chime(buf: list[float], at: float) -> None:
    """Three rising bell notes (C6, E6, G6) when the answer shows."""
    for k, freq in enumerate((1046.5, 1318.5, 1568.0)):
        start, n = int((at + 0.085 * k) * RATE), int(1.3 * RATE)
        for i in range(n):
            j = start + i
            if j >= len(buf):
                break
            t = i / RATE
            env = math.exp(-t / 0.32) * min(1.0, t / 0.004)
            buf[j] += 0.2 * env * (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(2 * math.pi * 2 * freq * t))


def _read_voice(path: Path) -> list[float]:
    """Samples of a 48 kHz mono 16-bit WAV, as floats."""
    from array import array

    with wave.open(str(path)) as w:
        if w.getframerate() != RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise VideoError("voice audio must be 48 kHz mono 16-bit")
        data = array("h")
        data.frombytes(w.readframes(w.getnframes()))
    return [v / 32768.0 for v in data]


def make_sound(path: Path, think: float, total: float, clips: list[tuple[float, Path]] = ()) -> Path:
    """16-bit 48 kHz stereo WAV: ticks at 0, 1, ... think-1 seconds, chime at `think`, and the voice
    clips (start second, WAV) on top. Ticks under the voice are made quieter."""
    buf = [0.0] * int(math.ceil(total * RATE))
    voices = [(start, _read_voice(p)) for start, p in clips]
    spans = [(start, start + len(v) / RATE) for start, v in voices]
    whole = int(round(think))
    for s in range(whole):
        last_three = s >= whole - 3
        quiet = 0.4 if any(a - 0.1 <= s <= b for a, b in spans) else 1.0
        _tick(buf, s, 1480.0 if last_three else 1040.0, (0.30 if last_three else 0.24) * quiet)
    _chime(buf, think)
    for start, v in voices:
        j0 = int(start * RATE)
        for i, x in enumerate(v):
            if j0 + i >= len(buf):
                break
            buf[j0 + i] += 0.95 * x
    peak = max(1e-9, max(abs(x) for x in buf))
    gain = min(1.0, 0.89 / peak)
    frames = bytearray()
    for x in buf:
        v = int(max(-1.0, min(1.0, x * gain)) * 32767)
        frames += struct.pack("<hh", v, v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))
    return path


# ── video ───────────────────────────────────────────────────────────────────

def encode(frames: list[tuple[Path, float]], sound: Path, out: Path, total: float) -> Path:
    """frames: (image, seconds on screen) in order. Writes `out` and returns it."""
    if not frames:
        raise VideoError("no frames to encode")
    work = out.parent / (out.stem + "_frames.txt")
    lines = []
    for img, secs in frames:
        lines += [f"file '{img.resolve().as_posix()}'", f"duration {secs:.4f}"]
    lines.append(f"file '{frames[-1][0].resolve().as_posix()}'")      # the concat reader needs the last one twice
    work.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(work),
        "-i", str(sound),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "fps=30,scale=1080:1920:out_color_matrix=bt709:out_range=tv,format=yuv420p",
        # Instagram's Reels spec: H.264 high, progressive, closed GOP, 30 fps, AAC 48 kHz,
        # moov atom at the front, no edit lists.
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high", "-level:v", "4.1",
        "-bf", "0", "-g", "60", "-r", "30",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
        "-c:a", "aac", "-b:a", "128k", "-ar", str(RATE), "-ac", "2",
        "-t", f"{total:.3f}", "-movflags", "+faststart", "-use_editlist", "0",
        str(out),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise VideoError("ffmpeg took too long") from None
    finally:
        work.unlink(missing_ok=True)
    if res.returncode != 0 or not out.exists() or out.stat().st_size < 10_000:
        raise VideoError(f"ffmpeg failed: {(res.stderr or '').strip()[-400:]}")
    return out


def probe(path: Path) -> dict:
    """Duration, size and codecs of a video (needs ffprobe; empty if it isn't there)."""
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    res = subprocess.run([exe, "-v", "error", "-show_entries",
                          "format=duration:stream=codec_name,width,height,r_frame_rate,sample_rate",
                          "-of", "json", str(path)], capture_output=True, text=True)
    import json
    try:
        return json.loads(res.stdout or "{}")
    except ValueError:
        return {}
