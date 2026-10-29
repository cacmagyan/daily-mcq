"""Free voice for the explainer reels: the open Kokoro-82M voice model (Apache 2.0), run on the CPU with
onnxruntime, with phonemes from espeak-ng. No key, no account and no card.

On GitHub the workflow installs espeak-ng and keeps the model files (about 340 MB, downloaded once from
the kokoro-onnx release on GitHub) in its cache. Locally: install espeak-ng and set KOKORO_DIR to a
folder with kokoro-v1.0.onnx and voices-v1.0.bin (they are downloaded there if missing).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

from .config import ROOT

SR = 24000
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = {"kokoro-v1.0.onnx": 300_000_000, "voices-v1.0.bin": 25_000_000}   # name -> smallest valid size
MAX_PHONEMES = 500
PUNCT = r'([;:,.!?—…"“”()])'


class VoiceError(RuntimeError):
    pass


def model_dir() -> Path:
    return Path(os.environ.get("KOKORO_DIR") or ROOT / ".kokoro")


def ensure_model() -> Path:
    """The folder with both model files, downloading what is missing."""
    import requests

    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name, smallest in FILES.items():
        path = d / name
        if path.exists() and path.stat().st_size >= smallest:
            continue
        tmp = path.with_suffix(".part")
        try:
            with requests.get(f"{RELEASE}/{name}", stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
        except requests.RequestException as exc:
            raise VoiceError(f"couldn't download the voice model ({name}): {exc}") from None
        if tmp.stat().st_size < smallest:
            tmp.unlink(missing_ok=True)
            raise VoiceError(f"the voice model download ({name}) was incomplete")
        tmp.replace(path)
    return d


def _espeak() -> str:
    exe = os.environ.get("ESPEAK_NG") or shutil.which("espeak-ng")
    if not exe:
        raise VoiceError("espeak-ng is not installed (on GitHub the workflow installs it; locally: sudo apt install espeak-ng)")
    return exe


def _vocab() -> dict:
    with open(Path(__file__).parent / "kokoro_vocab.json", encoding="utf-8") as fh:
        return json.load(fh)["vocab"]


_VOCAB: dict | None = None


def _ipa(text: str, lang: str) -> str:
    out = subprocess.run([_espeak(), "-q", "--ipa", "-v", lang, text], capture_output=True, text=True,
                         timeout=60, check=True).stdout
    return " ".join(out.split())


def phonemize(text: str, lang: str = "en-us") -> str:
    """espeak phonemes with punctuation kept (it shapes the voice's pauses); [[...]] is passed through
    as ready-made phonemes (for names espeak says wrongly)."""
    global _VOCAB
    _VOCAB = _VOCAB or _vocab()
    parts = re.split(r"(\[\[[^\]]+\]\])", text)
    out = ""
    for part in parts:
        if part.startswith("[["):
            out += part[2:-2] + " "
            continue
        for piece in re.split(PUNCT, part):
            if not piece.strip():
                continue
            if re.fullmatch(PUNCT, piece):
                out = out.rstrip() + piece + " "
            else:
                out += _ipa(piece, lang) + " "
    return "".join(c for c in " ".join(out.split()) if c in _VOCAB)


class Voice:
    """One loaded model; synth() is called once per scene."""

    def __init__(self):
        import numpy as np
        import onnxruntime as rt

        d = ensure_model()
        opts = rt.SessionOptions()
        opts.log_severity_level = 3
        self.np = np
        self.sess = rt.InferenceSession(str(d / "kokoro-v1.0.onnx"), opts, providers=["CPUExecutionProvider"])
        self.voices = np.load(d / "voices-v1.0.bin")

    def synth(self, text: str, voice: str = "af_heart", speed: float = 1.0, lang: str = "en-us"):
        np = self.np
        if voice not in self.voices:
            raise VoiceError(f"unknown voice '{voice}'")
        ph = phonemize(text, lang)
        if not ph:
            raise VoiceError(f"nothing to say in {text!r}")
        if len(ph) > MAX_PHONEMES:            # very long line: say it in two halves
            cut = max(ph.rfind(", ", 0, MAX_PHONEMES), ph.rfind(". ", 0, MAX_PHONEMES), ph.rfind(" ", 0, MAX_PHONEMES))
            return np.concatenate([self._run(ph[:cut + 1], voice, speed), np.zeros(int(0.12 * SR), np.float32),
                                   self._run(ph[cut + 1:].strip(), voice, speed)])
        return self._run(ph, voice, speed)

    def _run(self, ph: str, voice: str, speed: float):
        np = self.np
        tokens = [_VOCAB[c] for c in ph]
        style = self.voices[voice][len(tokens) - 1]
        audio = self.sess.run(None, {"tokens": np.array([[0, *tokens, 0]], dtype=np.int64),
                                     "style": style.astype(np.float32),
                                     "speed": np.array([speed], dtype=np.float32)})[0]
        return np.asarray(audio, dtype=np.float32).ravel()


def save_wav(audio, path: Path, sr: int = SR) -> None:
    import numpy as np

    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def available() -> str:
    """Empty if the voice can run here, else why not."""
    try:
        _espeak()
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
    except (VoiceError, ImportError) as exc:
        return str(exc)
    return ""
