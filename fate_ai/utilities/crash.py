"""Crash reporting for the windowed (no-console) build: never fail silently."""
from __future__ import annotations

import faulthandler
import sys
import traceback
from datetime import datetime
from pathlib import Path

from ..security.redaction import redact

_fault_file = None


def install(log_dir: Path) -> Path:
    """Write native crashes (segfaults) and unhandled Python errors to crash.log and show a message box."""
    global _fault_file
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_log = log_dir / "crash.log"
    try:
        _fault_file = open(log_dir / "native-crash.log", "a", encoding="utf-8")
        faulthandler.enable(_fault_file)
    except OSError:
        pass

    def hook(exc_type, exc, tb):
        report(crash_log, "".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = hook
    return crash_log


def report(crash_log: Path, text: str) -> None:
    text = redact(text)
    try:
        with open(crash_log, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} =====\n{text}\n")
    except OSError:
        pass
    message = ("FATE AI hit an unexpected error.\n\n" + text.strip().splitlines()[-1][:500] +
               f"\n\nDetails were saved to:\n{crash_log}")
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None:
            QMessageBox.critical(None, "FATE AI error", message)
            return
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "FATE AI error", 0x10)
        except Exception:
            pass
