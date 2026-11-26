"""Permission model for agents and tools.

Every tool action is classified; anything destructive or outside the agent's
approved directories must be confirmed by the user through a callback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from ..core.exceptions import PermissionDeniedError
from .paths import check_allowed


class Capability(str, Enum):
    READ_FILES = "read_files"
    WRITE_FILES = "write_files"
    RUN_SANDBOX = "run_sandbox"
    NETWORK = "network"
    SYSTEM_INFO = "system_info"


DESTRUCTIVE = {Capability.WRITE_FILES}


@dataclass
class PermissionSet:
    capabilities: set[Capability] = field(default_factory=set)
    allowed_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, perms: dict, paths: list[str]) -> "PermissionSet":
        caps = {Capability(k) for k, v in (perms or {}).items() if v and k in Capability._value2member_map_}
        return cls(caps, list(paths or []))

    def to_dict(self) -> dict:
        return {c.value: (c in self.capabilities) for c in Capability}


ConfirmFn = Callable[[str], bool]


class PermissionGuard:
    def __init__(self, perms: PermissionSet, confirm: ConfirmFn, audit=None, actor: str = "agent"):
        self.perms, self.confirm, self.audit, self.actor = perms, confirm, audit, actor

    def require(self, cap: Capability, description: str, path: str | None = None) -> None:
        if cap not in self.perms.capabilities:
            self._log("denied", f"{cap.value}: {description}")
            raise PermissionDeniedError(f"{self.actor} lacks permission '{cap.value}'")
        if path is not None:
            check_allowed(path, self.perms.allowed_paths)
        if cap in DESTRUCTIVE and not self.confirm(f"{self.actor} wants to: {description}\n\nAllow?"):
            self._log("rejected_by_user", description)
            raise PermissionDeniedError("Action rejected by user")
        self._log("allowed", f"{cap.value}: {description}")

    def _log(self, action: str, detail: str) -> None:
        if self.audit:
            self.audit.log("agent", action, f"{self.actor}: {detail}")
