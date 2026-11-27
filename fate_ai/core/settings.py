"""Typed application settings, validated with Pydantic and persisted as JSON."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)


class GeneralSettings(BaseModel):
    theme: Literal["dark", "midnight"] = "dark"
    language: str = "en"
    notifications: bool = True
    minimize_to_tray: bool = True
    start_minimized: bool = False


class AISettings(BaseModel):
    default_provider: str = "ollama"
    default_model: str = ""
    default_system_prompt: str = "You are FATE AI, a helpful, precise assistant."
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=200_000)
    confirm_cloud_document_upload: bool = True


class LocalModelSettings(BaseModel):
    ollama_url: str = "http://127.0.0.1:11434"
    llamacpp_url: str = "http://127.0.0.1:8080"
    model_storage_path: str = ""
    keep_alive: str = "5m"
    num_gpu_layers: int | None = None


class VMSettings(BaseModel):
    default_storage: str = ""
    default_cpus: int = Field(2, ge=1, le=256)
    default_ram_mb: int = Field(4096, ge=256)
    default_disk_gb: int = Field(40, ge=1)
    keep_running_in_background: bool = True


class SandboxSettings(BaseModel):
    default_level: Literal["process", "container", "vm"] = "process"
    cpu_limit: float = Field(1.0, gt=0, le=256)
    memory_limit_mb: int = Field(512, ge=32)
    timeout_seconds: int = Field(60, ge=1, le=86_400)
    allow_network: bool = False
    output_limit_kb: int = Field(512, ge=1)
    cleanup_on_delete: bool = True
    container_image: str = "python:3.12-slim"


class ResourceSettings(BaseModel):
    preset: Literal["low", "balanced", "high", "custom"] = "balanced"
    max_cpu_percent: int = Field(60, ge=5, le=100)
    ram_budget_mb: int = Field(4096, ge=256)
    background_priority: Literal["low", "normal", "high"] = "low"
    gpu_index: int | None = None
    monitor_interval_ms: int = Field(1500, ge=250, le=60_000)


class PrivacySettings(BaseModel):
    store_chat_history: bool = True
    diagnostics_include_system_info: bool = True


class AdvancedSettings(BaseModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    developer_mode: bool = False
    update_channel: Literal["stable", "beta"] = "stable"
    update_repository: str = ""  # "owner/repo" on GitHub; empty = official FATE AI releases
    auto_update_check: bool = True
    update_check_hours: int = Field(6, ge=1, le=168)
    skipped_version: str = ""


class AppSettings(BaseModel):
    onboarding_complete: bool = False
    general: GeneralSettings = GeneralSettings()
    ai: AISettings = AISettings()
    local: LocalModelSettings = LocalModelSettings()
    vm: VMSettings = VMSettings()
    sandbox: SandboxSettings = SandboxSettings()
    resources: ResourceSettings = ResourceSettings()
    privacy: PrivacySettings = PrivacySettings()
    advanced: AdvancedSettings = AdvancedSettings()


class SettingsStore:
    """Loads/saves settings atomically. Never contains secrets."""

    def __init__(self, path: Path):
        self.path = path
        self.settings = self._load()

    def _load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            return AppSettings.model_validate(json.loads(self.path.read_text("utf-8")))
        except (ValidationError, json.JSONDecodeError, OSError):
            log.warning("settings file invalid, falling back to defaults")
            backup = self.path.with_suffix(".invalid.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return AppSettings()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self.settings.model_dump_json(indent=2)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def update(self, **sections) -> AppSettings:
        merged = self.settings.model_dump()
        for key, value in sections.items():
            if isinstance(value, BaseModel):
                value = value.model_dump()
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        self.settings = AppSettings.model_validate(merged)
        self.save()
        return self.settings
