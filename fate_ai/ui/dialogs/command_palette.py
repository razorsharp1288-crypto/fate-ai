"""Ctrl+K command palette: fuzzy jump to any page, chat or action."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout


def _score(query: str, text: str) -> int:
    q, t = query.lower(), text.lower()
    if not q:
        return 1
    if q in t:
        return 100 - t.index(q)
    i = 0
    for ch in t:
        if i < len(q) and ch == q[i]:
            i += 1
    return 10 if i == len(q) else 0


class CommandPalette(QDialog):
    def __init__(self, commands, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Dialog)
        self.commands = commands
        self.setMinimumWidth(560)
        self.setStyleSheet("QDialog{border:1px solid #3D3360;border-radius:12px;background:#12101B;}")
        lay = QVBoxLayout(self)
        self.input = QLineEdit(placeholderText="Type a command, page or chat…")
        self.input.setStyleSheet("font-size:15px;padding:10px;")
        self.input.textChanged.connect(self.filter)
        self.input.returnPressed.connect(self.run)
        self.list = QListWidget()
        self.list.setMinimumHeight(320)
        self.list.itemActivated.connect(lambda _: self.run())
        lay.addWidget(self.input)
        lay.addWidget(self.list)
        self.filter("")
        if parent is not None:
            g = parent.geometry()
            self.move(g.center().x() - 280, g.top() + 120)

    def filter(self, text):
        self.list.clear()
        ranked = sorted(((s, name, fn) for name, fn in self.commands if (s := _score(text, name)) > 0),
                        key=lambda t: -t[0])
        for _, name, fn in ranked[:40]:
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, fn)
            self.list.addItem(it)
        self.list.setCurrentRow(0)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Down, Qt.Key_Up):
            r = self.list.currentRow() + (1 if e.key() == Qt.Key_Down else -1)
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, r)))
            return
        super().keyPressEvent(e)

    def run(self):
        it = self.list.currentItem()
        if it:
            fn = it.data(Qt.UserRole)
            self.accept()
            fn()
