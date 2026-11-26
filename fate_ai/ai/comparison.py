"""Run one prompt against several models and measure real, local results."""
from __future__ import annotations

import time
from dataclasses import dataclass

from .providers.base import ChatMessage, ChatRequest, estimate_tokens


@dataclass
class ComparisonResult:
    provider: str
    model: str
    text: str
    success: bool
    error: str | None
    latency_ms: int
    first_token_ms: int | None
    output_tokens: int
    tokens_exact: bool
    tokens_per_sec: float | None


def run_one(registry, provider_id: str, model: str, prompt: str, max_tokens: int = 512,
            temperature: float = 0.2, cancel=None, on_token=None) -> ComparisonResult:
    start = time.perf_counter()
    first = None
    parts = []
    last = None
    try:
        p = registry.get(provider_id)
        req = ChatRequest(model, [ChatMessage("user", prompt)], temperature=temperature, max_tokens=max_tokens)
        for ch in p.stream_chat(req, cancel=cancel):
            if ch.text:
                if first is None:
                    first = int((time.perf_counter() - start) * 1000)
                parts.append(ch.text)
                if on_token:
                    on_token(ch.text)
            if ch.done:
                last = ch
    except Exception as e:
        return ComparisonResult(provider_id, model, "".join(parts), False, str(e),
                                int((time.perf_counter() - start) * 1000), first, 0, False, None)
    total = int((time.perf_counter() - start) * 1000)
    text = "".join(parts)
    exact = bool(last and last.output_tokens)
    out_tokens = last.output_tokens if exact else estimate_tokens(text)
    gen_s = (total - (first or 0)) / 1000
    tps = round(out_tokens / gen_s, 1) if gen_s > 0 and out_tokens else None
    return ComparisonResult(provider_id, model, text, True, None, total, first, out_tokens, exact, tps)


# Published specifications (from provider documentation). Shown separately from
# measured results; "None" means not documented here.
PUBLISHED_SPECS = {
    "gpt-4o": {"context": 128_000, "modalities": "text, image", "tools": True},
    "gpt-4o-mini": {"context": 128_000, "modalities": "text, image", "tools": True},
    "gpt-4.1": {"context": 1_047_576, "modalities": "text, image", "tools": True},
    "llama3.1": {"context": 128_000, "modalities": "text", "tools": True},
    "llama3.2": {"context": 128_000, "modalities": "text", "tools": True},
    "qwen2.5": {"context": 32_768, "modalities": "text", "tools": True},
    "mistral": {"context": 32_768, "modalities": "text", "tools": True},
    "gemma2": {"context": 8_192, "modalities": "text", "tools": False},
    "phi3": {"context": 4_096, "modalities": "text", "tools": False},
}


def published_spec(model: str) -> dict | None:
    m = model.lower()
    best = None
    for k, v in PUBLISHED_SPECS.items():
        if m.startswith(k) and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best else None
