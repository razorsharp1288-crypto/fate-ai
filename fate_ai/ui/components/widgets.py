"""Reusable FATE AI widgets: cards, stat tiles, badges, charts, page scaffolding."""
from __future__ import annotations

import html
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from ..theme import C


class Card(QFrame):
    def __init__(self, title: str | None = None, accent: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("CardAccent" if accent else "Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setObjectName("H2")
            self.lay.addWidget(t)

    def add(self, w):
        if isinstance(w, QWidget):
            self.lay.addWidget(w)
        else:
            self.lay.addLayout(w)
        return w


class StatTile(Card):
    def __init__(self, label: str, value: str = "—", hint: str = "", parent=None):
        super().__init__(parent=parent)
        self.label = QLabel(label.upper())
        self.label.setObjectName("StatLabel")
        self.value = QLabel(value)
        self.value.setObjectName("StatValue")
        self.hint = QLabel(hint)
        self.hint.setObjectName("Dim")
        self.hint.setWordWrap(True)
        for w in (self.label, self.value, self.hint):
            self.lay.addWidget(w)

    def set(self, value: str, hint: str | None = None):
        self.value.setText(value)
        if hint is not None:
            self.hint.setText(hint)


class Badge(QLabel):
    COLORS = {"ok": C["ok"], "warn": C["warn"], "err": C["err"], "info": C["info"], "accent": C["accent_hi"],
              "muted": C["muted"]}

    def __init__(self, text: str = "", kind: str = "muted", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Badge")
        self.set(text, kind)

    def set(self, text: str, kind: str = "muted"):
        col = QColor(self.COLORS.get(kind, C["muted"]))
        self.setText(text)
        self.setVisible(bool(text))
        self.setStyleSheet(f"color: {col.name()}; background: rgba({col.red()},{col.green()},{col.blue()},0.14);"
                           f" border: 1px solid rgba({col.red()},{col.green()},{col.blue()},0.40);")


class Banner(QFrame):
    def __init__(self, text: str, warn: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("WarnBanner" if warn else "Banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        self.label.setOpenExternalLinks(True)
        lay.addWidget(self.label)

    def setText(self, t: str):
        self.label.setText(t)


class Page(QWidget):
    """Scrollable page scaffold with title + subtitle header."""

    def __init__(self, title: str, subtitle: str = "", scroll: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 22, 28, 8)
        tbox = QVBoxLayout()
        t = QLabel(title)
        t.setObjectName("PageTitle")
        tbox.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("PageSubtitle")
            s.setWordWrap(True)
            tbox.addWidget(s)
        hl.addLayout(tbox, 1)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(8)
        hl.addLayout(self.header_actions)
        outer.addWidget(header)
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(28, 8, 28, 24)
        self.body.setSpacing(14)
        if scroll:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setWidget(self.content)
            outer.addWidget(sa, 1)
        else:
            outer.addWidget(self.content, 1)

    def on_show(self) -> None:
        """Called by the main window whenever the page becomes visible."""


class LineChart(QWidget):
    """Lightweight real-time line chart (0..max) with gradient fill."""

    def __init__(self, title: str, unit: str = "%", maximum: float | None = 100.0, color: str = C["accent"],
                 points: int = 120, parent=None):
        super().__init__(parent)
        self.title, self.unit, self.maximum, self.color = title, unit, maximum, QColor(color)
        self.data: deque[float | None] = deque(maxlen=points)
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.subtitle = ""

    def push(self, v: float | None, subtitle: str = ""):
        self.data.append(v)
        self.subtitle = subtitle
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(C["border"]), 1))
        p.setBrush(QColor(C["card"]))
        p.drawRoundedRect(r, 12, 12)
        p.setPen(QColor(C["muted"]))
        f = p.font()
        f.setPointSizeF(9)
        p.setFont(f)
        p.drawText(r.adjusted(14, 10, -14, 0), Qt.AlignLeft | Qt.AlignTop, self.title.upper())
        last = next((v for v in reversed(self.data) if v is not None), None)
        f.setPointSizeF(14)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C["text"]))
        txt = "n/a" if last is None else f"{last:.1f}{self.unit}"
        p.drawText(r.adjusted(14, 8, -14, 0), Qt.AlignRight | Qt.AlignTop, txt)
        if self.subtitle:
            f.setPointSizeF(8.5)
            f.setBold(False)
            p.setFont(f)
            p.setPen(QColor(C["dim"]))
            p.drawText(r.adjusted(14, 30, -14, 0), Qt.AlignRight | Qt.AlignTop, self.subtitle)
        plot = r.adjusted(14, 48, -14, -12)
        p.setPen(QPen(QColor(C["border"]), 1, Qt.DotLine))
        for i in range(1, 4):
            y = plot.top() + plot.height() * i / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        vals = list(self.data)
        if not any(v is not None for v in vals):
            p.setPen(QColor(C["dim"]))
            p.drawText(plot, Qt.AlignCenter, "Not available on this system" if vals else "Collecting…")
            return
        mx = self.maximum or max((v for v in vals if v is not None), default=1) * 1.2 or 1
        n = self.data.maxlen
        step = plot.width() / max(1, n - 1)
        offset = n - len(vals)
        path = QPainterPath()
        started = False
        first_x = None
        last_x = plot.left()
        for i, v in enumerate(vals):
            if v is None:
                continue
            x = plot.left() + (i + offset) * step
            y = plot.bottom() - min(1.0, max(0.0, v / mx)) * plot.height()
            if not started:
                path.moveTo(x, y)
                first_x = x
                started = True
            else:
                path.lineTo(x, y)
            last_x = x
        fill = QPainterPath(path)
        fill.lineTo(last_x, plot.bottom())
        fill.lineTo(first_x, plot.bottom())
        fill.closeSubpath()
        g = QLinearGradient(0, plot.top(), 0, plot.bottom())
        c1 = QColor(self.color)
        c1.setAlpha(110)
        c2 = QColor(self.color)
        c2.setAlpha(0)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.fillPath(fill, QBrush(g))
        p.setPen(QPen(self.color, 2))
        p.drawPath(path)


class BarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[tuple[str, float]] = []
        self.setMinimumHeight(180)

    def set_items(self, items):
        self.items = items
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(8, 8, -8, -24)
        if not self.items:
            p.setPen(QColor(C["dim"]))
            p.drawText(self.rect(), Qt.AlignCenter, "No data yet")
            return
        mx = max(v for _, v in self.items) or 1
        w = r.width() / len(self.items)
        f = p.font()
        f.setPointSizeF(8)
        p.setFont(f)
        for i, (label, v) in enumerate(self.items):
            h = r.height() * v / mx
            bar = QRectF(r.left() + i * w + w * 0.15, r.bottom() - h, w * 0.7, h)
            g = QLinearGradient(bar.topLeft(), bar.bottomLeft())
            g.setColorAt(0, QColor(C["accent_hi"]))
            g.setColorAt(1, QColor(C["accent_lo"]))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(bar, 4, 4)
            p.setPen(QColor(C["dim"]))
            p.drawText(QRectF(r.left() + i * w, r.bottom() + 4, w, 18), Qt.AlignCenter, label)


def h(text) -> str:
    return html.escape(str(text))


def confirm(parent, title: str, text: str, danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes


def error(parent, text: str, title: str = "Something went wrong") -> None:
    QMessageBox.critical(parent, title, str(text))


def info(parent, text: str, title: str = "FATE AI") -> None:
    QMessageBox.information(parent, title, str(text))


def hbox(*widgets, spacing: int = 8, stretch_last: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    if stretch_last:
        lay.addStretch(1)
    return lay


def fmt_bytes(n: float | None) -> str:
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"
