"""Level 3: run commands inside a prepared VM, reverting to a clean snapshot.

Supported executors:
* VirtualBox ``guestcontrol`` (needs Guest Additions in the VM and a guest account)
* Hyper-V PowerShell Direct (Windows guests; needs a guest account)
The guest password is stored in the OS credential vault, never in the database.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..core.exceptions import SandboxError
from ..utilities.proc import powershell, ps_quote, run
from .base import ExecutionResult, SandboxLimits

CLEAN_SNAPSHOT = "fate-sandbox-clean"


class VMSandbox:
    level = "vm"

    def __init__(self, backend, vm_id: str, username: str, password: str, limits: SandboxLimits,
                 guest_dir: str = "/tmp/fate"):
        if backend.name not in ("virtualbox", "hyperv"):
            raise SandboxError("VM sandboxes need a VirtualBox or Hyper-V VM.")
        self.backend, self.vm_id = backend, vm_id
        self.username, self.password = username, password
        self.limits = limits
        self.guest_dir = guest_dir

    def ensure_clean_snapshot(self) -> None:
        names = [s.name for s in self.backend.snapshots(self.vm_id)]
        if CLEAN_SNAPSHOT not in names:
            self.backend.create_snapshot(self.vm_id, CLEAN_SNAPSHOT)

    def reset(self) -> None:
        state = next((v.state for v in self.backend.list() if v.id == self.vm_id or v.name == self.vm_id), "")
        if state == "running":
            self.backend.stop(self.vm_id, force=True)
            time.sleep(2)
        self.backend.restore_snapshot(self.vm_id, CLEAN_SNAPSHOT)

    def run(self, workdir: Path, argv: list[str], revert_after: bool = True, on_output=None) -> ExecutionResult:
        self.ensure_clean_snapshot()
        start = time.perf_counter()
        try:
            self.backend.start(self.vm_id)
        except Exception:
            pass  # may already be running
        code, out, err = 1, "", ""
        try:
            if self.backend.name == "virtualbox":
                code, out, err = self._run_vbox(workdir, argv)
            else:
                code, out, err = self._run_hyperv(workdir, argv)
        finally:
            if revert_after:
                try:
                    self.reset()
                except Exception as e:  # report but don't mask the result
                    err += f"\n[FATE] Snapshot revert failed: {e}"
        cap = self.limits.output_limit_kb * 1024
        return ExecutionResult(" ".join(argv), code, out[:cap], err[:cap], int((time.perf_counter() - start) * 1000),
                               code == 124, False, len(out) > cap, None,
                               [x for x in ("separate virtual machine", "snapshot revert" if revert_after else "",
                                          f"timeout {self.limits.timeout_s}s") if x], [])

    def _run_vbox(self, workdir: Path, argv: list[str]):
        exe = self.backend.exe
        auth = ["--username", self.username, "--password", self.password]
        # wait for guest additions to come up
        deadline = time.time() + 180
        while time.time() < deadline:
            r = run([exe, "guestproperty", "get", self.vm_id, "/VirtualBox/GuestAdd/Version"], timeout=15)
            if r.ok and "No value" not in r.stdout:
                break
            time.sleep(3)
        run([exe, "guestcontrol", self.vm_id, "mkdir", "--parents", self.guest_dir, *auth], timeout=60)
        r = run([exe, "guestcontrol", self.vm_id, "copyto", "--recursive", "--target-directory", self.guest_dir,
                 *auth, str(workdir)], timeout=600)
        if not r.ok:
            raise SandboxError("Copy into VM failed (are Guest Additions installed?): " + r.stderr[-300:])
        target = f"{self.guest_dir}/{workdir.name}"
        cmd = "cd " + _sh_quote(target) + " && " + " ".join(_sh_quote(a) for a in argv)
        r = run([exe, "guestcontrol", self.vm_id, "run", "--exe", "/bin/sh", *auth,
                 "--timeout", str(self.limits.timeout_s * 1000), "--", "sh", "-c", cmd],
                timeout=self.limits.timeout_s + 60)
        return r.code, r.stdout, r.stderr

    def _run_hyperv(self, workdir: Path, argv: list[str]):
        vm = ps_quote(self.vm_id)
        script = (
            f"$ErrorActionPreference='Stop'; $sec = ConvertTo-SecureString {ps_quote(self.password)} -AsPlainText -Force; "
            f"$cred = New-Object System.Management.Automation.PSCredential({ps_quote(self.username)}, $sec); "
            f"$s = New-PSSession -VMName {vm} -Credential $cred; "
            f"Invoke-Command -Session $s -ScriptBlock {{ New-Item -ItemType Directory -Force C:\\fate | Out-Null }}; "
            f"Copy-Item -ToSession $s -Path {ps_quote(str(workdir))} -Destination C:\\fate -Recurse -Force; "
            f"$r = Invoke-Command -Session $s -ArgumentList (,@({', '.join(ps_quote(a) for a in argv)})) "
            f"-ScriptBlock {{ param($a) Set-Location (Join-Path C:\\fate {ps_quote(workdir.name)}); "
            f"$exe=$a[0]; $rest=@(); if ($a.Count -gt 1) {{ $rest=$a[1..($a.Count-1)] }}; "
            f"& $exe @rest 2>&1 | Out-String; $LASTEXITCODE }}; Remove-PSSession $s; $r"
        )
        r = powershell(script, timeout=self.limits.timeout_s + 120)
        lines = r.stdout.rstrip().splitlines()
        code = int(lines[-1]) if lines and lines[-1].strip().lstrip("-").isdigit() else r.code
        return code, "\n".join(lines[:-1]), r.stderr


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"
