"""Ordered schema migrations. Add ``vNNN_description.py`` with ``VERSION`` and ``SQL``.

Applied in order by ``Database.migrate()``; the current version is stored in
SQLite's ``PRAGMA user_version``. Never edit a released migration — add a new one.
"""
from __future__ import annotations

import importlib
import pkgutil


def load() -> list[str]:
    mods = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("v") and info.name[1:4].isdigit():
            mods.append(importlib.import_module(f"{__name__}.{info.name}"))
    mods.sort(key=lambda m: m.VERSION)
    for i, m in enumerate(mods, start=1):
        if m.VERSION != i:
            raise RuntimeError(f"Migration versions must be contiguous; expected {i}, found {m.VERSION}")
    return [m.SQL for m in mods]
