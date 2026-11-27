"""Small transient notification shown in the bottom-right of the main window."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel


class Toast(QLabel):
    def __init__(self, parent, text: str, ms: int = 4000):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setMaximumWidth(380)
        self.setStyleSheet("background:#1E1A2C;border:1px solid #8B5CF6;border-radius:10px;padding:10px 14px;"
                           "color:#ECE9F5;")
        self.adjustSize()
        self.move(parent.width() - self.width() - 24, parent.height() - self.height() - 40)
        self.show()
        self.raise_()
        QTimer.singleShot(ms, self.deleteLater)
