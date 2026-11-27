"""One-click installation / enabling of virtualization technologies on Windows.

Nothing runs silently: Windows features are enabled through an elevated
PowerShell window (the user sees and approves the UAC prompt), and apps are
installed with winget in a visible console. Most features need a restart.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from ..core.exceptions import VirtualizationError
from ..utilities.proc import which


@dataclass(frozen=True)
class SetupAction:
    id: str
    backend: str          # VMManager backend name this enables
    name: str
    description: str
    script: str           # PowerShell script run in a visible window
    elevated: bool
    restart: bool
    pro_only: bool = False
    needs_winget: bool = False


ACTIONS: list[SetupAction] = [
    SetupAction("winsandbox", "winsandbox", "Windows Sandbox",
                "Built-in disposable Windows VM. Best quick option on Windows Pro.",
                "Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All -NoRestart",
                elevated=True, restart=True, pro_only=True),
    SetupAction("wsl", "wsl", "WSL2 + Ubuntu", "Linux development environments; works on every Windows edition.",
                "wsl --install", elevated=True, restart=True),
    SetupAction("docker", "docker", "Docker Desktop",
                "Containers — also unlocks Level 2 sandboxes. Uses WSL2 underneath.",
                "winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements",
                elevated=False, restart=True, needs_winget=True),
    SetupAction("virtualbox", "virtualbox", "VirtualBox", "Full virtual machines from ISO images; any edition.",
                "winget install -e --id Oracle.VirtualBox --accept-package-agreements --accept-source-agreements",
                elevated=False, restart=False, needs_winget=True),
    SetupAction("hyperv", "hyperv", "Hyper-V", "Microsoft's full hypervisor (Windows Pro/Enterprise/Education).",
                "Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart; "
                "Add-LocalGroupMember -Group 'Hyper-V Administrators' -Member $env:USERNAME -ErrorAction "
                "SilentlyContinue", elevated=True, restart=True, pro_only=True),
]
BY_ID = {a.id: a for a in ACTIONS}


def windows_edition() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            return str(winreg.QueryValueEx(k, "EditionID")[0])
    except OSError:
        return None


def is_home_edition(edition: str | None = None) -> bool:
    edition = edition if edition is not None else windows_edition()
    return bool(edition) and edition.lower().startswith("core")  # "Core" == Home


def availability(action: SetupAction, edition: str | None = None) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Windows only"
    if action.pro_only and is_home_edition(edition):
        return False, "Needs Windows Pro/Enterprise/Education (you have Home)"
    if action.needs_winget and not which("winget"):
        return False, "Needs winget (App Installer from the Microsoft Store)"
    return True, ""


def command_line(action: SetupAction) -> tuple[str, str]:
    """(executable, parameters) for a visible PowerShell window that runs the action and waits for a key press."""
    tail = ("; Write-Host ''; Write-Host 'Done. " + ("Restart Windows to finish. " if action.restart else "") +
            "You can close this window and click Re-detect in FATE AI.'; Read-Host 'Press Enter to close'")
    return "powershell.exe", f'-NoProfile -ExecutionPolicy Bypass -Command "{action.script}{tail}"'


def run(action_id: str) -> None:
    action = BY_ID[action_id]
    ok, why = availability(action)
    if not ok:
        raise VirtualizationError(f"{action.name}: {why}")
    exe, params = command_line(action)
    if action.elevated:
        import ctypes
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        if rc <= 32:
            raise VirtualizationError("Administrator permission was declined, so nothing was changed.")
    else:
        subprocess.Popen(f'start "FATE AI setup" {exe} {params}', shell=True)  # visible console (user-initiated)
