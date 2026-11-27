import json
import struct

import httpx
import pytest

from fate_ai.ai.providers.anthropic_provider import AnthropicProvider
from fate_ai.ai.providers.base import ChatMessage, ChatRequest
from fate_ai.ai.providers.ollama_provider import OllamaProvider
from fate_ai.ai.providers.openai_provider import OpenAICompatibleProvider
from fate_ai.core.exceptions import FateError
from fate_ai.voice import wav
from fate_ai.voice.speak import clean_for_speech
from fate_ai.voice.transcribe import cloud_engine, transcribe_cloud

PNG = "iVBORw0KGgo="
REQ = ChatRequest("m", [ChatMessage("user", "what is this?", [PNG])])


def capture(resp_body: bytes):
    seen = {}

    def handler(req):
        seen["json"] = json.loads(req.content)
        return httpx.Response(200, content=resp_body)
    return seen, httpx.MockTransport(handler)


def test_openai_vision_payload():
    seen, t = capture(b"data: [DONE]\n\n")
    list(OpenAICompatibleProvider("x", "http://h/v1", transport=t).stream_chat(REQ))
    content = seen["json"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "what is this?"}
    assert content[1]["image_url"]["url"] == f"data:image/png;base64,{PNG}"


def test_anthropic_vision_payload():
    seen, t = capture(b'event: message_stop\ndata: {"type":"message_stop"}\n\n')
    list(AnthropicProvider("a", "https://api.anthropic.com", "k" * 12, transport=t).stream_chat(REQ))
    blocks = seen["json"]["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["data"] == PNG
    assert blocks[1] == {"type": "text", "text": "what is this?"}


def test_ollama_vision_payload():
    seen, t = capture(b'{"done": true}\n')
    list(OllamaProvider("o", "http://h", transport=t).stream_chat(REQ))
    assert seen["json"]["messages"][0]["images"] == [PNG]


def test_wav_helpers():
    floats = struct.pack("<4f", 0.0, 0.5, -0.5, 1.0)
    pcm = wav.float32_to_int16(floats)
    assert struct.unpack("<4h", pcm) == (0, 16383, -16383, 32767)
    stereo = struct.pack("<4h", 100, 300, -100, -300)
    assert struct.unpack("<2h", wav.to_mono(stereo, 2)) == (200, -200)
    w = wav.make_wav(b"\x00\x00" * 16000, 16000)
    assert wav.header_ok(w) and wav.duration_s(w) == pytest.approx(1.0)
    assert wav.level(b"\x00\x00" * 100) == 0


def test_cloud_transcription_prefers_groq(ctx):
    assert cloud_engine(ctx) is None
    with pytest.raises(FateError):
        transcribe_cloud(ctx, b"RIFF")
    ctx.credentials.set_api_key("openai", "sk-proj-" + "a" * 20)
    ctx.providers.add_preset("groq")
    ctx.credentials.set_api_key("groq", "gsk_" + "b" * 20)
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["body"] = req.content
        return httpx.Response(200, json={"text": " hello there "})
    t = transcribe_cloud(ctx, wav.make_wav(b"\x00\x00" * 8000, 16000), transport=httpx.MockTransport(handler))
    assert t.text == "hello there" and "groq" in t.engine
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer gsk_" + "b" * 20
    assert b"whisper-large-v3-turbo" in seen["body"] and b"speech.wav" in seen["body"]


def test_clean_for_speech():
    s = clean_for_speech("**Hi!** Here is code:\n```python\nprint(1)\n```\nSee [docs](https://x.y) and `x`.")
    assert "print" not in s and "code omitted" in s and "docs" in s and "*" not in s and "https" not in s
