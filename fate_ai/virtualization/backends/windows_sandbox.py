"""Windows Sandbox: Microsoft's built-in disposable VM (Windows 10/11 Pro, Enterprise, Education).

Each FATE environment is a ``.wsb`` configuration file (memory, networking, vGPU,
mapped folder, logon command). Starting opens a fresh, clean Windows desktop in a
lightweight Hyper-V VM; everything inside is discarded when it closes. Only one
Windows Sandbox can run at a time (a Windows limitation).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import psutil

from ...core.exceptions import VirtualizationError
from .base import BackendStatus, Cap, VirtualizationBackend, VMInfo, VMSpec

PROCESS_NAMES = {"windowssandbox.exe", "windowssandboxclient.exe", "windowssandboxremotesession.exe"}


def exe_path() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsSandbox.exe"


def build_wsb(spec: VMSpec, gpu: bool = True) -> str:
    parts = ["<Configuration>",
             f"  <VGpu>{'Enable' if gpu else 'Disable'}</VGpu>",
             f"  <Networking>{'Disable' if spec.network == 'none' else 'Enable'}</Networking>",
             f"  <MemoryInMB>{int(spec.memory_mb)}</MemoryInMB>",
             "  <ClipboardRedirection>Enable</ClipboardRedirection>",
             "  <ProtectedClient>Enable</ProtectedClient>"]
    if spec.shared_folder:
        parts += ["  <MappedFolders>", "    <MappedFolder>",
                  f"      <HostFolder>{escape(spec.shared_folder)}</HostFolder>",
                  r"      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\Shared</SandboxFolder>",
                  "      <ReadOnly>true</ReadOnly>", "    </MappedFolder>", "  </MappedFolders>"]
    if spec.image:  # optional logon command
        parts += ["  <LogonCommand>", f"    <Command>{escape(spec.image)}</Command>", "  </LogonCommand>"]
    parts.append("</Configuration>")
    return "\n".join(parts) + "\n"


class WindowsSandboxBackend(VirtualizationBackend):
    name = "winsandbox"
    label = "Windows Sandbox"
    kind = "vm"
    caps = {Cap.CREATE, Cap.START, Cap.STOP, Cap.FORCE_STOP, Cap.DELETE}
    gpu_note = ("Windows Sandbox can share your GPU through Windows' virtual GPU (vGPU) — good for testing apps. "
                "It runs one disposable Windows desktop at a time; everything inside is erased when you close it.")

    def __init__(self, storage_dir: Path | str | None = None):
        if storage_dir is None:
            from ...utilities.paths import default_data_dir
            storage_dir = default_data_dir() / "vms" / "windows-sandbox"
        self.dir = Path(storage_dir)

    def status(self) -> BackendStatus:
        if sys.platform != "win32":
            return BackendStatus(False, "Windows Sandbox is only available on Windows.")
        if exe_path().exists():
            return BackendStatus(True, "Windows Sandbox is enabled.")
        return BackendStatus(False, "Windows Sandbox is not enabled. Use “Set up” below (Windows Pro, Enterprise or "
                                    "Education; not available on Home).")

    def _meta(self) -> dict:
        f = self.dir / "fate-meta.json"
        try:
            return json.loads(f.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_meta(self, meta: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "fate-meta.json").write_text(json.dumps(meta, indent=2), "utf-8")

    @staticmethod
    def running() -> bool:
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info["name"] or "").lower() in PROCESS_NAMES:
                    return True
            except psutil.Error:
                continue
        return False

    def _file(self, vm_id: str) -> Path:
        f = (self.dir / f"{vm_id}.wsb").resolve()
        if f.parent != self.dir.resolve():
            raise VirtualizationError("Invalid environment name")
        return f

    def list(self) -> list[VMInfo]:
        meta = self._meta()
        active = meta.get("_active") if self.running() else None
        out = []
        for f in sorted(self.dir.glob("*.wsb")) if self.dir.exists() else []:
            m = meta.get(f.stem, {})
            out.append(VMInfo(id=f.stem, name=f.stem, backend=self.name,
                              state="running" if f.stem == active else "stopped", os_type="Windows (disposable)",
                              cpus=None, memory_mb=m.get("memory_mb"),
                              network="none" if m.get("network") == "none" else "nat",
                              gpu="vGPU (shared)" if m.get("gpu", True) else "Disabled"))
        return out

    def create(self, spec: VMSpec) -> VMInfo:
        from ..resource_limits import validate_env_name
        name = validate_env_name(spec.name)
        f = self._file(name)
        if f.exists():
            raise VirtualizationError(f"An environment named '{name}' already exists.")
        self.dir.mkdir(parents=True, exist_ok=True)
        f.write_text(build_wsb(spec), "utf-8")
        meta = self._meta()
        meta[name] = {"memory_mb": spec.memory_mb, "network": spec.network, "gpu": True,
                      "shared_folder": spec.shared_folder}
        self._save_meta(meta)
        if spec.start_after_create:
            self.start(name)
        return next(v for v in self.list() if v.id == name)

    def start(self, vm_id: str) -> None:
        if sys.platform != "win32":
            raise VirtualizationError("Windows Sandbox is only available on Windows.")
        if self.running():
            raise VirtualizationError("A Windows Sandbox is already running — Windows allows only one at a time.")
        f = self._file(vm_id)
        if not f.exists():
            raise VirtualizationError("Environment not found.")
        os.startfile(str(f))  # noqa: S606 - opens our own generated .wsb with Windows Sandbox
        meta = self._meta()
        meta["_active"] = vm_id
        self._save_meta(meta)

    def stop(self, vm_id: str, force: bool = False) -> None:
        procs = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() in PROCESS_NAMES]
        for p in procs:
            try:
                p.kill() if force else p.terminate()
            except psutil.Error:
                pass
        psutil.wait_procs(procs, timeout=10)

    def delete(self, vm_id: str) -> None:
        f = self._file(vm_id)
        f.unlink(missing_ok=True)
        meta = self._meta()
        meta.pop(vm_id, None)
        self._save_meta(meta)
