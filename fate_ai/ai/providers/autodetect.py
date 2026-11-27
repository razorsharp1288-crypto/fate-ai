"""Find which AI service an API key belongs to — just paste the key.

1. Key-format detection (``catalog.detect_from_key``) narrows the candidates.
2. Each candidate is tried in parallel with a read-only "list models" call; the
   first service that accepts the key wins.

Privacy: a recognised key is only ever sent to the service(s) its format
matches. An unrecognised key is tried against other services only when the
caller passes ``allow_all=True`` (the UI asks the user first).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .catalog import PRESETS, ProviderPreset, detect_from_key
from .registry import KINDS


@dataclass
class ProbeResult:
    preset: ProviderPreset
    ok: bool
    message: str
    models: list[str]


def cloud_candidates() -> list[ProviderPreset]:
    return [p for p in PRESETS if p.requires_key and not p.needs_url and p.category != "Local"]


def _probe(preset: ProviderPreset, key: str, transport=None, lenient: bool = False) -> ProbeResult:
    """Check whether ``preset`` accepts ``key``.

    1. List models (read-only). Success => accepted, with the live model list.
    2. If the service can't list models (404/405/odd format) — but did not reject the key — send a 1-token chat
       to a well-known model. Success => accepted, with the suggested model list.
       With ``lenient`` (the key format matched this service, or the user picked it), a chat reply that fails
       only because of the model name (not auth) also counts: the key works, the model list is a suggestion.
    """
    from ...core.exceptions import AuthenticationError, ProviderError
    from .base import ChatMessage, ChatRequest
    from .catalog import known_models
    from .openai_provider import OpenAICompatibleProvider
    cls = KINDS[preset.kind].cls
    kw = dict(api_key=key, transport=transport, timeout=12.0)
    if issubclass(cls, OpenAICompatibleProvider):
        kw["options"] = {"requires_key": True, "raw_base": preset.raw_base, "auth_header": preset.auth_header,
                         "auth_scheme": preset.auth_scheme}
    provider = cls(preset.id, preset.base_url, **kw)
    try:
        models = provider.list_models()
        if models:
            return ProbeResult(preset, True, f"{len(models)} models", [m.id for m in models])
        list_err = "empty model list"
    except AuthenticationError as e:
        return ProbeResult(preset, False, str(e), [])
    except Exception as e:  # noqa: BLE001
        list_err = str(e)
        if "could not connect" in list_err.lower() or "timed out" in list_err.lower():
            return ProbeResult(preset, False, list_err, [])
    suggested = known_models(preset.id)
    if not suggested:
        return ProbeResult(preset, False, list_err, [])
    for model in suggested[:2]:
        try:
            provider.chat(ChatRequest(model, [ChatMessage("user", "hi")], temperature=None, max_tokens=1))
            return ProbeResult(preset, True, "key accepted (service doesn't list models)",
                               [model] + [m for m in suggested if m != model])
        except AuthenticationError as e:
            return ProbeResult(preset, False, str(e), [])
        except ProviderError as e:
            msg = str(e).lower()
            if lenient and "request failed (4" in msg and "429" not in msg:
                return ProbeResult(preset, True, "key accepted; model list is a suggestion", suggested)
            list_err = str(e)
        except Exception as e:  # noqa: BLE001
            list_err = str(e)
    return ProbeResult(preset, False, list_err, [])


def find_service(key: str, allow_all: bool = False, transport=None,
                 candidates: list[ProviderPreset] | None = None) -> tuple[ProbeResult | None, list[ProbeResult]]:
    """Return (winner, all_results). ``winner`` is None when no service accepted the key."""
    key = (key or "").strip()
    lenient = candidates is not None  # caller named the service explicitly
    if candidates is None:
        candidates = detect_from_key(key)
        lenient = bool(candidates)
        if not candidates and allow_all:
            candidates = cloud_candidates()
    if not candidates:
        return None, []
    results: list[ProbeResult] = []
    order = {p.id: i for i, p in enumerate(candidates)}
    with ThreadPoolExecutor(max_workers=min(12, len(candidates))) as pool:
        futures = [pool.submit(_probe, p, key, transport, lenient) for p in candidates]
        for f in as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda r: order[r.preset.id])
    winner = next((r for r in results if r.ok), None)
    return winner, results


def connect(ctx, key: str, allow_all: bool = False, transport=None) -> tuple[ProbeResult | None, list[ProbeResult]]:
    """Detect the service, then add it, store the key and make it usable (sets a default model if none)."""
    winner, results = find_service(key, allow_all, transport)
    if winner is None:
        return None, results
    return connect_known(ctx, key, winner)[0], results


def connect_known(ctx, key: str, winner: ProbeResult) -> tuple[ProbeResult, list[ProbeResult]]:
    """Store a key for a service that already accepted it and make it the default if nothing better is set."""
    ctx.providers.add_preset(winner.preset.id)
    ctx.credentials.set_api_key(winner.preset.id, key)
    cfg = ctx.provider_repo.get(winner.preset.id)
    model = cfg.get("default_model") or _pick_model(winner.models)
    if model and not cfg.get("default_model"):
        ctx.provider_repo.upsert(cfg["id"], cfg["kind"], cfg["name"], cfg["base_url"], model, True, cfg["options"])
    ai = ctx.settings.settings.ai
    if not ai.default_model or ai.default_provider in ("ollama", "llamacpp"):
        if model:
            ctx.settings.update(ai={"default_provider": winner.preset.id, "default_model": model})
    ctx.audit.log("credentials", "key_autodetected", f"service={winner.preset.id}")
    return winner, [winner]


_PREFER = ("mercury", "gpt-4o-mini", "gpt-4.1-mini", "claude", "gemini-2", "gemini", "grok", "mistral-large",
           "deepseek-chat", "llama-3.3", "llama", "qwen")


def _pick_model(models: list[str]) -> str:
    if not models:
        return ""
    low = [m.lower() for m in models]
    for pref in _PREFER:
        for m, l in zip(models, low):
            if pref in l and not any(x in l for x in ("embed", "tts", "whisper", "image", "audio", "vision-preview")):
                return m
    return models[0]
