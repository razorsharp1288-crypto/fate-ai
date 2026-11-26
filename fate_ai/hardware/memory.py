"""Memory detection."""
from __future__ import annotations

from dataclasses import dataclass

import psutil

GB = 1024 ** 3


@dataclass
class MemoryInfo:
    total_gb: float
    available_gb: float
    used_gb: float
    percent: float


def detect_memory() -> MemoryInfo:
    vm = psutil.virtual_memory()
    return MemoryInfo(round(vm.total / GB, 2), round(vm.available / GB, 2), round((vm.total - vm.available) / GB, 2),
                      vm.percent)


