from __future__ import annotations

import dataclasses
import json
import platform
import sys
from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QFileDialog, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from ... import __version__
from ...ai.providers.base import ChatMessage, ChatRequest
from ...hardware.detection import detect_all
from ...security.redaction import redact
from ..components.widgets import Page, hbox, info
from ..components.worker import run_async
from ..themes import MONO_STACK


def mono(ro=True) -> QPlainTextEdit:
    e = QPlainTextEdit()
    e.setReadOnly(ro)
    e.setStyleSheet(f"font-family:{MONO_STACK};font-size:12px;")
    return e


class DevToolsPage(Page):
    def __init__(self, ctx):
        super().__init__("Developer Tools", "Logs, events, diagnostics and a raw model console.", scroll=False)
        self.ctx = ctx
        tabs = QTabWidget()
        self.body.addWidget(tabs, 1)

        lw = QWidget()
        ll = QVBoxLayout(lw)
        self.logs = mono()
        r = QPushButton("Reload")
        r.clicked.connect(self.load_logs)
        o = QPushButton("Open log folder")
        o.clicked.connect(self.open_logs)
        ll.addLayout(hbox(r, o, None))
        ll.addWidget(self.logs)
        tabs.addTab(lw, "Logs")

        ew = QWidget()
        el = QVBoxLayout(ew)
        self.events = mono()
        el.addWidget(self.events)
        tabs.addTab(ew, "Event bus")
        ctx.bus.subscribe("*", self._event)

        cw = QWidget()
        cl = QVBoxLayout(cw)
        self.c_provider = QComboBox()
        for p in ctx.providers.configs():
            self.c_provider.addItem(p["name"], p["id"])
        self.c_model = QLineEdit(placeholderText="model id")
        self.c_prompt = mono(False)
        self.c_prompt.setPlaceholderText("Prompt")
        self.c_prompt.setFixedHeight(100)
        send = QPushButton("Send (non-persistent)")
        send.setObjectName("Primary")
        send.clicked.connect(self.console_send)
        self.c_out = mono()
        cl.addLayout(hbox(self.c_provider, self.c_model, send))
        cl.addWidget(self.c_prompt)
        cl.addWidget(self.c_out, 1)
        tabs.addTab(cw, "API console")

        dw = QWidget()
        dl = QVBoxLayout(dw)
        self.diag = mono()
        gen = QPushButton("Generate diagnostics")
        gen.clicked.connect(self.diagnostics)
        save = QPushButton("Save report…")
        save.clicked.connect(self.save_diag)
        note = QLabel("Reports are redacted: API keys and secrets are removed. Nothing is uploaded.")
        note.setObjectName("Dim")
        dl.addLayout(hbox(gen, save, note, None))
        dl.addWidget(self.diag)
        tabs.addTab(dw, "Diagnostics")

    def on_show(self):
        self.load_logs()

    def load_logs(self):
        f = self.ctx.paths.logs / "fate.log"
        txt = f.read_text("utf-8", errors="replace")[-200_000:] if f.exists() else "(no log yet)"
        self.logs.setPlainText(redact(txt))
        self.logs.verticalScrollBar().setValue(self.logs.verticalScrollBar().maximum())

    def open_logs(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.logs)))

    def _event(self, ev):
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
        try:
            QMetaObject.invokeMethod(self.events, "appendPlainText", Qt.QueuedConnection,
                                     Q_ARG(str, redact(json.dumps(ev, default=str))))
        except RuntimeError:
            pass

    def console_send(self):
        pid, model, prompt = self.c_provider.currentData(), self.c_model.text().strip(), self.c_prompt.toPlainText()
        if not model or not prompt:
            return
        self.c_out.setPlainText("…")
        req = ChatRequest(model, [ChatMessage("user", prompt)])
        run_async(lambda progress: [progress(c.text) for c in self.ctx.providers.get(pid).stream_chat(req)],
                  on_progress=lambda t: self.c_out.insertPlainText(t), on_done=lambda _: None,
                  on_error=lambda e: self.c_out.setPlainText(f"Error: {e}"))
        self.c_out.clear()

    def diagnostics(self):
        def work():
            hw = detect_all()
            data = {"fate_ai_version": __version__, "python": sys.version, "platform": platform.platform(),
                    "frozen": getattr(sys, "frozen", False), "hardware": dataclasses.asdict(hw),
                    "providers": [{k: p[k] for k in ("id", "kind", "base_url", "enabled")} |
                                  {"has_key": self.ctx.credentials.has_api_key(p["id"])} for p in self.ctx.providers.configs()],
                    "credential_store": self.ctx.credentials.backend.name,
                    "db_schema": self.ctx.db.schema_version,
                    "settings": self.ctx.settings.settings.model_dump()}
            return redact(json.dumps(data, indent=2, default=str))
        run_async(work, on_done=self.diag.setPlainText)

    def save_diag(self):
        if not self.diag.toPlainText():
            self.diagnostics()
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save diagnostics", str(self.ctx.paths.exports / "fate-diagnostics.json"))
        if p:
            Path(p).write_text(self.diag.toPlainText(), "utf-8")
            info(self, "Saved.")
