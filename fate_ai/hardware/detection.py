"""Hardware detection. Missing values are ``None`` — never guessed."""
from __future__ import annotations

import logging
import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from ..utilities.proc import powershell, run, which

log = logging.getLogger(__name__)
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


@dataclass
class MemoryInfo:
    total_gb: float
    available_gb: float
    used_gb: float
    percent: float


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


@dataclass
class StorageInfo:
    mount: str
    total_gb: float
    free_gb: float
    percent: float


@dataclass
class VirtualizationInfo:
    cpu_supports: bool | None = None
    firmware_enabled: bool | None = None
    hypervisor_present: bool | None = None
    hyperv_available: bool | None = None
    whpx_available: bool | None = None
    wsl_available: bool | None = None
    virtualbox_path: str | None = None
    docker_path: str | None = None
    podman_path: str | None = None
    kvm_available: bool | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class SystemInfo:
    os_name: str
    os_version: str
    os_build: str | None
    architecture: str
    python: str
    hostname_hidden: bool = True  # hostname intentionally not collected


@dataclass
class HardwareSnapshot:
    cpu: CPUInfo
    memory: MemoryInfo
    gpus: list[GPUInfo]
    storage: list[StorageInfo]
    system: SystemInfo
    virtualization: VirtualizationInfo
    acceleration: list[str]

    @property
    def best_gpu_vram_gb(self) -> float | None:
        vals = [g.vram_total_gb for g in self.gpus if g.vram_total_gb]
        return max(vals) if vals else None


# ---------------------------------------------------------------------------- CPU
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


def detect_memory() -> MemoryInfo:
    vm = psutil.virtual_memory()
    return MemoryInfo(round(vm.total / GB, 2), round(vm.available / GB, 2), round((vm.total - vm.available) / GB, 2),
                      vm.percent)


# ---------------------------------------------------------------------------- GPU
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


# ---------------------------------------------------------------------------- storage
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


# ---------------------------------------------------------------------------- virtualization
_WIN_VIRT_PS = r"""
$ErrorActionPreference='SilentlyContinue'
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$hv = [bool](Get-Command Get-VM -ErrorAction SilentlyContinue)
"hyp={0};fw={1};slat={2};vmx={3};hvcmd={4}" -f $cs.HypervisorPresent, $cpu.VirtualizationFirmwareEnabled, $cpu.SecondLevelAddressTranslationExtensions, $cpu.VMMonitorModeExtensions, $hv
"""


def _tri(v: str | None) -> bool | None:
    if v is None or v == "":
        return None
    return v.strip().lower() == "true"


def detect_virtualization() -> VirtualizationInfo:
    v = VirtualizationInfo()
    v.docker_path = which("docker")
    v.podman_path = which("podman")
    vbox = which("VBoxManage")
    if not vbox and sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("VBOX_MSI_INSTALL_PATH", "")):
            cand = Path(base) / "Oracle" / "VirtualBox" / "VBoxManage.exe" if base else None
            if cand and cand.exists():
                vbox = str(cand)
                break
    v.virtualbox_path = vbox
    if sys.platform == "win32":
        r = powershell(_WIN_VIRT_PS, timeout=20)
        if r.ok:
            kv = dict(item.split("=", 1) for item in r.stdout.strip().split(";") if "=" in item)
            v.hypervisor_present = _tri(kv.get("hyp"))
            v.firmware_enabled = _tri(kv.get("fw"))
            v.cpu_supports = _tri(kv.get("vmx"))
            v.hyperv_available = _tri(kv.get("hvcmd"))
            if v.hypervisor_present and v.firmware_enabled is False:
                # When a hypervisor is running Windows reports firmware flags as False.
                v.firmware_enabled = None
                v.notes.append("A hypervisor is already running, so firmware flags are hidden by Windows.")
        v.whpx_available = Path(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WinHvPlatform.dll").exists()
        wsl = which("wsl")
        if wsl:
            r = run([wsl, "--status"], timeout=15)
            v.wsl_available = r.ok
        else:
            v.wsl_available = False
    elif sys.platform.startswith("linux"):
        flags = ""
        try:
            flags = Path("/proc/cpuinfo").read_text(errors="replace")
        except OSError:
            pass
        v.cpu_supports = (" vmx" in flags or " svm" in flags) if flags else None
        v.kvm_available = Path("/dev/kvm").exists()
        v.hypervisor_present = " hypervisor" in flags if flags else None
        v.hyperv_available = False
        v.wsl_available = False
    if not v.docker_path and not v.podman_path:
        v.notes.append("No container runtime found (install Docker Desktop or Podman for Level 2 sandboxes).")
    return v


def detect_system() -> SystemInfo:
    build = None
    ver = platform.version()
    name = platform.system()
    if sys.platform == "win32":
        try:
            wv = sys.getwindowsversion()
            build = str(wv.build)
            name = "Windows 11" if wv.build >= 22000 else "Windows 10" if wv.major == 10 else f"Windows {wv.major}"
        except Exception:
            pass
    return SystemInfo(name, ver, build, platform.machine(), platform.python_version())


def detect_acceleration(gpus: list[GPUInfo]) -> list[str]:
    acc = []
    vendors = {g.vendor for g in gpus}
    if "NVIDIA" in vendors:
        acc.append("CUDA (NVIDIA)")
    if "AMD" in vendors:
        acc.append("ROCm/Vulkan (AMD, model/driver dependent)")
    if "Intel" in vendors:
        acc.append("Vulkan/oneAPI (Intel, limited)")
    if sys.platform == "win32" and gpus:
        acc.append("DirectML (Windows)")
    if sys.platform == "darwin":
        acc.append("Metal")
    try:
        import cpuinfo  # optional
        flags = cpuinfo.get_cpu_info().get("flags", [])
        if "avx2" in flags:
            acc.append("AVX2 (CPU)")
    except Exception:
        if Path("/proc/cpuinfo").exists() and "avx2" in Path("/proc/cpuinfo").read_text(errors="replace"):
            acc.append("AVX2 (CPU)")
    return acc


def detect_all(extra_paths: list[str] | None = None) -> HardwareSnapshot:
    gpus = detect_gpus()
    return HardwareSnapshot(detect_cpu(), detect_memory(), gpus, detect_storage(extra_paths), detect_system(),
                            detect_virtualization(), detect_acceleration(gpus))
