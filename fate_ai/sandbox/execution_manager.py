"""Sandbox lifecycle: create, import, run, reset, export, delete."""
from __future__ import annotations

import shlex
import shutil
import sys
import zipfile
from pathlib import Path

from ..core.exceptions import SandboxError
from ..security.paths import is_within, safe_name
from ..utilities.proc import which
from .base import ExecutionResult, SandboxLimits
from .container_sandbox import ContainerSandbox
from .process_sandbox import ProcessSandbox

_IGNORED = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".venv", "venv", "*.pyc")


class ExecutionManager:
    def __init__(self, root: Path, repo, runs_repo, settings, audit=None, credentials=None, vm_manager=None):
        self.root = Path(root)
        self.repo = repo
        self.runs = runs_repo
        self.settings = settings
        self.audit = audit
        self.credentials = credentials
        self.vm_manager = vm_manager
        self._active: dict[int, object] = {}

    # -- lifecycle --------------------------------------------------------
    def create(self, name: str, level: str = "process", config: dict | None = None) -> dict:
        if level not in ("process", "container", "vm"):
            raise SandboxError("Unknown isolation level")
        s = getattr(self.settings, "settings", self.settings).sandbox
        cfg = {"timeout_s": s.timeout_seconds, "cpu_limit": s.cpu_limit, "memory_mb": s.memory_limit_mb,
               "output_limit_kb": s.output_limit_kb, "allow_network": s.allow_network,
               "image": s.container_image, "max_processes": 64}
        cfg.update(config or {})
        base = safe_name(name)
        workdir = self.root / base
        i = 1
        while workdir.exists():
            i += 1
            workdir = self.root / f"{base}-{i}"
        workdir.mkdir(parents=True)
        sid = self.repo.create(name=name, level=level, workdir=str(workdir), config=cfg)
        self._audit("sandbox_created", f"{name} level={level}")
        return self.repo.get(sid)

    def get(self, sid: int) -> dict:
        sb = self.repo.get(sid)
        if not sb:
            raise SandboxError("Sandbox not found")
        return sb

    def list(self) -> list[dict]:
        return self.repo.list()

    def update_config(self, sid: int, **cfg) -> dict:
        sb = self.get(sid)
        sb["config"].update(cfg)
        self.repo.update(sid, config=sb["config"])
        return self.get(sid)

    def import_project(self, sid: int, source: Path) -> int:
        sb = self.get(sid)
        source = Path(source)
        if not source.exists():
            raise SandboxError("Source does not exist")
        dest = Path(sb["workdir"])
        if source.is_dir():
            shutil.copytree(source, dest / source.name, ignore=_IGNORED, dirs_exist_ok=True, symlinks=False)
        else:
            shutil.copy2(source, dest / source.name)
        self._audit("sandbox_import", f"{sb['name']} <- {source.name}")
        return sum(1 for _ in dest.rglob("*") if _.is_file())

    def write_file(self, sid: int, relname: str, content: str) -> Path:
        from ..security.paths import resolve_inside
        sb = self.get(sid)
        target = resolve_inside(sb["workdir"], relname)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, "utf-8")
        return target

    def files(self, sid: int) -> list[str]:
        wd = Path(self.get(sid)["workdir"])
        return sorted(str(p.relative_to(wd)) for p in wd.rglob("*") if p.is_file() and ".tmp" not in p.parts)

    def reset(self, sid: int) -> None:
        """Wipe the sandbox's working directory (or revert its VM snapshot)."""
        sb = self.get(sid)
        if sb["level"] == "vm":
            self._vm_sandbox(sb).reset()
        wd = Path(sb["workdir"])
        if wd.exists() and is_within(wd, self.root):
            shutil.rmtree(wd)
        wd.mkdir(parents=True, exist_ok=True)
        self._audit("sandbox_reset", sb["name"])

    def delete(self, sid: int) -> None:
        sb = self.get(sid)
        self.stop(sid)
        wd = Path(sb["workdir"])
        if wd.exists() and is_within(wd, self.root):
            shutil.rmtree(wd, ignore_errors=True)
        self.repo.delete(sid)
        self._audit("sandbox_deleted", sb["name"])

    def export_results(self, sid: int, dest_zip: Path) -> Path:
        sb = self.get(sid)
        wd = Path(sb["workdir"])
        dest_zip = Path(dest_zip)
        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for p in wd.rglob("*"):
                if p.is_file() and ".tmp" not in p.parts and not p.is_symlink():
                    z.write(p, p.relative_to(wd))
            runs = self.runs.list(sid)
            log = "\n\n".join(f"$ {r['command']}\nexit={r['exit_code']} time={r['duration_ms']}ms "
                              f"timeout={bool(r['timed_out'])}\n--- stdout ---\n{r['stdout']}\n--- stderr ---\n"
                              f"{r['stderr']}" for r in runs)
            z.writestr("_fate_run_log.txt", log)
        return dest_zip

    # -- execution --------------------------------------------------------
    def limits_for(self, sb: dict) -> SandboxLimits:
        c = sb["config"]
        return SandboxLimits(timeout_s=int(c.get("timeout_s", 60)), cpu_limit=float(c.get("cpu_limit", 1)),
                             memory_mb=int(c.get("memory_mb", 512)), output_limit_kb=int(c.get("output_limit_kb", 512)),
                             max_processes=int(c.get("max_processes", 64)),
                             allow_network=bool(c.get("allow_network", False)))

    @staticmethod
    def parse_command(command: str) -> list[str]:
        try:
            argv = shlex.split(command, posix=sys.platform != "win32")
        except ValueError as e:
            raise SandboxError(f"Could not parse command: {e}") from None
        if sys.platform == "win32":
            argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] and a[0] in "\"'" else a for a in argv]
        if not argv:
            raise SandboxError("Empty command")
        return argv

    def _container_engine(self) -> str | None:
        return which("docker") or which("podman")

    def _vm_sandbox(self, sb: dict):
        from .vm_sandbox import VMSandbox
        c = sb["config"]
        if not self.vm_manager or not c.get("vm_backend") or not c.get("vm_id"):
            raise SandboxError("Choose a VM, guest user and password for this sandbox first.")
        backend = self.vm_manager.backend(c["vm_backend"])
        pw = self.credentials.get_api_key(f"sandbox-vm-{sb['id']}") if self.credentials else None
        if not pw:
            raise SandboxError("Guest password not set for this VM sandbox.")
        return VMSandbox(backend, c["vm_id"], c.get("vm_user", ""), pw, self.limits_for(sb),
                         c.get("guest_dir", "/tmp/fate"))

    def run(self, sid: int, command: str, on_output=None, host_consent: bool = False) -> ExecutionResult:
        sb = self.get(sid)
        argv = self.parse_command(command)
        limits = self.limits_for(sb)
        wd = Path(sb["workdir"])
        if sb["level"] == "process":
            if not host_consent:
                raise SandboxError("Level 1 runs on your PC without full isolation; explicit consent is required.")
            if argv[0] in ("python", "python3") and getattr(sys, "frozen", False):
                py = which("python") or which("py")
                if not py:
                    raise SandboxError("Python is not installed on this PC. Use a container sandbox instead.")
                argv[0] = py
            elif argv[0] in ("python", "python3") and not which(argv[0]):
                argv[0] = sys.executable
            box = ProcessSandbox(wd, limits)
        elif sb["level"] == "container":
            box = ContainerSandbox(self._container_engine(), wd, limits, sb["config"].get("image", "python:3.12-slim"))
        else:
            box = self._vm_sandbox(sb)
            self._active[sid] = box
            res = box.run(wd, argv, revert_after=sb["config"].get("revert_after", True), on_output=on_output)
            self._active.pop(sid, None)
            self._record(sid, res)
            return res
        self._active[sid] = box
        try:
            res = box.run(argv, on_output=on_output)
        finally:
            self._active.pop(sid, None)
        self._record(sid, res)
        return res

    def _record(self, sid: int, res: ExecutionResult) -> None:
        self.runs.record(sid, res.command, res.exit_code, res.duration_ms, res.stdout[-200_000:],
                         res.stderr[-200_000:], res.timed_out)
        self._audit("sandbox_run", f"sandbox={sid} cmd={res.command[:200]} exit={res.exit_code}")

    def is_running(self, sid: int) -> bool:
        return sid in self._active

    def stop(self, sid: int) -> None:
        box = self._active.get(sid)
        if box is not None and hasattr(box, "kill"):
            box.kill()

    def stop_all(self) -> None:
        for sid in list(self._active):
            self.stop(sid)

    def _audit(self, action, detail):
        if self.audit:
            self.audit.log("sandbox", action, detail)
