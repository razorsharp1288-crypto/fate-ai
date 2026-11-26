"""Level 2: Docker/Podman container with strict defaults."""
from __future__ import annotations

import subprocess
import threading
import time
import uuid
from pathlib import Path

from ..core.exceptions import SandboxError
from ..utilities.proc import CREATE_NO_WINDOW, run
from .base import ExecutionResult, SandboxLimits


class ContainerSandbox:
    level = "container"

    def __init__(self, engine_exe: str | None, workdir: Path, limits: SandboxLimits,
                 image: str = "python:3.12-slim"):
        if not engine_exe:
            raise SandboxError("Docker or Podman is required for container sandboxes.")
        self.exe = engine_exe
        self.workdir = Path(workdir)
        self.limits = limits
        self.image = image
        self._name: str | None = None

    def engine_ready(self) -> bool:
        return run([self.exe, "info", "--format", "{{.ServerVersion}}"], timeout=20).ok

    def build_args(self, argv: list[str], name: str) -> list[str]:
        lim = self.limits
        args = [self.exe, "run", "--rm", "--name", name, "--label", "fate-ai.sandbox=1",
                f"--cpus={lim.cpu_limit}", f"--memory={lim.memory_mb}m", f"--memory-swap={lim.memory_mb}m",
                f"--pids-limit={lim.max_processes}", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--read-only", "--tmpfs", "/tmp:rw,size=64m", "-v", f"{self.workdir}:/work:rw", "-w", "/work",
                "-e", "HOME=/work", "-e", "PYTHONUNBUFFERED=1", "-e", "PYTHONDONTWRITEBYTECODE=1"]
        if not lim.allow_network:
            args.append("--network=none")
        return args + [self.image, *argv]

    def run(self, argv: list[str], on_output=None) -> ExecutionResult:
        if not self.engine_ready():
            raise SandboxError("The container engine is not running. Start Docker Desktop or Podman.")
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._name = f"fate-sbx-{uuid.uuid4().hex[:10]}"
        args = self.build_args(argv, self._name)
        lim = self.limits
        enforced = [f"CPU ≤ {lim.cpu_limit} cores", f"memory ≤ {lim.memory_mb} MB", f"≤ {lim.max_processes} processes",
                    "all capabilities dropped", "read-only root filesystem", "only sandbox folder mounted",
                    f"timeout {lim.timeout_s}s", f"output ≤ {lim.output_limit_kb} KB"]
        enforced.append("no network" if not lim.allow_network else "network allowed (user setting)")
        start = time.perf_counter()
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW)
        cap = lim.output_limit_kb * 1024
        bufs = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = [False]

        def pump(stream, name):
            for chunk in iter(lambda: stream.read1(4096), b""):
                b = bufs[name]
                if len(b) < cap:
                    b.extend(chunk[: cap - len(b)])
                    if on_output:
                        on_output(name, chunk.decode("utf-8", "replace"))
                else:
                    truncated[0] = True

        ts = [threading.Thread(target=pump, args=(p.stdout, "stdout"), daemon=True),
              threading.Thread(target=pump, args=(p.stderr, "stderr"), daemon=True)]
        for t in ts:
            t.start()
        timed_out = False
        try:
            p.wait(timeout=lim.timeout_s + 30)  # allow container start-up time
        except subprocess.TimeoutExpired:
            timed_out = True
            self.kill()
            p.wait(timeout=30)
        for t in ts:
            t.join(timeout=5)
        code = p.returncode
        # 137 = SIGKILL, commonly the OOM killer
        stderr = bufs["stderr"].decode("utf-8", "replace")
        if code == 137 and not timed_out:
            stderr += "\n[FATE] Process was killed (exit 137) — most likely it exceeded the memory limit."
        return ExecutionResult(" ".join(argv), code, bufs["stdout"].decode("utf-8", "replace"), stderr,
                               int((time.perf_counter() - start) * 1000), timed_out, False, truncated[0], None,
                               enforced, [])

    def kill(self) -> None:
        if self._name:
            run([self.exe, "kill", self._name], timeout=30)
