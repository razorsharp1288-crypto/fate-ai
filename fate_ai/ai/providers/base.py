"""Provider-neutral interfaces for chat-capable AI backends."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Literal

import httpx

from ...core.exceptions import (AuthenticationError, ProviderError, ProviderUnavailableError,
                                RateLimitError)
from ...security.redaction import redact

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class ChatRequest:
    model: str
    messages: list[ChatMessage]
    system: str = ""
    temperature: float | None = 0.7
    max_tokens: int = 2048


@dataclass
class StreamChunk:
    text: str = ""
    done: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class ModelInfo:
    id: str
    name: str = ""
    size_bytes: int | None = None
    context_window: int | None = None
    details: dict = field(default_factory=dict)


@dataclass
class ConnectionResult:
    ok: bool
    message: str
    latency_ms: int | None = None
    model_count: int | None = None


class Cancelled(Exception):
    pass


class Provider(ABC):
    """A configured provider instance."""

    kind: str = ""
    is_local: bool = False
    requires_key: bool = True
    supports_streaming: bool = True

    def __init__(self, provider_id: str, base_url: str, api_key: str | None = None,
                 timeout: float = 60.0, transport: httpx.BaseTransport | None = None):
        self.id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._transport = transport

    # -- helpers -------------------------------------------------------------
    def _client(self, timeout: float | None = None) -> httpx.Client:
        t = httpx.Timeout(timeout or self.timeout, connect=10.0)
        return httpx.Client(timeout=t, transport=self._transport, headers=self._headers(),
                            follow_redirects=False)

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": "FateAI-Desktop"}

    @staticmethod
    def raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        try:
            body = resp.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        detail = ""
        try:
            data = json.loads(body)
            err = data.get("error", data)
            detail = err.get("message") if isinstance(err, dict) else str(err)
        except Exception:
            detail = body[:300]
        detail = redact(detail or resp.reason_phrase)
        code = resp.status_code
        if code in (401, 403):
            raise AuthenticationError(f"Authentication failed ({code}): {detail}")
        if code == 429:
            ra = resp.headers.get("retry-after")
            raise RateLimitError(f"Rate limited: {detail}", float(ra) if ra and ra.replace('.', '', 1).isdigit() else None)
        if code >= 500:
            raise ProviderUnavailableError(f"Provider error ({code}): {detail}")
        raise ProviderError(f"Request failed ({code}): {detail}")

    @staticmethod
    def wrap_network_errors(exc: Exception) -> ProviderError:
        if isinstance(exc, httpx.ConnectError):
            return ProviderUnavailableError("Could not connect. Is the server running and the URL correct?")
        if isinstance(exc, httpx.TimeoutException):
            return ProviderUnavailableError("The request timed out.")
        return ProviderError(redact(f"Network error: {exc}"))

    # -- API -----------------------------------------------------------------
    @abstractmethod
    def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    def stream_chat(self, req: ChatRequest, cancel=None) -> Iterator[StreamChunk]: ...

    def chat(self, req: ChatRequest) -> tuple[str, StreamChunk]:
        text, last = [], StreamChunk()
        for chunk in self.stream_chat(req):
            text.append(chunk.text)
            if chunk.done:
                last = chunk
        return "".join(text), last

    def test_connection(self) -> ConnectionResult:
        if self.requires_key and not self.api_key:
            return ConnectionResult(False, "No API key configured.")
        start = time.perf_counter()
        try:
            models = self.list_models()
        except ProviderError as e:
            return ConnectionResult(False, str(e))
        except httpx.HTTPError as e:
            return ConnectionResult(False, str(self.wrap_network_errors(e)))
        ms = int((time.perf_counter() - start) * 1000)
        return ConnectionResult(True, f"Connected — {len(models)} models available.", ms, len(models))


def iter_sse(resp: httpx.Response) -> Iterator[tuple[str, str]]:
    """Yield (event, data) pairs from a Server-Sent-Events response."""
    event, data = "message", []
    for line in resp.iter_lines():
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
            continue
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "event":
            event = value
        elif name == "data":
            data.append(value)
    if data:
        yield event, "\n".join(data)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) used when a provider reports no usage."""
    return max(1, len(text) // 4) if text else 0
