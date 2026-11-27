"""Minimal WAV helpers (no external dependencies)."""
from __future__ import annotations

import array
import io
import struct
import wave


def float32_to_int16(data: bytes) -> bytes:
    floats = array.array("f")
    floats.frombytes(data[: len(data) // 4 * 4])
    ints = array.array("h", (max(-32768, min(32767, int(x * 32767))) for x in floats))
    return ints.tobytes()


def int32_to_int16(data: bytes) -> bytes:
    src = array.array("i")
    src.frombytes(data[: len(data) // 4 * 4])
    return array.array("h", (x >> 16 for x in src)).tobytes()


def to_mono(pcm16: bytes, channels: int) -> bytes:
    if channels <= 1:
        return pcm16
    s = array.array("h")
    s.frombytes(pcm16[: len(pcm16) // 2 * 2])
    return array.array("h", (sum(s[i:i + channels]) // channels for i in range(0, len(s) - channels + 1, channels))).tobytes()


def make_wav(pcm16_mono: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16_mono)
    return buf.getvalue()


def duration_s(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / float(w.getframerate() or 1)


def level(pcm16: bytes) -> float:
    """RMS level 0..1 of a PCM16 chunk (for the microphone meter)."""
    s = array.array("h")
    s.frombytes(pcm16[: len(pcm16) // 2 * 2])
    if not s:
        return 0.0
    step = max(1, len(s) // 2000)
    sample = s[::step]
    return min(1.0, (sum(x * x for x in sample) / len(sample)) ** 0.5 / 12000)


def header_ok(wav_bytes: bytes) -> bool:
    return len(wav_bytes) > 44 and wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE" and \
        struct.unpack("<H", wav_bytes[22:24])[0] == 1
