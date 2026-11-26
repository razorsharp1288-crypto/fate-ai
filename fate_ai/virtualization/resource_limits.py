"""Host-aware resource limits for VMs and containers.

FATE AI always reserves one logical CPU and 2 GB RAM for Windows, and refuses
allocations that would exceed what the host can safely provide.
"""
from __future__ import annotations

import psutil

from ..core.exceptions import ResourceLimitError
from ..utilities.validation import validate_env_name
from .backends.base import VMSpec

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
    validate_env_name(spec.name)
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
