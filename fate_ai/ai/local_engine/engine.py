"""Local inference engine management: status of Ollama and llama.cpp and model lifecycle.

Wraps the provider adapters so UI code asks one object "what local engines are
running and which models are installed/loaded" instead of talking HTTP itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..providers.base import ModelInfo


@dataclass
class EngineStatus:
    ollama_version: str | None = None
    llamacpp_running: bool = False
    installed: list[ModelInfo] = field(default_factory=list)
    loaded: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def ollama_running(self) -> bool:
        return self.ollama_version is not None


class LocalEngineManager:
    def __init__(self, registry, settings_store=None):
        self.registry = registry
        self.settings = settings_store

    @property
    def ollama(self):
        return self.registry.get("ollama")

    def status(self) -> EngineStatus:
        st = EngineStatus()
        try:
            o = self.ollama
            st.ollama_version = o.version()
            if st.ollama_version:
                st.installed = o.list_models()
                st.loaded = o.running_models()
        except Exception as e:  # report, never raise to the UI
            st.error = str(e)
        try:
            st.llamacpp_running = self.registry.get("llamacpp").health()
        except Exception:
            st.llamacpp_running = False
        return st

    def pull(self, tag: str, progress=None, cancel=None) -> None:
        from ...utilities.validation import validate_model_tag
        self.ollama.pull(validate_model_tag(tag), progress=progress, cancel=cancel)

    def delete(self, tag: str) -> None:
        self.ollama.delete(tag)

    def load(self, tag: str) -> None:
        keep = self.settings.settings.local.keep_alive if self.settings else "5m"
        self.ollama.load(tag, keep)

    def unload(self, tag: str) -> None:
        self.ollama.unload(tag)

    def details(self, tag: str) -> dict:
        return self.ollama.show(tag)
