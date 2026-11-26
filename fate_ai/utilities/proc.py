"""Subprocess helpers: no shell, hidden console windows on Windows, timeouts."""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


@dataclass
class CmdResult:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def which(name: str) -> str | None:
    return shutil.which(name)


def run(args: list[str], timeout: float = 30, input: str | None = None, cwd: str | None = None,
        env: dict | None = None) -> CmdResult:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input, cwd=cwd,
                           env=env, creationflags=CREATE_NO_WINDOW, encoding="utf-8", errors="replace")
        return CmdResult(p.returncode, p.stdout or "", p.stderr or "")
    except FileNotFoundError:
        return CmdResult(127, "", f"{args[0]} not found")
    except subprocess.TimeoutExpired:
        return CmdResult(124, "", f"{args[0]} timed out after {timeout}s")
    except OSError as e:
        return CmdResult(126, "", str(e))


def powershell(script: str, timeout: float = 30) -> CmdResult:
    """Run a PowerShell snippet (Windows only). Never interpolate user input into ``script``."""
    exe = which("powershell") or which("pwsh")
    if not exe:
        return CmdResult(127, "", "PowerShell not available")
    return run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
               timeout=timeout)


def ps_quote(value: str) -> str:
    """Quote a value as a PowerShell single-quoted literal (safe for arbitrary text)."""
    return "'" + str(value).replace("'", "''") + "'"
