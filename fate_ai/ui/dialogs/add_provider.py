"""Dialogs for connecting any AI service: catalog presets, key setup and custom endpoints."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ...ai.providers.catalog import PRESETS, ProviderPreset
from ..components.widgets import Badge, Banner, error, hbox
from ..components.worker import run_async


class PresetTile(QFrame):
    clicked = Signal(object)

    def __init__(self, preset: ProviderPreset, added: bool, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        t = QLabel(f"<b>{preset.name}</b>")
        top.addWidget(t)
        top.addStretch(1)
        kind = {"Cloud": "info", "Aggregator": "accent", "Local": "ok"}[preset.category]
        top.addWidget(Badge("Added ✓" if added else preset.category, "ok" if added else kind))
        lay.addLayout(top)
        d = QLabel(preset.description)
        d.setObjectName("Muted")
        d.setWordWrap(True)
        lay.addWidget(d)
        lay.addStretch(1)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.preset)
        super().mouseReleaseEvent(e)


class CatalogGrid(QWidget):
    """Searchable grid of every supported AI service."""
    picked = Signal(object)

    def __init__(self, ctx, parent=None, columns: int = 3):
        super().__init__(parent)
        self.ctx = ctx
        self.columns = columns
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit(placeholderText="Search 35 AI services… (Gemini, Grok, Mistral, Groq, OpenRouter…)")
        self.search.textChanged.connect(self.rebuild)
        self.cat = QComboBox()
        for c in ("All", "Cloud", "Aggregator", "Local"):
            self.cat.addItem(c)
        self.cat.currentIndexChanged.connect(self.rebuild)
        lay.addLayout(hbox(self.search, self.cat))
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(10)
        self.grid.setContentsMargins(0, 4, 0, 0)
        lay.addWidget(self.grid_host)
        self.rebuild()

    def rebuild(self, *_):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        q = self.search.text().strip().lower()
        cat = self.cat.currentText()
        added = {p["id"] for p in self.ctx.providers.configs()}
        i = 0
        for p in PRESETS:
            if cat != "All" and p.category != cat:
                continue
            if q and q not in (p.name + " " + p.description + " " + p.id).lower():
                continue
            tile = PresetTile(p, p.id in added and (not p.requires_key or self.ctx.credentials.has_api_key(p.id)))
            tile.clicked.connect(self.picked.emit)
            self.grid.addWidget(tile, i // self.columns, i % self.columns)
            i += 1
        for c in range(self.columns):
            self.grid.setColumnStretch(c, 1)


class PresetSetupDialog(QDialog):
    """Enter the key (and URL if needed) for one catalog provider, then test it."""

    def __init__(self, ctx, preset: ProviderPreset, prefill_key: str = "", parent=None):
        super().__init__(parent)
        self.ctx, self.preset = ctx, preset
        self.setWindowTitle(f"Connect {preset.name}")
        self.setMinimumWidth(560)
        f = QFormLayout(self)
        intro = QLabel(preset.description + (f'<br><a href="{preset.key_url}">Get an API key from {preset.name} →</a>'
                                             if preset.key_url else ""))
        intro.setOpenExternalLinks(True)
        intro.setWordWrap(True)
        f.addRow(intro)
        existing = ctx.provider_repo.get(preset.id)
        self.url = QLineEdit(existing["base_url"] if existing else preset.base_url)
        f.addRow("Endpoint", self.url)
        self.key = QLineEdit(prefill_key)
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Paste your API key" if preset.requires_key else "Optional — usually not needed")
        if ctx.credentials.has_api_key(preset.id):
            self.key.setPlaceholderText(f"Saved: {ctx.credentials.mask(ctx.credentials.get_api_key(preset.id))} — "
                                        f"paste to replace")
        f.addRow("API key", self.key)
        self.result = Banner("Your key is stored in Windows Credential Manager and only sent to "
                             f"{preset.name}. Usage is billed by {preset.name} to your account."
                             if preset.category != "Local" else "Runs on this PC — no key or account needed.")
        f.addRow(self.result)
        bb = QDialogButtonBox()
        self.test_btn = bb.addButton("Save && test", QDialogButtonBox.ActionRole)
        self.test_btn.setObjectName("Primary")
        bb.addButton("Done", QDialogButtonBox.AcceptRole)
        bb.addButton(QDialogButtonBox.Cancel)
        self.test_btn.clicked.connect(self.save_and_test)
        bb.accepted.connect(self._done)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _save(self) -> bool:
        url = self.url.text().strip()
        if self.preset.needs_url and "YOUR-RESOURCE" in url:
            error(self, "Enter your own endpoint URL first.")
            return False
        try:
            self.ctx.providers.add_preset(self.preset.id, url if url != self.preset.base_url else None)
            if self.key.text().strip():
                self.ctx.credentials.set_api_key(self.preset.id, self.key.text())
                self.key.clear()
        except Exception as e:
            error(self, str(e))
            return False
        return True

    def save_and_test(self):
        if not self._save():
            return
        self.result.setText("Testing connection…")
        self.test_btn.setEnabled(False)

        def done(r):
            self.test_btn.setEnabled(True)
            self.result.setText(("✓ " if r.ok else "✗ ") + r.message)
        run_async(lambda: self.ctx.providers.get(self.preset.id).test_connection(), on_done=done,
                  on_error=lambda e: (self.test_btn.setEnabled(True), self.result.setText(f"✗ {e}")))

    def _done(self):
        if self._save():
            self.accept()


class CustomEndpointDialog(QDialog):
    """Any OpenAI-compatible endpoint, with any auth header."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.pid = None
        self.setWindowTitle("Add custom endpoint")
        self.setMinimumWidth(560)
        f = QFormLayout(self)
        f.addRow(QLabel("Works with any service that speaks the OpenAI chat-completions API."))
        self.name = QLineEdit(placeholderText="e.g. My company gateway")
        self.url = QLineEdit(placeholderText="https://api.example.com/v1")
        self.header = QLineEdit("Authorization")
        self.scheme = QLineEdit("Bearer")
        self.scheme.setPlaceholderText("Prefix before the key (empty for none)")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("API key (leave empty if not required)")
        self.needs_key = QCheckBox("This endpoint requires a key")
        self.needs_key.setChecked(True)
        for label, w in (("Name", self.name), ("Base URL", self.url), ("Auth header", self.header),
                         ("Auth prefix", self.scheme), ("API key", self.key)):
            f.addRow(label, w)
        f.addRow("", self.needs_key)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _save(self):
        try:
            p = self.ctx.providers.add_custom(self.name.text().strip() or "Custom", self.url.text().strip(),
                                              requires_key=self.needs_key.isChecked(),
                                              auth_header=self.header.text().strip() or "Authorization",
                                              auth_scheme=self.scheme.text().strip())
            if self.key.text().strip():
                self.ctx.credentials.set_api_key(p["id"], self.key.text())
        except Exception as e:
            error(self, str(e))
            return
        self.pid = p["id"]
        self.accept()


class CatalogDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Add an AI provider")
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        grid = CatalogGrid(ctx)
        grid.picked.connect(self._pick)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(grid)
        lay.addWidget(sa, 1)
        custom = QPushButton("+ Custom endpoint (any URL)")
        custom.clicked.connect(lambda: CustomEndpointDialog(ctx, self).exec() and self.accept())
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addLayout(hbox(custom, None, close))

    def _pick(self, preset):
        if PresetSetupDialog(self.ctx, preset, parent=self).exec():
            self.accept()
