"""Level 1: restricted subprocess. Honest about what it does and does not isolate."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from ..core.exceptions import SandboxError
from .base import ExecutionResult, SandboxLimits

_SAFE_ENV_KEYS = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "LANG", "LC_ALL",
                  "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS"}


def scrubbed_env(workdir: Path, extra: dict | None = None) -> dict[str, str]:
    """Environment without secrets: only an allow-list of variables is passed through."""
    env = {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV_KEYS}
    tmp = workdir / ".tmp"
    tmp.mkdir(exist_ok=True)
    env.update({"HOME": str(workdir), "USERPROFILE": str(workdir), "TEMP": str(tmp), "TMP": str(tmp),
                "TMPDIR": str(tmp), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
                "FATE_SANDBOX": "1"})
    for k, v in (extra or {}).items():
        if k.upper() not in {"PATH", "SYSTEMROOT"}:
            env[str(k)] = str(v)
    return env


class _WindowsJob:
    """Wraps a Windows Job Object enforcing memory, CPU-rate and process-count limits."""

    def __init__(self, limits: SandboxLimits):
        import ctypes
        from ctypes import wintypes as wt
        self.ctypes = ctypes
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.handle = self.k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
        self.enforced: list[str] = []

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                        "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD),
                        ("SchedulingClass", wt.DWORD)]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        class CPU_RATE(ctypes.Structure):
            _fields_ = [("ControlFlags", wt.DWORD), ("CpuRate", wt.DWORD)]

        self.EXTENDED = EXTENDED
        JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
        JOB_OBJECT_LIMIT_PRIORITY_CLASS = 0x20
        JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200
        JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x400
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = (JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_JOB_MEMORY |
                                                 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
                                                 JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION |
                                                 JOB_OBJECT_LIMIT_PRIORITY_CLASS)
        info.BasicLimitInformation.ActiveProcessLimit = limits.max_processes
        info.BasicLimitInformation.PriorityClass = 0x4000  # BELOW_NORMAL_PRIORITY_CLASS
        info.JobMemoryLimit = limits.memory_mb * 1024 * 1024
        if self.k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.enforced += [f"memory ≤ {limits.memory_mb} MB", f"≤ {limits.max_processes} processes",
                              "below-normal priority", "kill on close"]
        # CPU hard cap: CpuRate is in 1/100 of a percent of the whole machine.
        ncpu = os.cpu_count() or 1
        pct = max(1, min(100, int(limits.cpu_limit / ncpu * 100)))
        rate = CPU_RATE(0x1 | 0x4, pct * 100)  # ENABLE | HARD_CAP
        if self.k32.SetInformationJobObject(self.handle, 15, ctypes.byref(rate), ctypes.sizeof(rate)):
            self.enforced.append(f"CPU ≤ {pct}% of machine")

    def assign(self, proc: subprocess.Popen) -> None:
        if not self.k32.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise OSError(self.ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def peak_memory_mb(self) -> float | None:
        info = self.EXTENDED()
        ok = self.k32.QueryInformationJobObject(self.handle, 9, self.ctypes.byref(info),
                                                self.ctypes.sizeof(info), None)
        return info.PeakJobMemoryUsed / 2 ** 20 if ok else None

    def terminate(self) -> None:
        self.k32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle:
            self.k32.CloseHandle(self.handle)
            self.handle = None


def _posix_limits(limits: SandboxLimits):
    def apply():  # runs in the child before exec
        import resource
        mem = limits.memory_mb * 1024 * 1024
        for res, val in ((resource.RLIMIT_AS, mem), (resource.RLIMIT_CPU, limits.timeout_s + 1),
                         (resource.RLIMIT_NPROC, limits.max_processes + 64)):
            try:
                resource.setrlimit(res, (val, val))
            except (ValueError, OSError):
                pass
        os.setsid()
        try:
            os.nice(10)
        except OSError:
            pass
    return apply


class ProcessSandbox:
    level = "process"

    def __init__(self, workdir: Path, limits: SandboxLimits):
        self.workdir = Path(workdir)
        self.limits = limits
        self._proc: subprocess.Popen | None = None
        self._job = None
        self._kill_requested = False

    def run(self, argv: list[str], on_output=None, env_extra: dict | None = None) -> ExecutionResult:
        if not argv:
            raise SandboxError("No command given")
        self.workdir.mkdir(parents=True, exist_ok=True)
        lim = self.limits
        enforced = [f"timeout {lim.timeout_s}s", f"output ≤ {lim.output_limit_kb} KB", "scrubbed environment",
                    "private working directory"]
        not_enforced = ["filesystem isolation", "network isolation" if not lim.allow_network else ""]
        kwargs: dict = dict(cwd=str(self.workdir), env=scrubbed_env(self.workdir, env_extra),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if sys.platform == "win32":
            CREATE_SUSPENDED, CREATE_NO_WINDOW, NEW_GROUP = 0x4, 0x08000000, 0x200
            kwargs["creationflags"] = CREATE_SUSPENDED | CREATE_NO_WINDOW | NEW_GROUP
            try:
                self._job = _WindowsJob(lim)
                enforced += self._job.enforced
            except OSError:
                self._job = None
                not_enforced += ["memory limit", "CPU limit"]
        else:
            kwargs["preexec_fn"] = _posix_limits(lim)
            enforced += [f"address space ≤ {lim.memory_mb} MB (rlimit)", "CPU time limit", "process-count limit",
                         "lower priority"]
            not_enforced.append("CPU percentage cap")
        start = time.perf_counter()
        self._kill_requested = False
        try:
            self._proc = subprocess.Popen(argv, **kwargs)
        except FileNotFoundError:
            raise SandboxError(f"Program not found: {argv[0]}") from None
        except OSError as e:
            raise SandboxError(f"Could not start process: {e}") from None
        if sys.platform == "win32":
            if self._job:
                try:
                    self._job.assign(self._proc)
                except OSError:
                    not_enforced += ["memory limit", "CPU limit"]
            import ctypes
            ctypes.WinDLL("ntdll").NtResumeProcess(int(self._proc._handle))

        cap = lim.output_limit_kb * 1024
        out_buf, err_buf = bytearray(), bytearray()
        truncated = [False]

        def pump(stream, buf, name):
            for chunk in iter(lambda: stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096), b""):
                if len(buf) < cap:
                    buf.extend(chunk[: cap - len(buf)])
                    if on_output:
                        on_output(name, chunk.decode("utf-8", "replace"))
                else:
                    truncated[0] = True
            stream.close()

        threads = [threading.Thread(target=pump, args=(self._proc.stdout, out_buf, "stdout"), daemon=True),
                   threading.Thread(target=pump, args=(self._proc.stderr, err_buf, "stderr"), daemon=True)]
        for t in threads:
            t.start()
        timed_out = False
        try:
            self._proc.wait(timeout=lim.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self.kill()
            self._proc.wait(timeout=10)
        for t in threads:
            t.join(timeout=5)
        peak = self._job.peak_memory_mb() if self._job else None
        if self._job:
            self._job.close()
            self._job = None
        code = self._proc.returncode
        return ExecutionResult(" ".join(argv), code, out_buf.decode("utf-8", "replace"),
                               err_buf.decode("utf-8", "replace"), int((time.perf_counter() - start) * 1000),
                               timed_out, self._kill_requested and not timed_out, truncated[0], peak,
                               enforced, [x for x in not_enforced if x])

    def kill(self) -> None:
        """Emergency stop: terminate the whole process tree."""
        self._kill_requested = True
        p = self._proc
        if p is None or p.poll() is not None:
            return
        if self._job:
            self._job.terminate()
            return
        try:
            parent = psutil.Process(p.pid)
            for c in parent.children(recursive=True):
                c.kill()
            parent.kill()
        except psutil.Error:
            pass
