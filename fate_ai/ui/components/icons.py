"""Minimal stroke icons (24x24 viewBox) rendered from inline SVG."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    "chat": '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
    "models": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
              '<path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/>',
    "providers": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><circle cx="12" cy="12" r="4"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M15 8l2 2"/>',
    "vm": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "sandbox": '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M12 22V12M21 7l-9 5-9-5"/>',
    "projects": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "prompts": '<path d="M4 4h12l4 4v12H4z"/><path d="M8 10h8M8 14h8M8 18h5"/>',
    "compare": '<path d="M6 20V10M12 20V4M18 20v-7"/>',
    "usage": '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
    "hardware": '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h4v4H6zM14 10h4M14 14h4"/>',
    "dev": '<path d="M8 8l-5 4 5 4M16 8l5 4-5 4M14 4l-4 16"/>',
    "security": '<path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z"/><path d="M9 12l2 2 4-4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1'
                'a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3'
                'l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0'
                ' 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3'
                'a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0'
                '-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "about": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "blueprint": '<path d="M3 3h18v18H3z"/><path d="M3 9h18M9 21V9"/><path d="M13 13h5v5h-5z"/>',
    "cube": '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M12 22V12M21 7l-9 5-9-5"/>',
    "update": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    "speaker": '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12"/>',
    "cursor": '<path d="M4 3l7 17 2.5-7.5L21 10z"/>',
    "send": '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "attach": '<path d="M21 11l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8"/>',
    "power": '<path d="M12 2v10M6.3 6.3a8 8 0 1 0 11.4 0"/>',
}


def icon(name: str, color: str = "#B8B0D6", size: int = 20) -> QIcon:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{PATHS.get(name, PATHS["about"])}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        renderer.render(p, QRectF(0, 0, size * scale, size * scale))
        p.end()
        pm.setDevicePixelRatio(scale)
        ic.addPixmap(pm)
    return ic


def logo_pixmap(size: int = 256) -> QPixmap:
    """Draw the FATE AI mark: a purple gradient hexagon with a stylised F."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPen, QPolygonF
    import math
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    cx = cy = size / 2
    r = size * 0.46
    poly = QPolygonF([QPointF(cx + r * math.cos(math.radians(60 * i - 90)),
                              cy + r * math.sin(math.radians(60 * i - 90))) for i in range(6)])
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#A78BFA"))
    g.setColorAt(0.5, QColor("#7C3AED"))
    g.setColorAt(1, QColor("#2E1065"))
    p.setBrush(QBrush(g))
    p.setPen(QPen(QColor("#C4B5FD"), size * 0.015))
    p.drawPolygon(poly)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0B0614"))
    u = size / 16
    p.drawRoundedRect(QRectF(cx - 3.2 * u, cy - 4.6 * u, 1.9 * u, 9.2 * u), u * 0.4, u * 0.4)
    p.drawRoundedRect(QRectF(cx - 3.2 * u, cy - 4.6 * u, 6.6 * u, 1.9 * u), u * 0.4, u * 0.4)
    p.drawRoundedRect(QRectF(cx - 3.2 * u, cy - 0.9 * u, 4.8 * u, 1.7 * u), u * 0.4, u * 0.4)
    p.setBrush(QColor("#E9D5FF"))
    p.drawEllipse(QPointF(cx + 3.0 * u, cy + 3.6 * u), 0.95 * u, 0.95 * u)
    p.end()
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(s))
    return ic
