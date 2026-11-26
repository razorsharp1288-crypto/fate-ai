"""Per-user data locations and bundled-resource lookup."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .. import APP_ID


def default_data_dir() -> Path:
    """%LOCALAPPDATA%\\FateAI on Windows. Override with FATE_AI_HOME (used by tests)."""
    override = os.environ.get("FATE_AI_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_ID
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "fate-ai"


def resource_path(relative: str) -> Path:
    """Locate bundled assets both from source and from a PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
    return base / relative


def dir_size(path: Path) -> int:
    total = 0
    for p in Path(path).rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            pass
    return total
