from __future__ import annotations

import json
from typing import Callable, Iterator

import httpx

from ...core.exceptions import ProviderError
from .base import Cancelled, ChatRequest, ConnectionResult, ModelInfo, Provider, StreamChunk


class OllamaProvider(Provider):
    """Ollama local server (https://ollama.com). Also exposes model management."""

    kind = "ollama"
    is_local = True
    requires_key = False
    DEFAULT_URL = "http://127.0.0.1:11434"

    def version(self) -> str | None:
        try:
            with self._client(5) as c:
                r = c.get(f"{self.base_url}/api/version")
                return r.json().get("version") if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None

    def test_connection(self) -> ConnectionResult:
        v = self.version()
        if not v:
            return ConnectionResult(False, "Ollama is not running at " + self.base_url +
                                    ". Install it from ollama.com and start it.")
        res = super().test_connection()
        if res.ok:
            res.message = f"Ollama {v} running — {res.model_count} models installed."
        return res

    def list_models(self) -> list[ModelInfo]:
        try:
            with self._client(15) as c:
                r = c.get(f"{self.base_url}/api/tags")
                self.raise_for_status(r)
                data = r.json().get("models", [])
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None
        return [ModelInfo(id=m["name"], name=m["name"], size_bytes=m.get("size"),
                          details=m.get("details", {}) | {"modified_at": m.get("modified_at", "")})
                for m in data]

    def running_models(self) -> list[dict]:
        try:
            with self._client(10) as c:
                r = c.get(f"{self.base_url}/api/ps")
                self.raise_for_status(r)
                return r.json().get("models", [])
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None

    def show(self, model: str) -> dict:
        try:
            with self._client(15) as c:
                r = c.post(f"{self.base_url}/api/show", json={"model": model})
                self.raise_for_status(r)
                return r.json()
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None

    def pull(self, model: str, progress: Callable[[str, int | None, int | None], None] | None = None,
             cancel=None) -> None:
        try:
            with self._client(None) as c, c.stream("POST", f"{self.base_url}/api/pull",
                                                   json={"model": model, "stream": True},
                                                   timeout=httpx.Timeout(None, connect=10)) as r:
                self.raise_for_status(r)
                for line in r.iter_lines():
                    if cancel is not None and cancel.cancelled:
                        raise Cancelled()
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if "error" in obj:
                        raise ProviderError(obj["error"])
                    if progress:
                        progress(obj.get("status", ""), obj.get("completed"), obj.get("total"))
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None

    def delete(self, model: str) -> None:
        try:
            with self._client(30) as c:
                r = c.request("DELETE", f"{self.base_url}/api/delete", json={"model": model})
                self.raise_for_status(r)
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None

    def load(self, model: str, keep_alive: str = "5m") -> None:
        self._generate_empty(model, keep_alive)

    def unload(self, model: str) -> None:
        self._generate_empty(model, 0)

    def _generate_empty(self, model: str, keep_alive) -> None:
        try:
            with self._client(300) as c:
                r = c.post(f"{self.base_url}/api/generate", json={"model": model, "keep_alive": keep_alive})
                self.raise_for_status(r)
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None

    def stream_chat(self, req: ChatRequest, cancel=None, options: dict | None = None) -> Iterator[StreamChunk]:
        msgs = []
        if req.system:
            msgs.append({"role": "system", "content": req.system})
        msgs += [{"role": m.role, "content": m.content} for m in req.messages]
        opts = {"num_predict": req.max_tokens}
        if req.temperature is not None:
            opts["temperature"] = req.temperature
        opts.update(options or {})
        payload = {"model": req.model, "messages": msgs, "stream": True, "options": opts}
        try:
            with self._client(600) as c, c.stream("POST", f"{self.base_url}/api/chat", json=payload) as r:
                self.raise_for_status(r)
                for line in r.iter_lines():
                    if cancel is not None and cancel.cancelled:
                        raise Cancelled()
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if "error" in obj:
                        raise ProviderError(obj["error"])
                    text = (obj.get("message") or {}).get("content", "")
                    if text:
                        yield StreamChunk(text=text)
                    if obj.get("done"):
                        yield StreamChunk(done=True, input_tokens=obj.get("prompt_eval_count"),
                                          output_tokens=obj.get("eval_count"))
                        return
        except httpx.HTTPError as e:
            raise self.wrap_network_errors(e) from None
        yield StreamChunk(done=True)
