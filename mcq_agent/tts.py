"""AI voiceover for the reel, from an official text-to-speech service (both have free monthly tiers):

  Azure Speech                 secrets AZURE_SPEECH_KEY and AZURE_SPEECH_REGION (e.g. centralindia)
  Google Cloud Text-to-Speech  secret GOOGLE_TTS_API_KEY

With neither secret the reel simply has no voice (ticks and a chime only). A voice problem never
stops a reel: it is made without the voice and the day's report says why.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import wave
from pathlib import Path
from xml.sax.saxutils import escape

import requests

DEFAULT_VOICES = {"azure": "en-IN-PrabhatNeural", "google": "en-IN-Neural2-B"}


class TTSError(RuntimeError):
    pass


def _voice_cfg(cfg) -> dict:
    return (cfg.reels.get("voice") or {}) if hasattr(cfg, "reels") else {}


def provider(cfg) -> str | None:
    """'azure', 'google' or None (no voice)."""
    v = _voice_cfg(cfg)
    if not v.get("enabled", False):
        return None
    want = str(v.get("provider") or "auto").lower()
    has_azure = bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))
    has_google = bool(os.environ.get("GOOGLE_TTS_API_KEY"))
    if want == "azure":
        return "azure" if has_azure else None
    if want == "google":
        return "google" if has_google else None
    return "azure" if has_azure else "google" if has_google else None


def voice_for(cfg, prov: str, author: str) -> str:
    voices = (_voice_cfg(cfg).get("voices") or {}).get(prov) or {}
    return str(voices.get(author) or DEFAULT_VOICES[prov])


# ── text a voice can read ────────────────────────────────────────────────────

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _below_1000(n: int) -> str:
    words = []
    if n >= 100:
        words += [_ONES[n // 100], "hundred"]
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else ""))
    elif n or not words:
        words.append(_ONES[n])
    return " ".join(words)


def indian_words(n: int) -> str:
    """1,45,800 -> 'one lakh forty-five thousand eight hundred' (Indian system: lakh, crore)."""
    if n < 0:
        return "minus " + indian_words(-n)
    if n == 0:
        return "zero"
    parts = []
    for size, name in ((10 ** 7, "crore"), (10 ** 5, "lakh"), (1000, "thousand")):
        if n >= size:
            parts.append(f"{indian_words(n // size) if size == 10 ** 7 else _below_1000(n // size)} {name}")
            n %= size
    if n:
        parts.append(_below_1000(n))
    return " ".join(parts)


def _number(raw: str) -> str:
    raw = raw.replace(",", "")
    if "." in raw:
        whole, frac = raw.split(".", 1)
        return f"{indian_words(int(whole or 0))} point {' '.join(_ONES[int(d)] for d in frac)}"
    return indian_words(int(raw))


_SWAPS = [
    (r"√\s*\(", "the square root of ("), (r"√", "the square root of "), (r"÷", " divided by "), (r"×", " times "),
    (r"\s=\s|=", " equals "), (r"≈", " about "), (r"≥", " at least "), (r"≤", " at most "), (r"\s[–—]\s", ", "),
    (r"%", " percent"), (r"\bp\.a\.", "per annum"),
    (r"\bu/s\b", "under section"), (r"\bi\.e\.", "that is"), (r"\be\.g\.", "for example"), (r"&", " and "),
    (r"\bInd AS\b", "Ind A S"), (r"\bAS\b", "A S"), (r"\bSA\b", "S A"), (r"\bv\.\s", "versus "),
    (r"\bvs\.?\s", "versus "), (r"\bRs\.?\s*", "₹"), (r"\bFY\s", "financial year "), (r"\bA\.Y\.\s*", "assessment year "),
    (r"[()\[\]{}]", " "), (r"\s*[:;]\s*", ", "), (r"\s*/\s*", " per "),
]


def speakable(text: str) -> str:
    """Written MCQ text -> words a voice reads naturally: rupee amounts, Indian-format numbers and
    symbols spelt out. '₹10,00,000' -> 'ten lakh rupees'."""
    t = (text or "").replace("==", "").replace("!!", "")
    # arithmetic signs between amounts, before the amounts become words
    t = re.sub(r"(?<=[\d)])\s*[−–]\s*(?=[₹\d(√])|(?<=[\d)])\s+-\s+(?=[₹\d(√])", " minus ", t)
    t = re.sub(r"(?<=[\d)])\s*\+\s*(?=[₹\d(√])", " plus ", t)
    t = re.sub(r"(?:^|(?<=\s))[−-](?=₹?\d)", "minus ", t)
    t = re.sub(r"(\d)\^?([²³])", lambda m: m.group(1) + (" squared" if m.group(2) == "²" else " cubed"), t)

    def rupees(m):
        amount = _number(m.group(1))
        scale = m.group(2) or ""
        return f"{amount} {scale + ' ' if scale else ''}rupees"
    t = re.sub(r"₹\s*(\d+(?:,\d+)*(?:\.\d+)?)(?:\s*(lakh|lakhs|crore|crores)\b)?", rupees, t, flags=re.I)
    t = re.sub(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?", lambda m: _number(m.group(0)), t)   # 20,000 / 10,00,000
    for pat, rep in _SWAPS:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\s+([.,!?])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


# ── calling the service ──────────────────────────────────────────────────────

def _redact(text: str) -> str:
    out = str(text)
    for key in ("AZURE_SPEECH_KEY", "GOOGLE_TTS_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            out = out.replace(secret, "***")
    return out[:300]


def _azure(text: str, voice: str, speed: float) -> bytes:
    region = os.environ["AZURE_SPEECH_REGION"].strip()
    rate = f"{round((speed - 1) * 100):+d}%"
    ssml = (f"<speak version='1.0' xml:lang='en-IN'><voice name='{escape(voice)}'>"
            f"<prosody rate='{rate}'>{escape(text)}</prosody></voice></speak>")
    r = requests.post(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"),
                      headers={"Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"].strip(),
                               "Content-Type": "application/ssml+xml",
                               "X-Microsoft-OutputFormat": "riff-48khz-16bit-mono-pcm",
                               "User-Agent": "mcq-agent"}, timeout=60)
    if r.status_code != 200 or not r.content:
        raise TTSError(f"Azure voice {voice}: HTTP {r.status_code} {_redact(r.text)}")
    return r.content


def _google(text: str, voice: str, speed: float) -> bytes:
    lang = "-".join(voice.split("-")[:2]) or "en-IN"
    r = requests.post("https://texttospeech.googleapis.com/v1/text:synthesize",
                      headers={"X-Goog-Api-Key": os.environ["GOOGLE_TTS_API_KEY"].strip()},
                      json={"input": {"text": text}, "voice": {"languageCode": lang, "name": voice},
                            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 48000, "speakingRate": speed}},
                      timeout=60)
    try:
        audio = r.json().get("audioContent", "") if r.ok else ""
    except ValueError:
        audio = ""
    if not audio:
        raise TTSError(f"Google voice {voice}: HTTP {r.status_code} {_redact(r.text)}")
    return base64.b64decode(audio)


def synthesize(cfg, text: str, author: str, dest: Path) -> tuple[Path, str]:
    """Speaks `text` in the author's voice into a 48 kHz mono WAV. Returns (path, voice used).
    If the chosen voice is refused, the service's default Indian English voice is tried once."""
    from .video import ffmpeg_path

    prov = provider(cfg)
    if not prov:
        raise TTSError("no voice key")
    speed = float(_voice_cfg(cfg).get("speed", 1.05))
    call = _azure if prov == "azure" else _google
    voice = voice_for(cfg, prov, author)
    spoken = speakable(text)
    try:
        audio = call(spoken, voice, speed)
    except (TTSError, requests.RequestException) as exc:
        if voice == DEFAULT_VOICES[prov]:
            raise TTSError(_redact(exc)) from None
        voice = DEFAULT_VOICES[prov]
        try:
            audio = call(spoken, voice, speed)
        except requests.RequestException as exc2:
            raise TTSError(_redact(exc2)) from None
    raw = dest.with_suffix(".raw.wav")
    raw.write_bytes(audio)
    res = subprocess.run([ffmpeg_path(), "-y", "-loglevel", "error", "-i", str(raw), "-ar", "48000", "-ac", "1",
                          "-sample_fmt", "s16", str(dest)], capture_output=True, text=True)
    raw.unlink(missing_ok=True)
    if res.returncode != 0:
        raise TTSError(f"could not read the voice audio: {res.stderr[-200:]}")
    return dest, f"{voice} ({'Azure' if prov == 'azure' else 'Google'})"


def seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate())
