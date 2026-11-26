"""CPU detection."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import psutil

import platform

from ..utilities.proc import run

GB = 1024 ** 3


@dataclass
class CPUInfo:
    vendor: str | None
    model: str | None
    physical_cores: int | None
    logical_threads: int | None
    usage_percent: float | None
    freq_mhz: float | None
    max_freq_mhz: float | None


def _cpu_model() -> tuple[str | None, str | None]:
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            name = winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
            vendor = winreg.QueryValueEx(k, "VendorIdentifier")[0].strip()
            return _vendor(vendor), name
        except OSError:
            pass
    if Path("/proc/cpuinfo").exists():
        model = vendor = None
        for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            elif line.startswith("vendor_id") and not vendor:
                vendor = line.split(":", 1)[1].strip()
        return _vendor(vendor), model
    if sys.platform == "darwin":
        r = run(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=5)
        if r.ok:
            return ("Apple" if "Apple" in r.stdout else None), r.stdout.strip()
    return None, platform.processor() or None


def _vendor(v: str | None) -> str | None:
    if not v:
        return None
    v2 = v.lower()
    if "intel" in v2:
        return "Intel"
    if "amd" in v2:
        return "AMD"
    if "arm" in v2 or "qualcomm" in v2:
        return v
    return v


def detect_cpu(sample: bool = True) -> CPUInfo:
    vendor, model = _cpu_model()
    try:
        f = psutil.cpu_freq()
    except Exception:
        f = None
    return CPUInfo(vendor, model, psutil.cpu_count(logical=False), psutil.cpu_count(logical=True),
                   psutil.cpu_percent(interval=0.2 if sample else None),
                   round(f.current, 0) if f and f.current else None,
                   round(f.max, 0) if f and f.max else None)


