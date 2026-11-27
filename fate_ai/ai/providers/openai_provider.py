from __future__ import annotations

import json
from typing import Iterator

import httpx

from ...core.exceptions import ProviderError
from .base import (Cancelled, ChatRequest, ModelInfo, Provider, StreamChunk, iter_sse)

_NON_CHAT = ("embedding", "whisper", "tts", "dall-e", "moderation", "davinci", "babbage",
             "image", "transcribe", "realtime", "audio", "search")


def _mime(b64: str) -> str:
    return "image/jpeg" if b64.startswith("/9j/") else "image/png"


def parse_model_list(body, keep=lambda mid: True) -> list[ModelInfo]:
    """Accept every common model-list shape: {"data": [...]}, {"models": [...]}, {"result": [...]}, a bare list;
    entries as strings or objects with id / name / model / slug."""
    items = body
    if isinstance(body, dict):
        for k in ("data", "models", "result", "results", "items"):
            if isinstance(body.get(k), list):
                items = body[k]
                break
            if isinstance(body.get(k), dict) and isinstance(body[k].get("data"), list):
                items = body[k]["data"]
                break
        else:
            items = []
    out, seen = [], set()
    for m in items if isinstance(items, list) else []:
        if isinstance(m, str):
            mid, det = m, {}
        elif isinstance(m, dict):
            mid = m.get("id") or m.get("model") or m.get("name") or m.get("slug")
            det = {"owned_by": m.get("owned_by", "")} if m.get("owned_by") else {}
            if m.get("context_length") or m.get("context_window"):
                det["context"] = m.get("context_length") or m.get("context_window")
        else:
            continue
        if not mid or not isinstance(mid, str):
            continue
        mid = mid.removeprefix("models/")  # Google-style names
        if mid in seen or not keep(mid):
            continue
        seen.add(mid)
        out.append(ModelInfo(id=mid, name=mid, details=det))
    return out


class OpenAICompatibleProvider(Provider):
    """Any server implementing the OpenAI Chat Completions API (vLLM, LM Studio, llama.cpp, ...)."""

    kind = "openai_compatible"
    requires_key = False
    token_param = "max_tokens"

    def __init__(self, *args, options: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        o = options or {}
        if "requires_key" in o:
            self.requires_key = bool(o["requires_key"])
        self.raw_base = o.get("raw_base")
        self.auth_header = o.get("auth_header") or "Authorization"
        self.auth_scheme = o.get("auth_scheme", "Bearer")
        self.extra_headers = {str(k): str(v) for k, v in (o.get("headers") or {}).items()}

    def _headers(self) -> dict[str, str]:
        h = super()._headers()
        h.update(getattr(self, "extra_headers", {}))
        if self.api_key:
            header = getattr(self, "auth_header", "Authorization")
            scheme = getattr(self, "auth_scheme", "Bearer")
            h[header] = f"{scheme} {self.api_key}".strip()
        return h

    def _api_base(self) -> str:
        """``raw_base``: the URL already includes its version path (…/v1, /v1beta/openai, /api/paas/v4)."""
        raw = getattr(self, "raw_base", None)
        if raw is None:  # custom URL: use it as-is if it ends in a version segment, else assume /v1
            import re
            raw = bool(re.search(r"/v\d+[a-z]*(/openai)?$", self.base_url)) or self.base_url.endswith("/openai")
        return self.base_url if raw else f"{self.base_url}/v1"

    def _models_url(self) -> str:
        return f"{self._api_base()}/models"

    def _chat_url(self) -> str:
        return f"{self._api_base()}/chat/completions"

    def _filter_model(self, mid: str) -> bool:
        return True

    def list_models(self) -> list[ModelInfo]:
        try:
            with self._client(20) as c:
                r = c.get(self._models_url())
                self.raise_for_status(r)
                try:
                    body = r.json()
                except ValueError:
                    from ...core.exceptions import ProviderError
                    raise ProviderError("The service's model list is not JSON.") from None
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None
        return sorted(parse_model_list(body, self._filter_model), key=lambda m: m.id)

    def _payload(self, req: ChatRequest, include_temperature: bool = True) -> dict:
        msgs = []
        if req.system:
            msgs.append({"role": "system", "content": req.system})
        for m in req.messages:
            if m.images:
                parts = [{"type": "text", "text": m.content}] + [
                    {"type": "image_url", "image_url": {"url": f"data:{_mime(b)};base64,{b}"}} for b in m.images]
                msgs.append({"role": m.role, "content": parts})
            else:
                msgs.append({"role": m.role, "content": m.content})
        p = {"model": req.model, "messages": msgs, "stream": True,
             "stream_options": {"include_usage": True}, self.token_param: req.max_tokens}
        if include_temperature and req.temperature is not None:
            p["temperature"] = req.temperature
        return p

    def stream_chat(self, req: ChatRequest, cancel=None) -> Iterator[StreamChunk]:
        try:
            yield from self._stream(req, include_temperature=True, cancel=cancel)
        except ProviderError as e:
            # Some reasoning models reject custom temperature; retry once without it.
            if "temperature" in str(e).lower() and "unsupported" in str(e).lower():
                yield from self._stream(req, include_temperature=False, cancel=cancel)
            else:
                raise

    def _stream(self, req: ChatRequest, include_temperature: bool, cancel) -> Iterator[StreamChunk]:
        usage_in = usage_out = None
        try:
            with self._client(300) as c, c.stream("POST", self._chat_url(),
                                                   json=self._payload(req, include_temperature)) as r:
                self.raise_for_status(r)
                for _event, data in iter_sse(r):
                    if cancel is not None and cancel.cancelled:
                        raise Cancelled()
                    if data.strip() == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        raise ProviderError(str(obj["error"].get("message", obj["error"])))
                    if obj.get("usage"):
                        usage_in = obj["usage"].get("prompt_tokens")
                        usage_out = obj["usage"].get("completion_tokens")
                    for ch in obj.get("choices") or []:
                        text = (ch.get("delta") or {}).get("content")
                        if text:
                            yield StreamChunk(text=text)
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None
        yield StreamChunk(done=True, input_tokens=usage_in, output_tokens=usage_out)


class OpenAIProvider(OpenAICompatibleProvider):
    kind = "openai"
    requires_key = True
    token_param = "max_completion_tokens"
    DEFAULT_URL = "https://api.openai.com/v1"

    def _filter_model(self, mid: str) -> bool:
        low = mid.lower()
        return not any(t in low for t in _NON_CHAT)


class LlamaCppProvider(OpenAICompatibleProvider):
    """llama.cpp ``llama-server`` exposes an OpenAI-compatible API on port 8080."""

    kind = "llamacpp"
    is_local = True
    requires_key = False

    def health(self) -> bool:
        try:
            with self._client(5) as c:
                return c.get(f"{self.base_url}/health").status_code == 200
        except httpx.HTTPError:
            return False
