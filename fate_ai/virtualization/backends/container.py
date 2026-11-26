"""Docker / Podman containers as lightweight environments."""
from __future__ import annotations

import json

from ...core.exceptions import VirtualizationError
from ...utilities.proc import CmdResult, run
from .base import BackendStatus, Cap, VirtualizationBackend, VMInfo, VMSpec

LABEL = "fate-ai.managed=1"


class ContainerBackend(VirtualizationBackend):
    kind = "container"
    caps = {Cap.CREATE, Cap.START, Cap.STOP, Cap.FORCE_STOP, Cap.PAUSE, Cap.DELETE, Cap.SNAPSHOT,
            Cap.EXEC, Cap.SET_RESOURCES}
    gpu_note = ("Containers can use NVIDIA GPUs with '--gpus all' when Docker Desktop's WSL2 backend and the "
                "NVIDIA driver are installed. AMD/Intel GPU access in containers on Windows is limited.")

    def __init__(self, exe: str | None, name: str = "docker"):
        self.exe = exe
        self.name = name
        self.label = "Docker" if name == "docker" else "Podman"

    def _run(self, *args: str, timeout: float = 120) -> str:
        if not self.exe:
            raise VirtualizationError(f"{self.label} is not installed.")
        r = run([self.exe, *args], timeout=timeout)
        if not r.ok:
            raise VirtualizationError(f"{self.label}: " + (r.stderr.strip() or r.stdout.strip())[-400:])
        return r.stdout

    def raw(self, *args: str, timeout: float = 120) -> CmdResult:
        return run([self.exe, *args], timeout=timeout)

    def status(self) -> BackendStatus:
        if not self.exe:
            return BackendStatus(False, f"{self.label} not found on PATH.")
        r = run([self.exe, "version", "--format", "{{.Server.Version}}"], timeout=20)
        if not r.ok or not r.stdout.strip():
            return BackendStatus(False, f"{self.label} is installed but the engine is not running.")
        return BackendStatus(True, f"{self.label} engine running.", r.stdout.strip())

    def list(self) -> list[VMInfo]:
        out = self._run("ps", "-a", "--filter", f"label={LABEL}", "--format", "{{json .}}")
        vms = []
        stats = self._stats()
        for line in out.splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            state = str(d.get("State", "")).lower()
            name = d.get("Names", d.get("Name", ""))
            if isinstance(name, list):
                name = name[0]
            cid = d.get("ID", d.get("Id", ""))
            s = stats.get(name) or stats.get(cid[:12], {})
            vms.append(VMInfo(id=cid, name=name, backend=self.name,
                              state="running" if state == "running" else "paused" if state == "paused" else "stopped",
                              os_type=d.get("Image", ""), cpu_usage=s.get("cpu"), memory_usage_mb=s.get("mem"),
                              extra={"status": d.get("Status", "")}))
        return vms

    def _stats(self) -> dict:
        r = run([self.exe, "stats", "--no-stream", "--format", "{{json .}}"], timeout=30) if self.exe else None
        out = {}
        if r and r.ok:
            for line in r.stdout.splitlines():
                try:
                    d = json.loads(line)
                    cpu = float(str(d.get("CPUPerc", "0")).rstrip("%") or 0)
                    mem = str(d.get("MemUsage", "0MiB")).split("/")[0].strip()
                    out[d.get("Name", "")] = {"cpu": cpu, "mem": _to_mb(mem)}
                    out[d.get("ID", "")[:12]] = out[d.get("Name", "")]
                except (ValueError, json.JSONDecodeError):
                    continue
        return out

    def create(self, spec: VMSpec) -> VMInfo:
        image = spec.image or "ubuntu:24.04"
        args = ["create", "--name", spec.name, "--label", LABEL, "-it",
                f"--cpus={spec.cpus}", f"--memory={spec.memory_mb}m", "--pids-limit=512"]
        if spec.network == "none":
            args.append("--network=none")
        if spec.shared_folder:
            args += ["-v", f"{spec.shared_folder}:/shared:ro"]
        args += [image, "sleep", "infinity"]
        self._run(*args, timeout=1800)
        if spec.start_after_create:
            self.start(spec.name)
        return next(v for v in self.list() if v.name == spec.name)

    def start(self, vm_id: str) -> None:
        self._run("start", vm_id)

    def stop(self, vm_id: str, force: bool = False) -> None:
        self._run("kill" if force else "stop", vm_id, timeout=60)

    def pause(self, vm_id: str) -> None:
        self._run("pause", vm_id)

    def resume(self, vm_id: str) -> None:
        self._run("unpause", vm_id)

    def delete(self, vm_id: str) -> None:
        self._run("rm", "-f", vm_id)

    def create_snapshot(self, vm_id: str, name: str) -> None:
        tag = "".join(c if c.isalnum() or c in "-_." else "-" for c in name.lower())
        self._run("commit", vm_id, f"fate-snapshot/{vm_id[:12]}:{tag}", timeout=1800)

    def set_resources(self, vm_id: str, cpus: int | None = None, memory_mb: int | None = None) -> None:
        args = ["update"]
        if cpus:
            args.append(f"--cpus={cpus}")
        if memory_mb:
            args += [f"--memory={memory_mb}m", f"--memory-swap={memory_mb}m"]
        self._run(*args, vm_id)

    def exec(self, vm_id: str, command: list[str], timeout: float = 60) -> CmdResult:
        return run([self.exe, "exec", vm_id, *command], timeout=timeout)


def _to_mb(s: str) -> float | None:
    units = {"b": 1 / 1024 ** 2, "kib": 1 / 1024, "kb": 1 / 1024, "mib": 1, "mb": 1, "gib": 1024, "gb": 1024}
    s = s.strip().lower()
    for u in sorted(units, key=len, reverse=True):
        if s.endswith(u):
            try:
                return float(s[: -len(u)]) * units[u]
            except ValueError:
                return None
    return None
