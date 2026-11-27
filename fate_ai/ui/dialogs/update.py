"""Update available dialog: release notes, verified download, one-click install."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, \
    QVBoxLayout

from ...updater.updater import Updater, UpdateInfo, install_and_restart
from ..components.markdown_view import render
from ..components.worker import run_async
from ..themes import chat_css


class UpdateDialog(QDialog):
    def __init__(self, ctx, updater: Updater, info: UpdateInfo, parent=None):
        super().__init__(parent)
        self.ctx, self.updater, self.info = ctx, updater, info
        self.setWindowTitle("Update available")
        self.setMinimumSize(560, 460)
        lay = QVBoxLayout(self)
        t = QLabel(f"<b style='font-size:18px'>FATE AI {info.latest} is available</b><br>"
                   f"<span style='color:#9A93B3'>You have {info.current}. Your chats, keys and settings are kept.</span>")
        lay.addWidget(t)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setHtml(f"<style>{chat_css()}</style>{render(info.notes or 'No release notes.')}")
        lay.addWidget(notes, 1)
        self.bar = QProgressBar()
        self.bar.hide()
        self.msg = QLabel("")
        self.msg.setObjectName("Muted")
        self.msg.setWordWrap(True)
        lay.addWidget(self.bar)
        lay.addWidget(self.msg)
        row = QHBoxLayout()
        skip = QPushButton("Skip this version")
        skip.setObjectName("Ghost")
        skip.clicked.connect(self.skip)
        later = QPushButton("Later")
        later.clicked.connect(self.reject)
        self.go = QPushButton("Update now")
        self.go.setObjectName("Primary")
        self.go.clicked.connect(self.update_now)
        row.addWidget(skip)
        row.addStretch(1)
        row.addWidget(later)
        row.addWidget(self.go)
        lay.addLayout(row)
        if not info.installer_url:
            self.go.setEnabled(False)
            self.msg.setText("This release has no Windows installer attached.")

    def skip(self):
        self.ctx.settings.update(advanced={"skipped_version": self.info.latest})
        self.reject()

    def update_now(self):
        self.go.setEnabled(False)
        self.bar.show()
        self.bar.setRange(0, 0)
        self.msg.setText("Downloading and verifying…")

        def work(progress):
            return self.updater.download(self.info, progress=lambda d, t: progress((d, t)))

        def prog(p):
            done, total = p
            if total:
                self.bar.setRange(0, 1000)
                self.bar.setValue(int(done / total * 1000))
                self.msg.setText(f"Downloading… {done / 2**20:.1f} / {total / 2**20:.1f} MB")

        def done(path):
            self.bar.setRange(0, 1)
            self.bar.setValue(1)
            if sys.platform != "win32" or not getattr(sys, "frozen", False):
                self.msg.setText(f"✓ Verified installer downloaded to {path}. Run it to update (automatic install "
                                 f"only works in the installed Windows app).")
                return
            self.msg.setText("✓ Verified. Installing — FATE AI will restart in a moment…")
            try:
                install_and_restart(path)
            except Exception as e:
                self.msg.setText(f"Could not start the installer: {e}")
                self.go.setEnabled(True)
                return
            win = self.parent()
            if win is not None and hasattr(win, "_really_quit"):
                win._really_quit = True
            QApplication.instance().quit()

        def fail(e):
            self.go.setEnabled(True)
            self.bar.hide()
            self.msg.setText(f"Update failed: {e}")
        run_async(work, on_progress=prog, on_done=done, on_error=fail)
