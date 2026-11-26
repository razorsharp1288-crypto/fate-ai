from __future__ import annotations

import json
from typing import Iterator

import httpx

from ...core.exceptions import ProviderError, ProviderUnavailableError
from .base import Cancelled, ChatRequest, ModelInfo, Provider, StreamChunk, iter_sse

API_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    kind = "anthropic"
    requires_key = True
    DEFAULT_URL = "https://api.anthropic.com"

    def _headers(self) -> dict[str, str]:
        h = super()._headers()
        h["anthropic-version"] = API_VERSION
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def list_models(self) -> list[ModelInfo]:
        out: list[ModelInfo] = []
        params = {"limit": 100}
        try:
            with self._client(20) as c:
                while True:
                    r = c.get(f"{self.base_url}/v1/models", params=params)
                    self.raise_for_status(r)
                    body = r.json()
                    for m in body.get("data", []):
                        out.append(ModelInfo(id=m["id"], name=m.get("display_name", m["id"]),
                                             details={"created_at": m.get("created_at", "")}))
                    if not body.get("has_more") or not body.get("last_id"):
                        break
                    params = {"limit": 100, "after_id": body["last_id"]}
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None
        return out

    def stream_chat(self, req: ChatRequest, cancel=None) -> Iterator[StreamChunk]:
        # Anthropic requires alternating user/assistant turns starting with user;
        # merge consecutive same-role messages to be safe.
        msgs: list[dict] = []
        for m in req.messages:
            if m.role == "system":
                continue
            if msgs and msgs[-1]["role"] == m.role:
                msgs[-1]["content"] += "\n\n" + m.content
            else:
                msgs.append({"role": m.role, "content": m.content})
        payload = {"model": req.model, "max_tokens": req.max_tokens, "messages": msgs, "stream": True}
        if req.system:
            payload["system"] = req.system
        if req.temperature is not None:
            payload["temperature"] = min(req.temperature, 1.0)
        usage_in = usage_out = None
        try:
            with self._client(300) as c, c.stream("POST", f"{self.base_url}/v1/messages", json=payload) as r:
                self.raise_for_status(r)
                for event, data in iter_sse(r):
                    if cancel is not None and cancel.cancelled:
                        raise Cancelled()
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    t = obj.get("type", event)
                    if t == "message_start":
                        usage_in = obj.get("message", {}).get("usage", {}).get("input_tokens")
                    elif t == "content_block_delta":
                        d = obj.get("delta", {})
                        if d.get("type") == "text_delta" and d.get("text"):
                            yield StreamChunk(text=d["text"])
                    elif t == "message_delta":
                        usage_out = obj.get("usage", {}).get("output_tokens", usage_out)
                    elif t == "error":
                        err = obj.get("error", {})
                        if err.get("type") == "overloaded_error":
                            raise ProviderUnavailableError("Anthropic is overloaded; try again shortly.")
                        raise ProviderError(err.get("message", "Unknown streaming error"))
                    elif t == "message_stop":
                        break
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None
        yield StreamChunk(done=True, input_tokens=usage_in, output_tokens=usage_out)
