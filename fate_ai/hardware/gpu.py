"""GPU detection: nvidia-smi for live NVIDIA data, Windows driver registry or lspci otherwise."""
from __future__ import annotations

import sys
from dataclasses import dataclass

from ..utilities.proc import powershell, run, which

GB = 1024 ** 3


@dataclass
class GPUInfo:
    index: int
    vendor: str | None
    name: str
    vram_total_gb: float | None = None
    vram_used_gb: float | None = None
    shared_gb: float | None = None
    utilization_percent: float | None = None
    temperature_c: float | None = None
    driver: str | None = None
    source: str = ""


def _nvidia_smi() -> list[GPUInfo]:
    exe = which("nvidia-smi")
    if not exe:
        return []
    r = run([exe, "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,driver_version",
             "--format=csv,noheader,nounits"], timeout=10)
    out = []
    if not r.ok:
        return out
    for line in r.stdout.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 7:
            continue

        def num(s):
            try:
                return float(s)
            except ValueError:
                return None
        tot, used = num(p[2]), num(p[3])
        out.append(GPUInfo(int(p[0]), "NVIDIA", p[1], round(tot / 1024, 2) if tot else None,
                           round(used / 1024, 2) if used is not None else None, None, num(p[4]), num(p[5]),
                           p[6], "nvidia-smi"))
    return out


_WIN_GPU_PS = r"""
$ErrorActionPreference='SilentlyContinue'
$base='HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
Get-ChildItem $base | Where-Object { $_.PSChildName -match '^\d{4}$' } | ForEach-Object {
  $p = Get-ItemProperty $_.PSPath
  if ($p.DriverDesc) {
    $mem = $p.'HardwareInformation.qwMemorySize'
    if (-not $mem) { $m = $p.'HardwareInformation.MemorySize'; if ($m -is [byte[]]) { $mem = [BitConverter]::ToUInt32($m,0) } else { $mem = $m } }
    "{0}|{1}|{2}|{3}" -f $p.DriverDesc, $p.ProviderName, $mem, $p.DriverVersion
  }
}
"""


def _windows_gpus() -> list[GPUInfo]:
    r = powershell(_WIN_GPU_PS, timeout=20)
    out: list[GPUInfo] = []
    if not r.ok:
        return out
    seen = set()
    for i, line in enumerate(r.stdout.strip().splitlines()):
        parts = line.split("|")
        if len(parts) < 4 or parts[0] in seen:
            continue
        seen.add(parts[0])
        name, provider, mem, drv = parts
        if "Basic Display" in name or "Remote Display" in name:
            continue
        try:
            vram = round(int(mem) / GB, 2) if mem and int(mem) > 0 else None
        except ValueError:
            vram = None
        out.append(GPUInfo(len(out), _gpu_vendor(name, provider), name, vram, None, None, None, None, drv or None,
                           "registry"))
    return out


def _gpu_vendor(name: str, provider: str = "") -> str | None:
    s = f"{name} {provider}".lower()
    for key, v in (("nvidia", "NVIDIA"), ("amd", "AMD"), ("radeon", "AMD"), ("intel", "Intel"),
                   ("qualcomm", "Qualcomm"), ("apple", "Apple")):
        if key in s:
            return v
    return None


def _linux_gpus() -> list[GPUInfo]:
    r = run(["lspci"], timeout=5) if which("lspci") else None
    out = []
    if r and r.ok:
        for line in r.stdout.splitlines():
            if "VGA" in line or "3D controller" in line:
                name = line.split(":", 2)[-1].strip()
                out.append(GPUInfo(len(out), _gpu_vendor(name), name, source="lspci"))
    return out


def detect_gpus() -> list[GPUInfo]:
    nv = _nvidia_smi()
    others: list[GPUInfo] = []
    if sys.platform == "win32":
        others = _windows_gpus()
    elif sys.platform.startswith("linux"):
        others = _linux_gpus()
    # nvidia-smi gives live data for NVIDIA cards; keep other vendors from the OS listing.
    merged = list(nv)
    for g in others:
        if g.vendor == "NVIDIA" and nv:
            continue
        g.index = len(merged)
        merged.append(g)
    return merged


