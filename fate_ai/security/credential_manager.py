"""API key storage backed by the OS credential vault.

On Windows ``keyring`` uses Windows Credential Manager. Keys are never written
to SQLite, settings files or logs. A memory backend exists for tests and for
systems without any vault (keys then last only for the session, and the UI says so).
"""
from __future__ import annotations

import logging

from ..core.exceptions import CredentialError
from .redaction import register_secret

log = logging.getLogger(__name__)
SERVICE = "FateAI"


class MemoryBackend:
    name = "In-memory (not persisted)"
    persistent = False

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


class KeyringBackend:
    persistent = True

    def __init__(self) -> None:
        import keyring
        from keyring.backends import fail

        self._kr = keyring
        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring):
            raise CredentialError("No OS credential vault available")
        self.name = type(backend).__name__
        if "Windows" in type(backend).__module__ or "Win" in self.name:
            self.name = "Windows Credential Manager"

    def get(self, key: str) -> str | None:
        return self._kr.get_password(SERVICE, key)

    def set(self, key: str, value: str) -> None:
        self._kr.set_password(SERVICE, key, value)

    def delete(self, key: str) -> None:
        try:
            self._kr.delete_password(SERVICE, key)
        except self._kr.errors.PasswordDeleteError:
            pass


def default_backend():
    try:
        return KeyringBackend()
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("OS credential vault unavailable (%s); using session-only memory store", type(exc).__name__)
        return MemoryBackend()


class CredentialManager:
    def __init__(self, backend=None, audit=None) -> None:
        self.backend = backend or default_backend()
        self._audit = audit
        self._cache: dict[str, str | None] = {}

    @staticmethod
    def _key(provider_id: str) -> str:
        if not provider_id or any(c in provider_id for c in "\r\n\0"):
            raise CredentialError("Invalid provider id")
        return f"provider:{provider_id}:api_key"

    def set_api_key(self, provider_id: str, api_key: str) -> None:
        api_key = (api_key or "").strip()
        if not api_key:
            raise CredentialError("API key is empty")
        if len(api_key) > 4096 or any(c in api_key for c in "\r\n\0 "):
            raise CredentialError("API key contains invalid characters")
        try:
            self.backend.set(self._key(provider_id), api_key)
        except Exception as exc:
            raise CredentialError(f"Could not save key to {self.backend.name}: {type(exc).__name__}") from None
        register_secret(api_key)
        self._cache[provider_id] = api_key
        if self._audit:
            self._audit.log("credentials", "key_saved", f"provider={provider_id}")

    def get_api_key(self, provider_id: str) -> str | None:
        if provider_id in self._cache:
            return self._cache[provider_id]
        try:
            val = self.backend.get(self._key(provider_id))
        except Exception:
            val = None
        register_secret(val)
        self._cache[provider_id] = val
        return val

    def has_api_key(self, provider_id: str) -> bool:
        return bool(self.get_api_key(provider_id))

    def delete_api_key(self, provider_id: str) -> None:
        try:
            self.backend.delete(self._key(provider_id))
        finally:
            self._cache.pop(provider_id, None)
        if self._audit:
            self._audit.log("credentials", "key_deleted", f"provider={provider_id}")

    @staticmethod
    def mask(api_key: str | None) -> str:
        if not api_key:
            return "not set"
        if len(api_key) <= 8:
            return "•" * len(api_key)
        return f"{api_key[:4]}…{api_key[-4:]}"
