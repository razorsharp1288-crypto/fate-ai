"""FATE AI entry point."""
from __future__ import annotations

import argparse
import logging
import os
import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point with crash reporting: errors are shown and logged, never silent."""
    from .utilities.crash import install, report
    from .utilities.paths import default_data_dir
    data_dir = _data_dir_from_args(argv) or default_data_dir()
    crash_log = install(data_dir / "logs")
    try:
        return _main(argv)
    except SystemExit:
        raise
    except BaseException:
        import traceback
        report(crash_log, traceback.format_exc())
        return 1


def _data_dir_from_args(argv):
    from pathlib import Path
    args = list(sys.argv[1:] if argv is None else argv)
    if "--data-dir" in args and args.index("--data-dir") + 1 < len(args):
        return Path(args[args.index("--data-dir") + 1])
    return None


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="FateAI")
    parser.add_argument("--minimized", action="store_true", help="start hidden in the system tray")
    parser.add_argument("--data-dir", help="override the data folder")
    parser.add_argument("--reset-onboarding", action="store_true")
    parser.add_argument("--smoke-test", action="store_true", help="start, build every page, then exit (CI)")
    args = parser.parse_args(argv)
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication

    from .bootstrap import build_context
    from .config import default_data_dir
    from .ui.components.icons import app_icon
    from .ui.themes import stylesheet
    from .utilities.logging import setup_logging

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("FATE AI")
    app.setOrganizationName("FateAI")
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())
    from PySide6.QtGui import QColor, QPalette
    pal = app.palette()
    pal.setColor(QPalette.Link, QColor("#A78BFA"))
    pal.setColor(QPalette.LinkVisited, QColor("#C4B5FD"))
    app.setPalette(pal)
    app.setQuitOnLastWindowClosed(False)

    from pathlib import Path
    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    setup_logging(data_dir / "logs")
    log = logging.getLogger("fate")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FateAI.Desktop")
        except Exception:
            pass
    ctx = build_context(data_dir)
    logging.getLogger().setLevel(ctx.settings.settings.advanced.log_level)
    log.info("FATE AI starting; data folder %s", ctx.paths.root)
    if args.reset_onboarding:
        ctx.settings.update(onboarding_complete=False)

    from .ui.main_window import NAV, MainWindow
    win = MainWindow(ctx)

    if args.smoke_test:
        for key, _, _ in NAV:
            win.navigate(key)
            app.processEvents()
        from .ui.dialogs.onboarding import OnboardingDialog
        OnboardingDialog(ctx, win)
        print("SMOKE OK: built", len(NAV), "pages")
        QTimer.singleShot(1500, app.quit)
        app.exec()
        ctx.shutdown()
        return 0

    if not ctx.settings.settings.onboarding_complete:
        from .ui.dialogs.onboarding import OnboardingDialog
        OnboardingDialog(ctx, win).exec()
    if not (args.minimized or ctx.settings.settings.general.start_minimized):
        win.show()
    code = app.exec()
    ctx.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
