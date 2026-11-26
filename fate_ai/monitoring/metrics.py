"""Metric records and aggregation helpers for the hardware monitor."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable


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


@dataclass
class Summary:
    count: int
    cpu_avg: float
    cpu_peak: float
    ram_avg: float
    ram_peak: float
    gpu_avg: float | None
    app_ram_peak_mb: float


def summarize(samples: Iterable[Sample], since: float | None = None) -> Summary | None:
    """Average/peak usage over ``samples`` (optionally only those newer than ``since``)."""
    xs = [s for s in samples if since is None or s.ts >= since]
    if not xs:
        return None
    gpus = [s.gpu_percent for s in xs if s.gpu_percent is not None]
    return Summary(len(xs), round(mean(s.cpu_percent for s in xs), 1), max(s.cpu_percent for s in xs),
                   round(mean(s.ram_percent for s in xs), 1), max(s.ram_percent for s in xs),
                   round(mean(gpus), 1) if gpus else None, max(s.app_ram_mb for s in xs))


def to_csv_rows(samples: Iterable[Sample]) -> list[list]:
    header = ["timestamp", "cpu_percent", "ram_percent", "ram_used_gb", "disk_read_mb_s", "disk_write_mb_s",
              "net_sent_kb_s", "net_recv_kb_s", "gpu_percent", "vram_used_gb", "app_cpu_percent", "app_ram_mb"]
    rows = [header]
    for s in samples:
        rows.append([round(s.ts, 3), s.cpu_percent, s.ram_percent, round(s.ram_used_gb, 3), round(s.disk_read_mb_s, 3),
                     round(s.disk_write_mb_s, 3), round(s.net_sent_kb_s, 2), round(s.net_recv_kb_s, 2),
                     s.gpu_percent, s.vram_used_gb, round(s.app_cpu_percent, 2), round(s.app_ram_mb, 1)])
    return rows
