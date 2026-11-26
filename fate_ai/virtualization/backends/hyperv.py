"""Windows Hyper-V via the Hyper-V PowerShell module.

Requires Windows Pro/Enterprise/Education with Hyper-V enabled and the user in
the "Hyper-V Administrators" group (FATE AI never self-elevates).
"""
from __future__ import annotations

import json
import subprocess
import sys

from ...core.exceptions import BackendUnavailableError, VirtualizationError
from ...utilities.proc import powershell, ps_quote, which
from .base import BackendStatus, Cap, Snapshot, VirtualizationBackend, VMInfo, VMSpec

_STATE = {"Running": "running", "Off": "stopped", "Paused": "paused", "Saved": "saved",
          "2": "running", "3": "stopped", "9": "paused", "6": "saved"}


class HyperVBackend(VirtualizationBackend):
    name = "hyperv"
    label = "Hyper-V"
    caps = {Cap.CREATE, Cap.START, Cap.STOP, Cap.FORCE_STOP, Cap.PAUSE, Cap.DELETE, Cap.SNAPSHOT,
            Cap.CONSOLE, Cap.SET_RESOURCES, Cap.DYNAMIC_MEMORY, Cap.ISO, Cap.CLONE}
    gpu_note = ("GPU partitioning (GPU-PV) needs Windows 11/Server 2022+, a supporting GPU driver and manual "
                "driver copying into the guest. FATE AI reports availability but does not configure it "
                "automatically. Prefer running inference on the host.")

    def __init__(self, storage_dir: str | None = None):
        self.storage_dir = storage_dir

    def _ps(self, script: str, timeout: float = 120) -> str:
        r = powershell("$ErrorActionPreference='Stop'; Import-Module Hyper-V; " + script, timeout=timeout)
        if not r.ok:
            msg = (r.stderr or r.stdout).strip().splitlines()
            raise VirtualizationError("Hyper-V: " + (msg[0] if msg else f"exit code {r.code}"))
        return r.stdout

    def status(self) -> BackendStatus:
        if sys.platform != "win32":
            return BackendStatus(False, "Hyper-V is only available on Windows.")
        r = powershell("if (Get-Command Get-VM -ErrorAction SilentlyContinue) { try { Get-VMHost | Out-Null; 'ok' }"
                       " catch { 'noperm' } } else { 'missing' }", timeout=30)
        out = r.stdout.strip()
        if out == "ok":
            return BackendStatus(True, "Hyper-V is enabled and accessible.")
        if out == "noperm":
            return BackendStatus(False, "Hyper-V is installed but your account is not in the "
                                        "'Hyper-V Administrators' group.")
        return BackendStatus(False, "Hyper-V is not enabled. On Windows Pro/Enterprise enable it via "
                                    "'Turn Windows features on or off'. Not available on Windows Home.")

    def list(self) -> list[VMInfo]:
        out = self._ps("Get-VM | Select-Object Name,Id,@{n='State';e={[string]$_.State}},ProcessorCount,"
                       "MemoryAssigned,MemoryStartup,CPUUsage,Uptime,DynamicMemoryEnabled | ConvertTo-Json -Depth 3")
        if not out.strip():
            return []
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        vms = []
        for d in data:
            up = d.get("Uptime") or {}
            vms.append(VMInfo(id=str(d["Name"]), name=d["Name"], backend=self.name,
                              state=_STATE.get(str(d.get("State")), "unknown"), os_type="",
                              cpus=d.get("ProcessorCount"), memory_mb=(d.get("MemoryStartup") or 0) // 2 ** 20,
                              cpu_usage=d.get("CPUUsage"),
                              memory_usage_mb=(d.get("MemoryAssigned") or 0) / 2 ** 20,
                              uptime_s=int(up.get("TotalSeconds", 0)) if isinstance(up, dict) else None,
                              extra={"dynamic_memory": d.get("DynamicMemoryEnabled")}))
        return vms

    def create(self, spec: VMSpec) -> VMInfo:
        n = ps_quote(spec.name)
        path = ps_quote(self.storage_dir) if self.storage_dir else "(Get-VMHost).VirtualHardDiskPath"
        script = (
            f"$vhd = Join-Path {path} ({n} + '.vhdx'); "
            f"New-VM -Name {n} -Generation 2 -MemoryStartupBytes {spec.memory_mb}MB -NewVHDPath $vhd "
            f"-NewVHDSizeBytes {spec.disk_gb}GB | Out-Null; "
            f"Set-VMProcessor -VMName {n} -Count {spec.cpus}; "
            f"Set-VMMemory -VMName {n} -DynamicMemoryEnabled ${str(spec.dynamic_memory).lower()}; "
            f"Set-VMFirmware -VMName {n} -EnableSecureBoot Off; "
        )
        if spec.iso_path:
            script += (f"Add-VMDvdDrive -VMName {n} -Path {ps_quote(spec.iso_path)}; "
                       f"Set-VMFirmware -VMName {n} -FirstBootDevice (Get-VMDvdDrive -VMName {n}); ")
        if spec.network == "none":
            script += f"Get-VMNetworkAdapter -VMName {n} | Disconnect-VMNetworkAdapter; "
        else:
            script += (f"$sw = Get-VMSwitch -Name 'Default Switch' -ErrorAction SilentlyContinue; "
                       f"if ($sw) {{ Connect-VMNetworkAdapter -VMName {n} -SwitchName 'Default Switch' }}; ")
        self._ps(script, timeout=300)
        if spec.start_after_create:
            self.start(spec.name)
        return next(v for v in self.list() if v.name == spec.name)

    def start(self, vm_id: str) -> None:
        self._ps(f"Start-VM -Name {ps_quote(vm_id)}")

    def stop(self, vm_id: str, force: bool = False) -> None:
        self._ps(f"Stop-VM -Name {ps_quote(vm_id)} " + ("-TurnOff -Force" if force else "-Force"), timeout=300)

    def restart(self, vm_id: str) -> None:
        self._ps(f"Restart-VM -Name {ps_quote(vm_id)} -Force", timeout=300)

    def pause(self, vm_id: str) -> None:
        self._ps(f"Suspend-VM -Name {ps_quote(vm_id)}")

    def resume(self, vm_id: str) -> None:
        self._ps(f"Resume-VM -Name {ps_quote(vm_id)}")

    def delete(self, vm_id: str) -> None:
        n = ps_quote(vm_id)
        self._ps(f"$d = (Get-VMHardDiskDrive -VMName {n}).Path; Remove-VM -Name {n} -Force; "
                 f"foreach ($p in $d) {{ if ($p -and (Test-Path $p)) {{ Remove-Item $p -Force }} }}", timeout=300)

    def clone(self, vm_id: str, new_name: str) -> VMInfo:
        src, dst = ps_quote(vm_id), ps_quote(new_name)
        path = ps_quote(self.storage_dir) if self.storage_dir else "(Get-VMHost).VirtualMachinePath"
        self._ps(f"$tmp = Join-Path $env:TEMP ('fate-export-' + [guid]::NewGuid()); Export-VM -Name {src} -Path $tmp; "
                 f"$cfg = Get-ChildItem -Recurse -Path $tmp -Include *.vmcx | Select-Object -First 1; "
                 f"$vm = Import-VM -Path $cfg.FullName -Copy -GenerateNewId -VirtualMachinePath {path} "
                 f"-VhdDestinationPath (Join-Path {path} {dst}); Rename-VM -VM $vm -NewName {dst}; "
                 f"Remove-Item $tmp -Recurse -Force", timeout=3600)
        return next(v for v in self.list() if v.name == new_name)

    def snapshots(self, vm_id: str) -> list[Snapshot]:
        out = self._ps(f"Get-VMSnapshot -VMName {ps_quote(vm_id)} | Select-Object Name,"
                       f"@{{n='Created';e={{$_.CreationTime.ToString('s')}}}} | ConvertTo-Json")
        if not out.strip():
            return []
        data = json.loads(out)
        data = [data] if isinstance(data, dict) else data
        return [Snapshot(d["Name"], d["Name"], d.get("Created", "")) for d in data]

    def create_snapshot(self, vm_id: str, name: str) -> None:
        self._ps(f"Checkpoint-VM -Name {ps_quote(vm_id)} -SnapshotName {ps_quote(name)}", timeout=600)

    def restore_snapshot(self, vm_id: str, snapshot: str) -> None:
        self._ps(f"Restore-VMSnapshot -VMName {ps_quote(vm_id)} -Name {ps_quote(snapshot)} -Confirm:$false",
                 timeout=600)

    def delete_snapshot(self, vm_id: str, snapshot: str) -> None:
        self._ps(f"Remove-VMSnapshot -VMName {ps_quote(vm_id)} -Name {ps_quote(snapshot)}", timeout=600)

    def set_resources(self, vm_id: str, cpus: int | None = None, memory_mb: int | None = None) -> None:
        n = ps_quote(vm_id)
        script = ""
        if cpus:
            script += f"Set-VMProcessor -VMName {n} -Count {int(cpus)}; "
        if memory_mb:
            script += f"Set-VMMemory -VMName {n} -StartupBytes {int(memory_mb)}MB; "
        if script:
            self._ps(script)

    def set_cpu_limit(self, vm_id: str, percent: int) -> None:
        """Hyper-V enforces a per-VM CPU cap (Maximum, 0-100 %)."""
        self._ps(f"Set-VMProcessor -VMName {ps_quote(vm_id)} -Maximum {max(1, min(100, int(percent)))}")

    def gpu_partition_available(self) -> bool:
        try:
            return bool(self._ps("(Get-VMHostPartitionableGpu -ErrorAction SilentlyContinue | Measure-Object).Count")
                        .strip() not in ("", "0"))
        except VirtualizationError:
            return False

    def open_console(self, vm_id: str) -> None:
        exe = which("vmconnect")
        if not exe:
            raise BackendUnavailableError("vmconnect.exe not found (Hyper-V management tools).")
        subprocess.Popen([exe, "localhost", vm_id])
