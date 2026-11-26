"""Safe path handling: keeps file operations inside approved directories."""
from __future__ import annotations

import os
from pathlib import Path

from ..core.exceptions import PermissionDeniedError, ValidationError

_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(name: str, max_len: int = 64) -> str:
    """Make a user-provided name safe to use as a single file/dir name on Windows."""
    cleaned = "".join(c if c.isalnum() or c in "-_. " else "_" for c in (name or "")).strip(" .")
    if not cleaned:
        raise ValidationError("Name is empty")
    if cleaned.split(".")[0].upper() in _WIN_RESERVED:
        cleaned = "_" + cleaned
    return cleaned[:max_len]


def is_within(path: Path | str, root: Path | str) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(Path(os.path.realpath(root)))
        return True
    except ValueError:
        return False


def resolve_inside(root: Path | str, relative: str) -> Path:
    """Resolve ``relative`` under ``root``; raise if it escapes (``..``, absolute paths, symlinks)."""
    root_p = Path(os.path.realpath(root))
    rel = Path(relative)
    if rel.is_absolute() or rel.drive:
        raise PermissionDeniedError("Absolute paths are not allowed here")
    target = Path(os.path.realpath(root_p / rel))
    if not is_within(target, root_p):
        raise PermissionDeniedError(f"Path escapes the allowed directory: {relative}")
    return target


def check_allowed(path: Path | str, allowed_roots: list[str | Path]) -> Path:
    p = Path(os.path.realpath(path))
    for root in allowed_roots:
        if is_within(p, root):
            return p
    raise PermissionDeniedError(f"Access to {p} is not permitted for this agent/project")
