"""Facade over all virtualization backends with resource safety checks."""
from __future__ import annotations

import logging

import psutil

from ..core.exceptions import BackendUnavailableError, ResourceLimitError, ValidationError
from ..utilities.proc import which
from .backends.base import Cap, VirtualizationBackend, VMInfo, VMSpec
from .backends.container import ContainerBackend
from .backends.hyperv import HyperVBackend
from .backends.virtualbox import VirtualBoxBackend
from .backends.wsl import WSLBackend

log = logging.getLogger(__name__)

# Keep at least this much for Windows itself.
HOST_RESERVE_RAM_MB = 2048
HOST_RESERVE_CPUS = 1


def host_limits() -> tuple[int, int]:
    cpus = psutil.cpu_count(logical=True) or 1
    ram_mb = psutil.virtual_memory().total // 2 ** 20
    return max(1, cpus - HOST_RESERVE_CPUS), max(256, ram_mb - HOST_RESERVE_RAM_MB)


def recommend(kind: str = "dev") -> tuple[int, int, int]:
    """Sensible (cpus, ram_mb, disk_gb) for a new VM given host size."""
    max_cpu, max_ram = host_limits()
    cpus = max(1, min(4, max_cpu // 2))
    ram = max(1024, min(8192, (max_ram // 2) // 512 * 512))
    return cpus, ram, 40 if kind == "dev" else 64


def validate_spec(spec: VMSpec, running_ram_mb: int = 0) -> None:
    name = spec.name.strip()
    if not name or len(name) > 64 or not all(c.isalnum() or c in "-_ ." for c in name):
        raise ValidationError("VM name must be 1-64 characters: letters, digits, space, - _ .")
    max_cpu, max_ram = host_limits()
    if spec.cpus < 1 or spec.cpus > max_cpu:
        raise ResourceLimitError(f"CPU count must be between 1 and {max_cpu} (one core is kept for Windows).")
    if spec.memory_mb < 256:
        raise ResourceLimitError("At least 256 MB of RAM is required.")
    if spec.memory_mb + running_ram_mb > max_ram:
        raise ResourceLimitError(
            f"{spec.memory_mb} MB plus {running_ram_mb} MB used by running VMs exceeds the safe limit of "
            f"{max_ram} MB (2 GB is reserved for Windows).")
    if spec.disk_gb < 1 or spec.disk_gb > 4096:
        raise ResourceLimitError("Disk size must be between 1 and 4096 GB.")


class VMManager:
    def __init__(self, settings=None, audit=None, backends: list[VirtualizationBackend] | None = None):
        self.audit = audit
        if backends is None:
            storage = settings.vm.default_storage if settings and settings.vm.default_storage else None
            from ..hardware.detection import detect_virtualization
            v = detect_virtualization()
            backends = [HyperVBackend(storage), VirtualBoxBackend(v.virtualbox_path, storage), WSLBackend(),
                        ContainerBackend(which("docker"), "docker"), ContainerBackend(which("podman"), "podman")]
        self.backends = {b.name: b for b in backends}
        self._status_cache: dict = {}

    def statuses(self, refresh: bool = False) -> dict:
        if refresh or not self._status_cache:
            self._status_cache = {}
            for n, b in self.backends.items():
                try:
                    self._status_cache[n] = b.status()
                except Exception as e:  # never let one backend break the page
                    from .backends.base import BackendStatus
                    self._status_cache[n] = BackendStatus(False, f"Detection failed: {e}")
        return self._status_cache

    def available(self) -> list[VirtualizationBackend]:
        st = self.statuses()
        return [b for n, b in self.backends.items() if st.get(n) and st[n].available]

    def backend(self, name: str) -> VirtualizationBackend:
        b = self.backends.get(name)
        if b is None:
            raise BackendUnavailableError(f"Unknown backend {name}")
        st = self.statuses().get(name)
        if st is not None and not st.available:
            raise BackendUnavailableError(st.reason)
        return b

    def list_all(self) -> list[VMInfo]:
        out = []
        for b in self.available():
            try:
                out.extend(b.list())
            except Exception as e:
                log.warning("listing %s failed: %s", b.name, e)
        return out

    def running(self) -> list[VMInfo]:
        return [v for v in self.list_all() if v.state == "running"]

    def create(self, backend: str, spec: VMSpec) -> VMInfo:
        b = self.backend(backend)
        if not b.supports(Cap.CREATE):
            raise BackendUnavailableError(f"{b.label} does not support creating environments here.")
        running = sum((v.memory_mb or 0) for v in self.running() if v.backend in ("hyperv", "virtualbox"))
        validate_spec(spec, running if b.kind == "vm" else 0)
        info = b.create(spec)
        self._audit("vm_created", f"{b.label}: {spec.name} cpus={spec.cpus} ram={spec.memory_mb}MB")
        return info

    def op(self, backend: str, op: str, vm_id: str, *args):
        b = self.backend(backend)
        fn = getattr(b, op)
        result = fn(vm_id, *args)
        self._audit(f"vm_{op}", f"{b.label}: {vm_id}")
        return result

    def stop_all(self, force: bool = False) -> list[str]:
        """Emergency stop: stop every running managed VM/container."""
        errors = []
        for v in self.running():
            try:
                self.backends[v.backend].stop(v.id, force=force)
            except Exception as e:
                errors.append(f"{v.name}: {e}")
        self._audit("vm_stop_all", f"force={force} errors={len(errors)}")
        return errors

    def _audit(self, action: str, detail: str) -> None:
        if self.audit:
            self.audit.log("virtualization", action, detail)
