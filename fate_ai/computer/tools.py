"""Actions the PC Control agent can take, with permission categories.

Kinds decide approval:
* observe — look only (screenshot, read, list). Never needs approval once the capability is on.
* safe    — opens things (apps, websites, focus a window). Auto-approved in "auto_safe" and "auto_all".
* risky   — changes things (write files, run commands, mouse & keyboard). Auto-approved only in "auto_all".
"""
from __future__ import annotations

import difflib
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import psutil

from ..core.exceptions import FateError
from . import winput


@dataclass
class ToolResult:
    text: str
    image_b64: str | None = None


@dataclass
class Tool:
    name: str
    capability: str        # settings.computer.<capability>
    kind: str              # observe | safe | risky
    params: str
    description: str
    fn: Callable[..., ToolResult] = field(repr=False, default=None)


def _path(p: str) -> Path:
    if not p:
        raise FateError("No path given")
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()


class Toolbox:
    def __init__(self, settings, backup_dir: Path, screenshot: Callable[[int], tuple[str, int, int]] | None = None):
        """``screenshot(max_width)`` returns (base64 PNG/JPEG, image_width, real_screen_width)."""
        self.settings = settings
        self.backup_dir = Path(backup_dir)
        self._shot = screenshot
        self.scale = 1.0  # screenshot px -> screen px
        T = Tool
        self.tools: dict[str, Tool] = {t.name: t for t in [
            T("screenshot", "see_screen", "observe", "{}", "Capture the screen to see what is on it.", self.screenshot),
            T("list_windows", "open_apps", "observe", "{}", "List titles of open windows.", self.list_windows),
            T("focus_window", "open_apps", "safe", '{"title": str}', "Bring a window to the front.", self.focus_window),
            T("open_app", "open_apps", "safe", '{"name": str}',
              "Open an app by name (e.g. 'notepad', 'chrome', 'spotify') or a file/folder path.", self.open_app),
            T("open_url", "open_apps", "safe", '{"url": str}', "Open a web page in the default browser.", self.open_url),
            T("list_dir", "read_files", "observe", '{"path": str}', "List a folder.", self.list_dir),
            T("read_file", "read_files", "observe", '{"path": str}', "Read a text file (max 200 KB).", self.read_file),
            T("write_file", "write_files", "risky", '{"path": str, "content": str}',
              "Create or overwrite a text file (the old version is backed up).", self.write_file),
            T("run_command", "run_commands", "risky", '{"command": str}',
              "Run a PowerShell command (or sh on Linux/macOS) and get its output.", self.run_command),
            T("click", "mouse_keyboard", "risky", '{"x": int, "y": int, "button": "left|right|middle", "double": bool}',
              "Click at screenshot coordinates.", self.click),
            T("type_text", "mouse_keyboard", "risky", '{"text": str}', "Type text at the cursor.", self.type_text),
            T("press_keys", "mouse_keyboard", "risky", '{"keys": str}',
              "Press a key or shortcut, e.g. 'enter', 'ctrl+s', 'alt+tab', 'win+r'.", self.press_keys),
            T("scroll", "mouse_keyboard", "risky", '{"amount": int}', "Scroll (positive = up).", self.scroll),
            T("system_info", "see_screen", "observe", "{}", "CPU, RAM, disks and OS.", self.system_info),
            T("wait", "see_screen", "observe", '{"seconds": number}', "Wait up to 10 s for something to load.",
              self.wait),
        ]}

    def enabled_tools(self) -> list[Tool]:
        c = self.settings.computer
        return [t for t in self.tools.values() if getattr(c, t.capability, False)]

    def describe(self) -> str:
        return "\n".join(f"- {t.name} {t.params}: {t.description}" for t in self.enabled_tools())

    # -- observe ------------------------------------------------------------
    def screenshot(self) -> ToolResult:
        if self._shot is None:
            raise FateError("Screen capture is not available.")
        b64, img_w, real_w = self._shot(self.settings.computer.screenshot_max_width)
        self.scale = real_w / max(1, img_w)
        return ToolResult(f"Screenshot taken ({img_w}px wide). Use these pixel coordinates for clicks.", b64)

    def list_windows(self) -> ToolResult:
        return ToolResult("\n".join(t for _, t in winput.windows()[:60]) or "(no windows)")

    def list_dir(self, path: str = "~") -> ToolResult:
        p = _path(path)
        if not p.is_dir():
            raise FateError(f"Not a folder: {p}")
        items = []
        for c in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))[:300]:
            try:
                items.append(f"{'[dir] ' if c.is_dir() else ''}{c.name}" +
                             ("" if c.is_dir() else f"  ({c.stat().st_size:,} B)"))
            except OSError:
                continue
        return ToolResult(f"{p}\n" + "\n".join(items))

    def read_file(self, path: str) -> ToolResult:
        p = _path(path)
        if not p.is_file():
            raise FateError(f"File not found: {p}")
        if p.stat().st_size > 200_000:
            raise FateError("File is larger than 200 KB.")
        return ToolResult(p.read_text("utf-8", errors="replace"))

    def system_info(self) -> ToolResult:
        vm = psutil.virtual_memory()
        disks = []
        for d in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(d.mountpoint)
                disks.append(f"{d.mountpoint} {u.free / 2**30:.0f}/{u.total / 2**30:.0f} GB free")
            except OSError:
                pass
        return ToolResult(f"{platform.platform()} | CPU {psutil.cpu_count()} threads, {psutil.cpu_percent(0.2)}% used"
                          f" | RAM {vm.available / 2**30:.1f}/{vm.total / 2**30:.1f} GB free | " + "; ".join(disks))

    def wait(self, seconds: float = 1) -> ToolResult:
        time.sleep(max(0.0, min(10.0, float(seconds))))
        return ToolResult(f"Waited {seconds}s.")

    # -- safe ---------------------------------------------------------------
    def focus_window(self, title: str) -> ToolResult:
        return ToolResult(f"Focused: {winput.focus(title)}")

    @staticmethod
    def _start_menu_apps() -> dict[str, Path]:
        roots = [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
                 Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
                 Path.home() / "Desktop"]
        apps = {}
        for r in roots:
            if r.exists():
                for f in r.rglob("*.lnk"):
                    apps.setdefault(f.stem.lower(), f)
        return apps

    def open_app(self, name: str) -> ToolResult:
        name = str(name).strip()
        if not name:
            raise FateError("No app name given")
        p = Path(os.path.expandvars(os.path.expanduser(name)))
        if p.exists():
            _open(str(p))
            return ToolResult(f"Opened {p}")
        if sys.platform == "win32":
            apps = self._start_menu_apps()
            key = name.lower()
            hit = apps.get(key) or next((v for k, v in apps.items() if key in k), None)
            if hit is None:
                close = difflib.get_close_matches(key, list(apps), n=1, cutoff=0.6)
                hit = apps[close[0]] if close else None
            if hit is not None:
                os.startfile(str(hit))  # noqa: S606 - user-approved app launch
                return ToolResult(f"Opened {hit.stem}")
            exe = shutil.which(name) or shutil.which(name + ".exe")
            if exe:
                os.startfile(exe)  # noqa: S606
                return ToolResult(f"Opened {exe}")
            if name.endswith(":") or name.startswith("ms-"):
                os.startfile(name)  # noqa: S606 - e.g. ms-settings:
                return ToolResult(f"Opened {name}")
            raise FateError(f"Couldn't find an app called '{name}'. Try the exact name from the Start menu.")
        exe = shutil.which(name)
        if not exe:
            raise FateError(f"App not found: {name}")
        import subprocess
        subprocess.Popen([exe], start_new_session=True)
        return ToolResult(f"Opened {exe}")

    def open_url(self, url: str) -> ToolResult:
        url = str(url).strip()
        if not url.startswith(("http://", "https://", "mailto:")):
            url = "https://" + url
        import webbrowser
        webbrowser.open(url)
        return ToolResult(f"Opened {url}")

    # -- risky --------------------------------------------------------------
    def write_file(self, path: str, content: str) -> ToolResult:
        p = _path(path)
        existed = p.exists()
        if existed:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(p, self.backup_dir / f"{stamp}-{p.name}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), "utf-8")
        return ToolResult(f"Wrote {len(str(content)):,} characters to {p}" +
                          (f" (previous version backed up in {self.backup_dir})" if existed else ""))

    def run_command(self, command: str) -> ToolResult:
        from ..utilities.proc import run, which
        if sys.platform == "win32":
            argv = [which("powershell") or "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
        else:
            argv = ["/bin/sh", "-c", command]
        r = run(argv, timeout=120)
        out = (r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr.strip() else ""))[-8000:]
        return ToolResult(f"exit code {r.code}\n{out}".strip())

    def _xy(self, x, y) -> tuple[int, int]:
        return int(float(x) * self.scale), int(float(y) * self.scale)

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> ToolResult:
        rx, ry = self._xy(x, y)
        winput.click(rx, ry, button if button in ("left", "right", "middle") else "left", bool(double))
        return ToolResult(f"{'Double-c' if double else 'C'}licked {button} at ({x}, {y}).")

    def type_text(self, text: str) -> ToolResult:
        winput.type_text(str(text))
        return ToolResult(f"Typed {len(str(text))} characters.")

    def press_keys(self, keys: str) -> ToolResult:
        winput.press(str(keys))
        return ToolResult(f"Pressed {keys}.")

    def scroll(self, amount: int) -> ToolResult:
        winput.scroll(int(amount))
        return ToolResult(f"Scrolled {amount}.")


def _open(target: str) -> None:
    if sys.platform == "win32":
        os.startfile(target)  # noqa: S606
    else:
        import subprocess
        subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", target], start_new_session=True)


def needs_approval(tool: Tool, approval_mode: str) -> bool:
    if tool.kind == "observe":
        return False
    if approval_mode == "auto_all":
        return False
    if approval_mode == "auto_safe":
        return tool.kind == "risky"
    return True


def describe_action(tool: Tool, args: dict) -> str:
    a = {k: (v if len(str(v)) < 300 else str(v)[:300] + "…") for k, v in args.items()}
    return {"open_app": f"Open app: {a.get('name')}", "open_url": f"Open website: {a.get('url')}",
            "focus_window": f"Switch to window: {a.get('title')}",
            "write_file": f"Write file: {a.get('path')}\n\n{a.get('content', '')}",
            "run_command": f"Run command:\n{a.get('command')}",
            "click": f"{'Double-click' if a.get('double') else 'Click'} {a.get('button', 'left')} at "
                     f"({a.get('x')}, {a.get('y')})",
            "type_text": f"Type: {a.get('text')}", "press_keys": f"Press keys: {a.get('keys')}",
            "scroll": f"Scroll {a.get('amount')}"}.get(tool.name, f"{tool.name} {a}")
