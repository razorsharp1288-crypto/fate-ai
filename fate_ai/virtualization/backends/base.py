"""Virtualization backend abstraction.

Backends are *not* interchangeable: each declares its capabilities, and the UI
only offers operations a backend reports as supported.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Cap(str, Enum):
    CREATE = "create"
    START = "start"
    STOP = "stop"
    FORCE_STOP = "force_stop"
    PAUSE = "pause"
    DELETE = "delete"
    CLONE = "clone"
    SNAPSHOT = "snapshot"
    CONSOLE = "console"
    SET_RESOURCES = "set_resources"
    DYNAMIC_MEMORY = "dynamic_memory"
    GPU_PARTITION = "gpu_partition"
    ISO = "iso"
    EXEC = "exec"


@dataclass
class VMSpec:
    name: str
    os_type: str = "Linux (64-bit)"
    cpus: int = 2
    memory_mb: int = 4096
    disk_gb: int = 40
    iso_path: str | None = None
    network: str = "nat"  # nat | none | bridged
    shared_folder: str | None = None
    dynamic_memory: bool = False
    image: str | None = None  # container image / WSL distro
    start_after_create: bool = False


@dataclass
class VMInfo:
    id: str
    name: str
    backend: str
    state: str  # running | stopped | paused | saved | unknown
    os_type: str = ""
    cpus: int | None = None
    memory_mb: int | None = None
    disk_gb: float | None = None
    network: str | None = None
    cpu_usage: float | None = None
    memory_usage_mb: float | None = None
    uptime_s: int | None = None
    gpu: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    id: str
    name: str
    created: str = ""


@dataclass
class BackendStatus:
    available: bool
    reason: str
    version: str | None = None


class VirtualizationBackend(ABC):
    name: str = ""
    label: str = ""
    kind: str = "vm"  # vm | container | wsl
    caps: set[Cap] = set()
    gpu_note: str = ""

    @abstractmethod
    def status(self) -> BackendStatus: ...

    @abstractmethod
    def list(self) -> list[VMInfo]: ...

    @abstractmethod
    def create(self, spec: VMSpec) -> VMInfo: ...

    @abstractmethod
    def start(self, vm_id: str) -> None: ...

    @abstractmethod
    def stop(self, vm_id: str, force: bool = False) -> None: ...

    @abstractmethod
    def delete(self, vm_id: str) -> None: ...

    def restart(self, vm_id: str) -> None:
        self.stop(vm_id)
        self.start(vm_id)

    def pause(self, vm_id: str) -> None:
        raise NotImplementedError

    def resume(self, vm_id: str) -> None:
        raise NotImplementedError

    def clone(self, vm_id: str, new_name: str) -> VMInfo:
        raise NotImplementedError

    def snapshots(self, vm_id: str) -> list[Snapshot]:
        return []

    def create_snapshot(self, vm_id: str, name: str) -> None:
        raise NotImplementedError

    def restore_snapshot(self, vm_id: str, snapshot: str) -> None:
        raise NotImplementedError

    def delete_snapshot(self, vm_id: str, snapshot: str) -> None:
        raise NotImplementedError

    def set_resources(self, vm_id: str, cpus: int | None = None, memory_mb: int | None = None) -> None:
        raise NotImplementedError

    def open_console(self, vm_id: str) -> None:
        raise NotImplementedError

    def exec(self, vm_id: str, command: list[str], timeout: float = 60):
        raise NotImplementedError

    def supports(self, cap: Cap) -> bool:
        return cap in self.caps
