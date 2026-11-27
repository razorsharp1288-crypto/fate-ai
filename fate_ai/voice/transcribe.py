"""Speech-to-text engines.

* Cloud Whisper through a key you already connected (OpenAI ``whisper-1``, Groq ``whisper-large-v3-turbo``) — best
  accuracy; the audio is sent to that service.
* Windows offline dictation (System.Speech) — no internet, audio never leaves the PC, lower accuracy.
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass

import httpx

from ..core.exceptions import FateError

CLOUD_ENGINES = [  # (provider id, model, base url)
    ("groq", "whisper-large-v3-turbo", "https://api.groq.com/openai/v1"),
    ("openai", "whisper-1", "https://api.openai.com/v1"),
]


@dataclass
class Transcript:
    text: str
    engine: str


def cloud_engine(ctx) -> tuple[str, str, str] | None:
    for pid, model, url in CLOUD_ENGINES:
        if ctx.credentials.has_api_key(pid):
            cfg = ctx.provider_repo.get(pid)
            return pid, model, (cfg["base_url"] if cfg else url).rstrip("/")
    return None


def transcribe_cloud(ctx, wav: bytes, language: str = "", transport=None) -> Transcript:
    eng = cloud_engine(ctx)
    if not eng:
        raise FateError("No speech service connected. Add an OpenAI or Groq key on the API Keys page, or switch "
                        "voice to 'Windows (offline)' in Settings.")
    pid, model, base = eng
    key = ctx.credentials.get_api_key(pid)
    data = {"model": model, "response_format": "json"}
    if language:
        data["language"] = language
    with httpx.Client(timeout=120, transport=transport) as c:
        r = c.post(f"{base}/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                   files={"file": ("speech.wav", wav, "audio/wav")}, data=data)
    if r.status_code in (401, 403):
        raise FateError(f"{pid} rejected the key for speech-to-text.")
    if r.status_code >= 400:
        raise FateError(f"Speech-to-text failed ({r.status_code}): {r.text[:200]}")
    try:
        text = r.json().get("text", "")
    except ValueError:
        text = r.text
    return Transcript(text.strip(), f"{pid} {model}")


_WIN_STT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$r.SetInputToWaveFile($env:FATE_WAV)
$out = @()
while ($true) { $res = $r.Recognize(); if ($null -eq $res) { break }; $out += $res.Text }
$r.Dispose()
[Console]::OutputEncoding = [Text.Encoding]::UTF8
($out -join ' ')
"""


def transcribe_windows(wav: bytes) -> Transcript:
    if sys.platform != "win32":
        raise FateError("Offline dictation uses Windows speech recognition and only works on Windows.")
    from ..utilities.proc import which, run
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="fate-voice-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(wav)
        exe = which("powershell") or "powershell.exe"
        env = dict(os.environ, FATE_WAV=path)
        r = run([exe, "-NoProfile", "-NonInteractive", "-Command", _WIN_STT], timeout=120, env=env)
        if not r.ok:
            raise FateError("Windows speech recognition failed. Install a speech language in Windows Settings → "
                            "Time & language → Speech. " + r.stderr.strip()[-200:])
        return Transcript(r.stdout.strip(), "Windows offline")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def transcribe(ctx, wav: bytes, engine: str = "auto", language: str = "") -> Transcript:
    if engine == "cloud" or (engine == "auto" and cloud_engine(ctx)):
        return transcribe_cloud(ctx, wav, language)
    if engine in ("auto", "windows"):
        return transcribe_windows(wav)
    raise FateError(f"Unknown voice engine: {engine}")
