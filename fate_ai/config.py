"""Filesystem locations used by FATE AI.

All user data lives under a single per-user directory so it can be inspected,
backed up or wiped with "Delete all local data". Override with the
``FATE_AI_HOME`` environment variable (used by the test-suite).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import APP_ID


def default_data_dir() -> Path:
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


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "fate.db"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def sandboxes(self) -> Path:
        return self.root / "sandboxes"

    @property
    def projects(self) -> Path:
        return self.root / "projects"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def vms(self) -> Path:
        return self.root / "vms"

    @property
    def updates(self) -> Path:
        return self.root / "updates"

    @property
    def models(self) -> Path:
        return self.root / "models"

    def ensure(self) -> "AppPaths":
        for p in (self.root, self.logs, self.sandboxes, self.projects, self.exports,
                  self.vms, self.updates, self.models):
            p.mkdir(parents=True, exist_ok=True)
        return self


def resource_path(relative: str) -> Path:
    """Locate bundled assets both from source and from a PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative
