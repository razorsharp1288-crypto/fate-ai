from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SandboxLimits:
    timeout_s: int = 60
    cpu_limit: float = 1.0        # cores (container) / fraction of machine (process, Windows job)
    memory_mb: int = 512
    output_limit_kb: int = 512
    max_processes: int = 64
    allow_network: bool = False


@dataclass
class ExecutionResult:
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    killed: bool = False
    truncated: bool = False
    peak_memory_mb: float | None = None
    enforced: list[str] = field(default_factory=list)   # limits actually enforced by the OS/runtime
    not_enforced: list[str] = field(default_factory=list)  # limits that could not be enforced

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.killed


ISOLATION_DESCRIPTIONS = {
    "process": ("Level 1 — Restricted process",
                "Runs on your PC in a separate folder with a scrubbed environment, time/output limits and "
                "(on Windows) a Job Object enforcing memory/CPU/process caps. It is NOT a security boundary: "
                "code can still read files your account can read and use the network. Use only for code you trust."),
    "container": ("Level 2 — Container",
                  "Runs inside a Docker/Podman container with no network by default, dropped capabilities, "
                  "CPU/memory/process limits and only the sandbox folder mounted. Good isolation for untrusted code."),
    "vm": ("Level 3 — Virtual machine",
           "Runs inside a dedicated VM (VirtualBox or Hyper-V) and can revert to a clean snapshot after each run. "
           "Strongest isolation; requires a prepared VM with guest tools and an account."),
}
