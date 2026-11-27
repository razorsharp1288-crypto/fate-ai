"""Lightweight software-rendered 3D viewport for blueprint models (no OpenGL/WebEngine dependency).

Flat-shaded triangles drawn back-to-front (painter's algorithm) with QPainter.
Left-drag orbits, right/middle-drag pans, wheel zooms, click selects a part,
double-click frames the model.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ...blueprints.geometry import Part, bounds, part_triangles
from ..themes import C

LIGHT = (0.45, 0.8, 0.4)
_ln = math.sqrt(sum(x * x for x in LIGHT))
LIGHT = tuple(x / _ln for x in LIGHT)


class Viewer3D(QWidget):
    partClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 300)
        self.setMouseTracking(True)
        self.parts: list[Part] = []
        self._tris: list[tuple] = []   # (v0, v1, v2, normal, QColor, part_index)
        self.yaw, self.pitch, self.dist = 35.0, 18.0, 4.0
        self.target = [0.0, 0.8, 0.0]
        self.selected = -1
        self.wireframe = False
        self.show_grid = True
        self._drag = None
        self._last = None
        self._moved = False
        self._hit: list[tuple[QPolygonF, int]] = []
        self.spin = QTimer(self, interval=33, timeout=self._spin)

    # -- data -----------------------------------------------------------------
    def set_parts(self, parts: list[Part], frame: bool = True):
        self.parts = list(parts)
        self._tris = []
        for i, p in enumerate(self.parts):
            col = QColor(p.color)
            for t in part_triangles(p):
                (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
                ux, uy, uz = bx - ax, by - ay, bz - az
                vx, vy, vz = cx - ax, cy - ay, cz - az
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                self._tris.append((t[0], t[1], t[2], (nx / ln, ny / ln, nz / ln), col, i))
        if self.selected >= len(self.parts):
            self.selected = -1
        if frame:
            self.frame_all()
        self.update()

    def frame_all(self):
        if not self.parts:
            self.target, self.dist = [0.0, 0.8, 0.0], 4.0
        else:
            (x0, y0, z0), (x1, y1, z1) = bounds(self.parts)
            self.target = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]
            r = max(x1 - x0, y1 - y0, z1 - z0, 0.05)
            self.dist = r * 1.35
        self.update()

    def set_selected(self, i: int):
        self.selected = i
        self.update()

    def set_auto_rotate(self, on: bool):
        self.spin.start() if on else self.spin.stop()

    def _spin(self):
        self.yaw = (self.yaw + 0.8) % 360
        self.update()

    # -- camera ---------------------------------------------------------------
    def _basis(self):
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        fwd = (-math.cos(pitch) * math.sin(yaw), -math.sin(pitch), -math.cos(pitch) * math.cos(yaw))
        eye = (self.target[0] - fwd[0] * self.dist, self.target[1] - fwd[1] * self.dist,
               self.target[2] - fwd[2] * self.dist)
        right = (math.cos(yaw), 0.0, -math.sin(yaw))
        up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
              right[0] * fwd[1] - right[1] * fwd[0])
        return eye, fwd, right, up

    def _projector(self):
        eye, fwd, right, up = self._basis()
        w, h = self.width(), self.height()
        f = min(w, h) * 0.9
        cx, cy = w / 2, h / 2
        ex, ey, ez = eye

        def proj(v):
            dx, dy, dz = v[0] - ex, v[1] - ey, v[2] - ez
            z = dx * fwd[0] + dy * fwd[1] + dz * fwd[2]
            if z < 0.01:
                return None, z
            x = dx * right[0] + dy * right[1] + dz * right[2]
            y = dx * up[0] + dy * up[1] + dz * up[2]
            return QPointF(cx + f * x / z, cy - f * y / z), z
        return proj, eye

    # -- painting -------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor("#120E1F"))
        g.setColorAt(1, QColor("#05040A"))
        p.fillRect(self.rect(), g)
        proj, eye = self._projector()
        if self.show_grid:
            self._grid(p, proj)
        # project & shade
        items = []
        for v0, v1, v2, n, col, idx in self._tris:
            a, za = proj(v0)
            b, zb = proj(v1)
            c, zc = proj(v2)
            if a is None or b is None or c is None:
                continue
            # two-sided lighting so imported/odd winding still looks right
            view = (eye[0] - v0[0], eye[1] - v0[1], eye[2] - v0[2])
            facing = n[0] * view[0] + n[1] * view[1] + n[2] * view[2]
            nn = n if facing >= 0 else (-n[0], -n[1], -n[2])
            d = max(0.0, nn[0] * LIGHT[0] + nn[1] * LIGHT[1] + nn[2] * LIGHT[2])
            shade = 0.38 + 0.62 * d
            items.append(((za + zb + zc) / 3, QPolygonF([a, b, c]), col, shade, idx))
        items.sort(key=lambda t: -t[0])
        self._hit = []
        sel_pen = QPen(QColor(C["accent_hi"]), 1.4)
        for _, poly, col, shade, idx in items:
            if idx == self.selected:
                shade = min(1.0, shade + 0.25)
            fc = QColor(int(col.red() * shade), int(col.green() * shade), int(col.blue() * shade))
            if self.wireframe:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(fc.lighter(160), 0.8))
            else:
                p.setBrush(fc)
                p.setPen(sel_pen if idx == self.selected else QPen(fc, 0.6))
            p.drawPolygon(poly)
            self._hit.append((poly, idx))
        self._overlay(p)

    def _grid(self, p: QPainter, proj):
        if self.parts:
            (x0, _, z0), (x1, _, z1) = bounds(self.parts)
            extent = max(abs(x0), abs(x1), abs(z0), abs(z1), 0.5) * 1.6
        else:
            extent = 2.0
        step = 10 ** math.floor(math.log10(extent / 4)) if extent > 0 else 0.5
        n = int(extent / step) + 1
        for i in range(-n, n + 1):
            for a, b in (((i * step, 0, -n * step), (i * step, 0, n * step)),
                         ((-n * step, 0, i * step), (n * step, 0, i * step))):
                pa, _ = proj(a)
                pb, _ = proj(b)
                if pa is not None and pb is not None:
                    col = QColor(C["accent"]) if i == 0 else QColor(C["border"])
                    col.setAlpha(140 if i == 0 else 90)
                    p.setPen(QPen(col, 1))
                    p.drawLine(pa, pb)

    def _overlay(self, p: QPainter):
        p.setPen(QColor(C["dim"]))
        f = p.font()
        f.setPointSizeF(8.5)
        p.setFont(f)
        txt = "Drag: orbit · Right-drag: pan · Wheel: zoom · Double-click: frame"
        if self.parts:
            (x0, y0, z0), (x1, y1, z1) = bounds(self.parts)
            txt = f"{len(self.parts)} parts · {x1 - x0:.2f} × {y1 - y0:.2f} × {z1 - z0:.2f} m   ·   " + txt
        else:
            p.setPen(QColor(C["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, "No model yet — generate one with AI or Auto 3D")
            p.setPen(QColor(C["dim"]))
        p.drawText(QRectF(10, self.height() - 22, self.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, txt)

    # -- interaction ------------------------------------------------------------
    def mousePressEvent(self, e):
        self._drag = e.button()
        self._last = e.position()
        self._moved = False

    def mouseMoveEvent(self, e):
        if self._drag is None or self._last is None:
            return
        d = e.position() - self._last
        self._last = e.position()
        if abs(d.x()) + abs(d.y()) > 1:
            self._moved = True
        if self._drag == Qt.LeftButton:
            self.yaw = (self.yaw - d.x() * 0.5) % 360
            self.pitch = max(-89.0, min(89.0, self.pitch + d.y() * 0.4))
        else:
            _, _, right, up = self._basis()
            k = self.dist / max(200.0, min(self.width(), self.height()) * 0.9)
            for i in range(3):
                self.target[i] -= right[i] * d.x() * k - up[i] * d.y() * k
        self.update()

    def mouseReleaseEvent(self, e):
        if not self._moved and e.button() == Qt.LeftButton:
            pt = e.position()
            hit = -1
            for poly, idx in reversed(self._hit):
                if poly.containsPoint(pt, Qt.OddEvenFill):
                    hit = idx
                    break
            self.selected = hit
            self.partClicked.emit(hit)
            self.update()
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        self.frame_all()

    def wheelEvent(self, e):
        self.dist = max(0.05, self.dist * (0.88 if e.angleDelta().y() > 0 else 1.14))
        self.update()

    def set_view(self, name: str):
        self.yaw, self.pitch = {"front": (0, 0), "side": (90, 0), "top": (0, 89), "iso": (35, 18),
                                "back": (180, 0)}.get(name, (35, 18))
        self.update()
