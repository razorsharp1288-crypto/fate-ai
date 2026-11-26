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
        return spec.cls(provider_id, cfg["base_url"] or spec.default_url, api_key=key, transport=self._transport)

    def add_custom(self, name: str, base_url: str, kind: str = "openai_compatible") -> dict:
        from ...security.paths import safe_name
        from ...utilities.validation import validate_url
        base_url = validate_url(base_url)
        pid = "custom_" + safe_name(name).lower().replace(" ", "_").replace(".", "_")
        return self.repo.upsert(pid, kind, name, base_url)

    def remove(self, provider_id: str) -> None:
        self.credentials.delete_api_key(provider_id)
        self.repo.delete(provider_id)
