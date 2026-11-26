"""Oracle VirtualBox via VBoxManage (must be installed by the user)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ...core.exceptions import VirtualizationError
from ...utilities.proc import run
from .base import BackendStatus, Cap, Snapshot, VirtualizationBackend, VMInfo, VMSpec

_STATE = {"running": "running", "poweroff": "stopped", "aborted": "stopped", "paused": "paused",
          "saved": "saved", "starting": "running", "stopping": "running"}

OS_TYPES = {"Linux (64-bit)": "Linux_64", "Ubuntu (64-bit)": "Ubuntu_64", "Debian (64-bit)": "Debian_64",
            "Windows 11 (64-bit)": "Windows11_64", "Windows 10 (64-bit)": "Windows10_64", "Other": "Other"}


class VirtualBoxBackend(VirtualizationBackend):
    name = "virtualbox"
    label = "VirtualBox"
    caps = {Cap.CREATE, Cap.START, Cap.STOP, Cap.FORCE_STOP, Cap.PAUSE, Cap.DELETE, Cap.CLONE, Cap.SNAPSHOT,
            Cap.CONSOLE, Cap.SET_RESOURCES, Cap.ISO}
    gpu_note = ("VirtualBox provides only emulated 3D graphics (VMSVGA). It cannot pass a physical GPU to "
                "the guest on Windows hosts, so AI workloads in VirtualBox VMs run on CPU.")

    def __init__(self, vboxmanage: str | None, storage_dir: str | None = None):
        self.exe = vboxmanage
        self.storage_dir = storage_dir

    def _run(self, *args: str, timeout: float = 120) -> str:
        if not self.exe:
            raise VirtualizationError("VirtualBox is not installed.")
        r = run([self.exe, *args], timeout=timeout)
        if not r.ok:
            raise VirtualizationError("VirtualBox: " + (r.stderr.strip().splitlines() or ["failed"])[-1])
        return r.stdout

    def status(self) -> BackendStatus:
        if not self.exe:
            return BackendStatus(False, "VirtualBox not found. Install it from virtualbox.org.")
        r = run([self.exe, "--version"], timeout=15)
        if not r.ok:
            return BackendStatus(False, "VBoxManage failed: " + r.stderr.strip()[:200])
        return BackendStatus(True, "VirtualBox is installed.", r.stdout.strip())

    @staticmethod
    def _parse_info(text: str) -> dict[str, str]:
        out = {}
        for line in text.splitlines():
            m = re.match(r'^"?([^"=]+)"?="?(.*?)"?$', line)
            if m:
                out[m.group(1)] = m.group(2)
        return out

    def info(self, vm_id: str) -> VMInfo:
        d = self._parse_info(self._run("showvminfo", vm_id, "--machinereadable"))
        return VMInfo(id=d.get("UUID", vm_id), name=d.get("name", vm_id), backend=self.name,
                      state=_STATE.get(d.get("VMState", ""), "unknown"), os_type=d.get("ostype", ""),
                      cpus=int(d["cpus"]) if d.get("cpus", "").isdigit() else None,
                      memory_mb=int(d["memory"]) if d.get("memory", "").isdigit() else None,
                      network=d.get("nic1"), gpu="Emulated (no passthrough)",
                      extra={"last_state_change": d.get("VMStateChangeTime", "")})

    def list(self) -> list[VMInfo]:
        out = self._run("list", "vms")
        ids = re.findall(r"\{([0-9a-fA-F\-]+)\}", out)
        result = []
        for uid in ids:
            try:
                result.append(self.info(uid))
            except VirtualizationError:
                continue
        return result

    def create(self, spec: VMSpec) -> VMInfo:
        ostype = OS_TYPES.get(spec.os_type, "Other")
        args = ["createvm", "--name", spec.name, "--ostype", ostype, "--register"]
        if self.storage_dir:
            args += ["--basefolder", self.storage_dir]
        self._run(*args)
        self._run("modifyvm", spec.name, "--cpus", str(spec.cpus), "--memory", str(spec.memory_mb),
                  "--nic1", "none" if spec.network == "none" else "nat", "--graphicscontroller", "vmsvga",
                  "--firmware", "efi" if "Windows 11" in spec.os_type else "bios")
        info = self._parse_info(self._run("showvminfo", spec.name, "--machinereadable"))
        cfg = Path(info.get("CfgFile", "")).parent
        disk = cfg / f"{spec.name}.vdi"
        self._run("createmedium", "disk", "--filename", str(disk), "--size", str(spec.disk_gb * 1024), timeout=600)
        self._run("storagectl", spec.name, "--name", "SATA", "--add", "sata", "--controller", "IntelAhci")
        self._run("storageattach", spec.name, "--storagectl", "SATA", "--port", "0", "--device", "0",
                  "--type", "hdd", "--medium", str(disk))
        if spec.iso_path:
            self._run("storageattach", spec.name, "--storagectl", "SATA", "--port", "1", "--device", "0",
                      "--type", "dvddrive", "--medium", spec.iso_path)
        if spec.shared_folder:
            self._run("sharedfolder", "add", spec.name, "--name", "fate_shared", "--hostpath",
                      spec.shared_folder, "--readonly")
        if spec.start_after_create:
            self.start(spec.name)
        return self.info(spec.name)

    def start(self, vm_id: str) -> None:
        # "headless" keeps the VM running in the background independent of FATE AI.
        self._run("startvm", vm_id, "--type", "headless", timeout=180)

    def stop(self, vm_id: str, force: bool = False) -> None:
        self._run("controlvm", vm_id, "poweroff" if force else "acpipowerbutton")

    def pause(self, vm_id: str) -> None:
        self._run("controlvm", vm_id, "pause")

    def resume(self, vm_id: str) -> None:
        self._run("controlvm", vm_id, "resume")

    def delete(self, vm_id: str) -> None:
        self._run("unregistervm", vm_id, "--delete", timeout=600)

    def clone(self, vm_id: str, new_name: str) -> VMInfo:
        self._run("clonevm", vm_id, "--name", new_name, "--register", timeout=3600)
        return self.info(new_name)

    def snapshots(self, vm_id: str) -> list[Snapshot]:
        r = run([self.exe, "snapshot", vm_id, "list", "--machinereadable"], timeout=60) if self.exe else None
        if not r or not r.ok:
            return []
        d = self._parse_info(r.stdout)
        return [Snapshot(v, v) for k, v in d.items() if k.startswith("SnapshotName")]

    def create_snapshot(self, vm_id: str, name: str) -> None:
        self._run("snapshot", vm_id, "take", name, timeout=600)

    def restore_snapshot(self, vm_id: str, snapshot: str) -> None:
        self._run("snapshot", vm_id, "restore", snapshot, timeout=600)

    def delete_snapshot(self, vm_id: str, snapshot: str) -> None:
        self._run("snapshot", vm_id, "delete", snapshot, timeout=600)

    def set_resources(self, vm_id: str, cpus: int | None = None, memory_mb: int | None = None) -> None:
        args = []
        if cpus:
            args += ["--cpus", str(int(cpus))]
        if memory_mb:
            args += ["--memory", str(int(memory_mb))]
        if args:
            self._run("modifyvm", vm_id, *args)

    def set_cpu_limit(self, vm_id: str, percent: int) -> None:
        self._run("modifyvm", vm_id, "--cpuexecutioncap", str(max(1, min(100, int(percent)))))

    def open_console(self, vm_id: str) -> None:
        exe = Path(self.exe).with_name("VirtualBox.exe" if self.exe.lower().endswith(".exe") else "VirtualBox")
        subprocess.Popen([str(exe), "--startvm", vm_id, "--separate"])
