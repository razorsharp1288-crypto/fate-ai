"""Snapshot management on top of any backend that supports ``Cap.SNAPSHOT``.

Adds validated names, a reserved "clean" snapshot used for disposable
environments, audit logging and a revert-to-clean helper.
"""
from __future__ import annotations

import re
import time
from datetime import datetime

from ..core.exceptions import BackendUnavailableError, ValidationError
from .backends.base import Cap, Snapshot, VirtualizationBackend

CLEAN = "fate-clean"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,79}$")


class SnapshotManager:
    def __init__(self, backend: VirtualizationBackend, audit=None):
        if not backend.supports(Cap.SNAPSHOT):
            raise BackendUnavailableError(f"{backend.label} does not support snapshots.")
        self.backend = backend
        self.audit = audit

    @staticmethod
    def default_name() -> str:
        return datetime.now().strftime("snapshot-%Y%m%d-%H%M%S")

    def list(self, vm_id: str) -> list[Snapshot]:
        return self.backend.snapshots(vm_id)

    def create(self, vm_id: str, name: str | None = None) -> str:
        name = (name or self.default_name()).strip()
        if not _NAME.match(name):
            raise ValidationError("Snapshot names may contain letters, digits, space, - _ . (max 80).")
        self.backend.create_snapshot(vm_id, name)
        self._audit("snapshot_created", vm_id, name)
        return name

    def restore(self, vm_id: str, name: str, stop_first: bool = True) -> None:
        if stop_first:
            state = next((v.state for v in self.backend.list() if v.id == vm_id or v.name == vm_id), "")
            if state == "running":
                self.backend.stop(vm_id, force=True)
                time.sleep(1)
        self.backend.restore_snapshot(vm_id, name)
        self._audit("snapshot_restored", vm_id, name)

    def delete(self, vm_id: str, name: str) -> None:
        self.backend.delete_snapshot(vm_id, name)
        self._audit("snapshot_deleted", vm_id, name)

    def ensure_clean(self, vm_id: str) -> None:
        if CLEAN not in {s.name for s in self.list(vm_id)}:
            self.backend.create_snapshot(vm_id, CLEAN)
            self._audit("snapshot_created", vm_id, CLEAN)

    def revert_to_clean(self, vm_id: str) -> None:
        self.restore(vm_id, CLEAN)

    def _audit(self, action: str, vm_id: str, name: str) -> None:
        if self.audit:
            self.audit.log("virtualization", action, f"{self.backend.label}: {vm_id} / {name}")
