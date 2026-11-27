"""Read replies aloud with the OS voices (Qt TextToSpeech → Windows SAPI/OneCore voices)."""
from __future__ import annotations

import re

_tts = None


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " (code omitted) ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#*_>|~]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:4000]


def engine():
    global _tts
    if _tts is None:
        from PySide6.QtTextToSpeech import QTextToSpeech
        _tts = QTextToSpeech()
    return _tts


def voices() -> list[str]:
    try:
        return [v.name() for v in engine().availableVoices()]
    except Exception:
        return []


def speak(text: str, voice: str = "", rate: float = 0.0) -> bool:
    try:
        t = engine()
        if voice:
            for v in t.availableVoices():
                if v.name() == voice:
                    t.setVoice(v)
                    break
        t.setRate(max(-1.0, min(1.0, rate)))
        t.say(clean_for_speech(text))
        return True
    except Exception:
        return False


def stop() -> None:
    if _tts is not None:
        _tts.stop()
