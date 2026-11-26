"""Live resource metrics with a bounded history ring-buffer."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import psutil

from ..hardware.detection import _nvidia_smi


@dataclass
class Sample:
    ts: float
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    disk_read_mb_s: float
    disk_write_mb_s: float
    net_sent_kb_s: float
    net_recv_kb_s: float
    gpu_percent: float | None
    vram_used_gb: float | None
    vram_total_gb: float | None
    app_cpu_percent: float
    app_ram_mb: float


class MetricsCollector:
    def __init__(self, history: int = 600, gpu: bool = True):
        self.history: deque[Sample] = deque(maxlen=history)
        self._last_disk = psutil.disk_io_counters()
        self._last_net = psutil.net_io_counters()
        self._last_t = time.time()
        self._proc = psutil.Process()
        self._proc.cpu_percent(None)
        psutil.cpu_percent(None)
        self._gpu_enabled = gpu
        self._gpu_tick = 0
        self._gpu_cache: tuple[float | None, float | None, float | None] = (None, None, None)

    def _gpu(self):
        # nvidia-smi spawns a process; poll it at most every 3rd sample.
        if not self._gpu_enabled:
            return self._gpu_cache
        self._gpu_tick += 1
        if self._gpu_tick % 3 == 1:
            g = _nvidia_smi()
            if g:
                self._gpu_cache = (g[0].utilization_percent, g[0].vram_used_gb, g[0].vram_total_gb)
            else:
                self._gpu_enabled = False
        return self._gpu_cache

    def _app_tree(self) -> tuple[float, float]:
        cpu = self._proc.cpu_percent(None)
        rss = self._proc.memory_info().rss
        for child in self._proc.children(recursive=True):
            try:
                rss += child.memory_info().rss
            except psutil.Error:
                pass
        return cpu / max(1, psutil.cpu_count() or 1), rss / 1024 ** 2

    def sample(self) -> Sample:
        now = time.time()
        dt = max(1e-3, now - self._last_t)
        disk = psutil.disk_io_counters()
        net = psutil.net_io_counters()
        dr = dw = ns = nr = 0.0
        if disk and self._last_disk:
            dr = (disk.read_bytes - self._last_disk.read_bytes) / dt / 1024 ** 2
            dw = (disk.write_bytes - self._last_disk.write_bytes) / dt / 1024 ** 2
        if net and self._last_net:
            ns = (net.bytes_sent - self._last_net.bytes_sent) / dt / 1024
            nr = (net.bytes_recv - self._last_net.bytes_recv) / dt / 1024
        self._last_disk, self._last_net, self._last_t = disk, net, now
        vm = psutil.virtual_memory()
        gpu_pct, vram_used, vram_total = self._gpu()
        app_cpu, app_ram = self._app_tree()
        s = Sample(now, psutil.cpu_percent(None), vm.percent, (vm.total - vm.available) / 1024 ** 3,
                   max(0, dr), max(0, dw), max(0, ns), max(0, nr), gpu_pct, vram_used, vram_total,
                   app_cpu, app_ram)
        self.history.append(s)
        return s
