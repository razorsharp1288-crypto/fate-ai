"""Hardware detection facade. Missing values are ``None`` — never guessed.

Component detectors live in cpu.py, memory.py, gpu.py and storage.py; this module
adds system/virtualization/acceleration detection and assembles a HardwareSnapshot.
"""
from __future__ import annotations

import logging
import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path


from ..utilities.proc import powershell, run, which
from .cpu import CPUInfo, detect_cpu  # noqa: F401
from .gpu import GPUInfo, _nvidia_smi, detect_gpus  # noqa: F401  (re-exported)
from .memory import MemoryInfo, detect_memory  # noqa: F401
from .storage import StorageInfo, detect_storage  # noqa: F401

log = logging.getLogger(__name__)
GB = 1024 ** 3


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
# ---------------------------------------------------------------------------- GPU
# ---------------------------------------------------------------------------- storage
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
