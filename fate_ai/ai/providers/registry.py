"""Creates provider instances from stored configuration + credential vault."""
from __future__ import annotations

from dataclasses import dataclass

from .anthropic_provider import AnthropicProvider
from .base import Provider
from .ollama_provider import OllamaProvider
from .openai_provider import LlamaCppProvider, OpenAICompatibleProvider, OpenAIProvider


@dataclass(frozen=True)
class ProviderKind:
    kind: str
    label: str
    cls: type
    default_url: str
    requires_key: bool
    is_local: bool
    description: str


KINDS: dict[str, ProviderKind] = {
    "openai": ProviderKind("openai", "OpenAI", OpenAIProvider, "https://api.openai.com/v1", True, False,
                           "GPT models via your own OpenAI account. Billed by OpenAI."),
    "anthropic": ProviderKind("anthropic", "Anthropic Claude", AnthropicProvider, "https://api.anthropic.com",
                              True, False, "Claude models via your own Anthropic account. Billed by Anthropic."),
    "ollama": ProviderKind("ollama", "Ollama (local)", OllamaProvider, "http://127.0.0.1:11434", False, True,
                           "Runs open models on this PC. Free, private, offline."),
    "llamacpp": ProviderKind("llamacpp", "llama.cpp server (local)", LlamaCppProvider, "http://127.0.0.1:8080",
                             False, True, "llama.cpp's llama-server with GGUF models on this PC."),
    "openai_compatible": ProviderKind("openai_compatible", "OpenAI-compatible API", OpenAICompatibleProvider,
                                      "http://127.0.0.1:1234/v1", False, False,
                                      "Any endpoint speaking the OpenAI chat API (LM Studio, vLLM, Groq, ...)."),
}

DEFAULT_PROVIDERS = [
    ("ollama", "ollama", "Ollama"),
    ("llamacpp", "llamacpp", "llama.cpp"),
    ("openai", "openai", "OpenAI"),
    ("anthropic", "anthropic", "Anthropic"),
]


class ProviderRegistry:
    def __init__(self, repo, credentials, transport=None):
        self.repo = repo
        self.credentials = credentials
        self._transport = transport  # injectable for tests

    def ensure_defaults(self, settings=None) -> None:
        existing = {p["id"] for p in self.repo.list()}
        for pid, kind, name in DEFAULT_PROVIDERS:
            if pid not in existing:
                url = KINDS[kind].default_url
                if settings is not None and kind == "ollama":
                    url = settings.local.ollama_url
                if settings is not None and kind == "llamacpp":
                    url = settings.local.llamacpp_url
                self.repo.upsert(pid, kind, name, url)

    def configs(self) -> list[dict]:
        return self.repo.list()

    def get(self, provider_id: str) -> Provider:
        cfg = self.repo.get(provider_id)
        if cfg is None:
            raise KeyError(f"Unknown provider '{provider_id}'")
        spec = KINDS[cfg["kind"]]
        key = self.credentials.get_api_key(provider_id)
        url = cfg["base_url"] or spec.default_url
        if issubclass(spec.cls, OpenAICompatibleProvider):
            return spec.cls(provider_id, url, api_key=key, transport=self._transport, options=cfg.get("options"))
        return spec.cls(provider_id, url, api_key=key, transport=self._transport)

    def requires_key(self, cfg: dict) -> bool:
        return bool(cfg.get("options", {}).get("requires_key", KINDS[cfg["kind"]].requires_key))

    def is_local(self, cfg: dict) -> bool:
        if "is_local" in cfg.get("options", {}):
            return bool(cfg["options"]["is_local"])
        return KINDS[cfg["kind"]].is_local

    def add_preset(self, preset_id: str, base_url: str | None = None) -> dict:
        """Add (or return) a provider from the catalog, e.g. 'gemini', 'groq', 'openrouter'."""
        from .catalog import BY_ID
        p = BY_ID[preset_id]
        existing = self.repo.get(p.id)
        if existing and not base_url:
            return existing
        url = base_url or p.base_url
        if base_url:
            from ...utilities.validation import validate_url
            url = validate_url(base_url)
        opts = {"preset": p.id, "requires_key": p.requires_key, "is_local": p.category == "Local"}
        if p.kind == "openai_compatible":
            opts.update(raw_base=p.raw_base, auth_header=p.auth_header, auth_scheme=p.auth_scheme)
        return self.repo.upsert(p.id, p.kind, p.name, url, existing["default_model"] if existing else "", True, opts)

    def add_custom(self, name: str, base_url: str, kind: str = "openai_compatible", requires_key: bool = True,
                   auth_header: str = "Authorization", auth_scheme: str = "Bearer", is_local: bool | None = None) -> dict:
        from ...security.paths import safe_name
        from ...utilities.validation import is_local_url, validate_url
        base_url = validate_url(base_url)
        if not auth_header or any(c in auth_header for c in ":\r\n "):
            raise ValueError("Invalid auth header name")
        pid = "custom_" + safe_name(name).lower().replace(" ", "_").replace(".", "_")
        opts = {"requires_key": requires_key, "auth_header": auth_header, "auth_scheme": auth_scheme,
                "is_local": is_local_url(base_url) if is_local is None else is_local}
        return self.repo.upsert(pid, kind, name, base_url, "", True, opts)

    def remove(self, provider_id: str) -> None:
        self.credentials.delete_api_key(provider_id)
        self.repo.delete(provider_id)
