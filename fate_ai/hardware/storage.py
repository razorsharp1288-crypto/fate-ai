"""Storage detection."""
from __future__ import annotations

from dataclasses import dataclass

import psutil

GB = 1024 ** 3


@dataclass
class StorageInfo:
    mount: str
    total_gb: float
    free_gb: float
    percent: float


def detect_storage(extra_paths: list[str] | None = None) -> list[StorageInfo]:
    out, seen = [], set()
    paths = list(extra_paths or [])
    try:
        for p in psutil.disk_partitions(all=False):
            if "cdrom" in p.opts or p.fstype == "":
                continue
            paths.append(p.mountpoint)
    except Exception:
        pass
    for mp in paths:
        try:
            u = psutil.disk_usage(mp)
        except (OSError, PermissionError):
            continue
        if u.total < GB and mp not in (extra_paths or []):
            continue  # skip tiny pseudo/overlay mounts
        key = (u.total, u.free) if not extra_paths or mp not in extra_paths else mp
        if key in seen:
            continue
        seen.add(key)
        out.append(StorageInfo(mp, round(u.total / GB, 1), round(u.free / GB, 1), u.percent))
    return out


