"""WSL2 distributions as lightweight Linux development environments."""
from __future__ import annotations

import sys

from ...core.exceptions import VirtualizationError
from ...utilities.proc import CmdResult, run, which
from .base import BackendStatus, Cap, VirtualizationBackend, VMInfo, VMSpec


def _decode(r: CmdResult) -> str:
    # wsl.exe writes UTF-16LE on older builds; strip NULs.
    return r.stdout.replace("\x00", "")


class WSLBackend(VirtualizationBackend):
    name = "wsl"
    label = "WSL2"
    kind = "wsl"
    caps = {Cap.CREATE, Cap.START, Cap.STOP, Cap.DELETE, Cap.EXEC, Cap.CONSOLE}
    gpu_note = ("WSL2 supports GPU compute (CUDA on NVIDIA, DirectML) with a recent Windows GPU driver. "
                "CPU/RAM limits are global for all distros and set in %UserProfile%\\.wslconfig.")

    def __init__(self) -> None:
        self.exe = which("wsl") if sys.platform == "win32" else None

    def status(self) -> BackendStatus:
        if not self.exe:
            return BackendStatus(False, "WSL is only available on Windows 10 2004+/Windows 11. "
                                        "Install with: wsl --install")
        r = run([self.exe, "--status"], timeout=20)
        if not r.ok:
            return BackendStatus(False, "WSL is not installed or not enabled. Run 'wsl --install' in an "
                                        "administrator terminal.")
        return BackendStatus(True, "WSL is available.")

    def list(self) -> list[VMInfo]:
        r = run([self.exe, "--list", "--verbose"], timeout=30)
        if not r.ok:
            return []
        out = []
        for line in _decode(r).splitlines()[1:]:
            parts = line.replace("*", " ").split()
            if len(parts) >= 3:
                name, state, ver = parts[0], parts[1], parts[2]
                out.append(VMInfo(id=name, name=name, backend=self.name,
                                  state="running" if state.lower() == "running" else "stopped",
                                  os_type=f"WSL{ver}", gpu="GPU compute via host driver (if supported)"))
        return out

    def online_distros(self) -> list[str]:
        r = run([self.exe, "--list", "--online"], timeout=60)
        names = []
        started = False
        for line in _decode(r).splitlines():
            if line.strip().startswith("NAME"):
                started = True
                continue
            if started and line.strip():
                names.append(line.split()[0])
        return names

    def create(self, spec: VMSpec) -> VMInfo:
        distro = spec.image or "Ubuntu"
        r = run([self.exe, "--install", "--distribution", distro, "--no-launch"], timeout=1800)
        if not r.ok:
            raise VirtualizationError("WSL install failed: " + _decode(r).strip()[-300:] + r.stderr[-300:])
        return VMInfo(id=distro, name=distro, backend=self.name, state="stopped", os_type="WSL2")

    def start(self, vm_id: str) -> None:
        r = run([self.exe, "-d", vm_id, "--exec", "true"], timeout=120)
        if not r.ok:
            raise VirtualizationError(f"Could not start {vm_id}: {r.stderr.strip()}")

    def stop(self, vm_id: str, force: bool = False) -> None:
        r = run([self.exe, "--terminate", vm_id], timeout=60)
        if not r.ok:
            raise VirtualizationError(r.stderr.strip() or "terminate failed")

    def delete(self, vm_id: str) -> None:
        r = run([self.exe, "--unregister", vm_id], timeout=300)
        if not r.ok:
            raise VirtualizationError(r.stderr.strip() or "unregister failed")

    def exec(self, vm_id: str, command: list[str], timeout: float = 60) -> CmdResult:
        return run([self.exe, "-d", vm_id, "--exec", *command], timeout=timeout)

    def open_console(self, vm_id: str) -> None:
        import subprocess
        subprocess.Popen(["cmd.exe", "/c", "start", "wsl.exe", "-d", vm_id])
