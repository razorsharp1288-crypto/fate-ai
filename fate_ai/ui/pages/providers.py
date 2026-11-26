from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from ...ai.providers.registry import KINDS
from ..components.widgets import Badge, Banner, Card, Page, confirm, error, hbox
from ..components.worker import run_async


class AddProviderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add OpenAI-compatible endpoint")
        f = QFormLayout(self)
        self.name = QLineEdit(placeholderText="e.g. LM Studio, Groq, vLLM")
        self.url = QLineEdit(placeholderText="http://127.0.0.1:1234/v1")
        f.addRow("Name", self.name)
        f.addRow("Base URL", self.url)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class ProvidersPage(Page):
    def __init__(self, ctx):
        super().__init__("Providers", "Connect cloud and local AI backends. Cloud usage is billed directly by each "
                                      "provider to your own account — FATE AI never proxies your requests.")
        self.ctx = ctx
        add = QPushButton("+ Custom endpoint")
        add.clicked.connect(self.add_custom)
        self.header_actions.addWidget(add)
        test_all = QPushButton("Test all")
        test_all.setObjectName("Primary")
        test_all.clicked.connect(self.test_all)
        self.header_actions.addWidget(test_all)

        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setFixedWidth(260)
        self.list.currentItemChanged.connect(self._select)
        row.addWidget(self.list)
        self.detail = Card()
        row.addWidget(self.detail, 1)
        self.body.addLayout(row, 1)

        self.title = QLabel("")
        self.title.setObjectName("H2")
        self.badge = Badge("")
        self.detail.add(hbox(self.title, self.badge, None))
        self.desc = QLabel("")
        self.desc.setObjectName("Muted")
        self.desc.setWordWrap(True)
        self.detail.add(self.desc)
        form = QFormLayout()
        self.url = QLineEdit()
        self.default_model = QComboBox()
        self.default_model.setEditable(True)
        self.enabled = QCheckBox("Show this provider in chat")
        self.key_state = QLabel("")
        form.addRow("Endpoint URL", self.url)
        form.addRow("Default model", self.default_model)
        form.addRow("API key", self.key_state)
        form.addRow("", self.enabled)
        self.detail.add(form)
        save = QPushButton("Save")
        save.setObjectName("Primary")
        save.clicked.connect(self.save)
        test = QPushButton("Test connection")
        test.clicked.connect(self.test)
        fetch = QPushButton("Fetch models")
        fetch.clicked.connect(self.fetch_models)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("Danger")
        self.remove_btn.clicked.connect(self.remove)
        self.detail.add(hbox(save, test, fetch, None, self.remove_btn))
        self.result = Banner("Select a provider.")
        self.detail.add(self.result)
        self.models = QTableWidget(0, 2)
        self.models.setHorizontalHeaderLabels(["Model", "Details"])
        self.models.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.models.verticalHeader().hide()
        self.detail.add(self.models)
        self.reload()

    def reload(self, select: str | None = None):
        cur = select or (self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None)
        self.list.clear()
        for p in self.ctx.providers.configs():
            spec = KINDS[p["kind"]]
            mark = "●" if (not spec.requires_key or self.ctx.credentials.has_api_key(p["id"])) else "○"
            it = QListWidgetItem(f"{mark}  {p['name']}  ·  {'Local' if spec.is_local else 'Cloud'}")
            it.setData(Qt.UserRole, p["id"])
            self.list.addItem(it)
            if p["id"] == cur:
                self.list.setCurrentItem(it)
        if not self.list.currentItem() and self.list.count():
            self.list.setCurrentRow(0)

    def _pid(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _select(self, *_):
        pid = self._pid()
        if not pid:
            return
        p = self.ctx.provider_repo.get(pid)
        spec = KINDS[p["kind"]]
        self.title.setText(p["name"])
        self.badge.set("Local" if spec.is_local else "Cloud", "ok" if spec.is_local else "info")
        self.desc.setText(spec.description)
        self.url.setText(p["base_url"])
        self.default_model.clear()
        self.default_model.setCurrentText(p["default_model"])
        self.enabled.setChecked(p["enabled"])
        if spec.requires_key:
            k = self.ctx.credentials.get_api_key(pid)
            self.key_state.setText(f"{self.ctx.credentials.mask(k)} — manage on the API Keys page")
        else:
            k = self.ctx.credentials.get_api_key(pid)
            self.key_state.setText("Optional" + (f" ({self.ctx.credentials.mask(k)})" if k else " — not required"))
        self.remove_btn.setVisible(pid.startswith("custom_"))
        self.result.setText("Click “Test connection” to verify.")
        self.models.setRowCount(0)

    def save(self):
        pid = self._pid()
        p = self.ctx.provider_repo.get(pid)
        url = self.url.text().strip()
        if url and not url.startswith(("http://", "https://")):
            error(self, "URL must start with http:// or https://")
            return
        if url.startswith("http://") and not any(h in url for h in ("127.0.0.1", "localhost", "[::1]")) \
                and KINDS[p["kind"]].requires_key:
            if not confirm(self, "Insecure URL", "This endpoint uses plain HTTP; your API key would be sent "
                                                 "unencrypted. Continue?", danger=True):
                return
        self.ctx.provider_repo.upsert(pid, p["kind"], p["name"], url, self.default_model.currentText().strip(),
                                      self.enabled.isChecked(), p["options"])
        self.result.setText("Saved.")
        self.reload(pid)

    def test(self):
        pid = self._pid()
        self.save()
        self.result.setText("Testing…")

        def done(res):
            self.result.setText(("✓ " if res.ok else "✗ ") + res.message +
                                (f" ({res.latency_ms} ms)" if res.latency_ms else ""))
        run_async(lambda: self.ctx.providers.get(pid).test_connection(), on_done=done,
                  on_error=lambda e: self.result.setText(f"✗ {e}"))

    def fetch_models(self):
        pid = self._pid()
        self.result.setText("Fetching models…")

        def done(models):
            self.models.setRowCount(0)
            cur = self.default_model.currentText()
            self.default_model.clear()
            self.default_model.addItems([m.id for m in models])
            self.default_model.setCurrentText(cur)
            for m in models:
                r = self.models.rowCount()
                self.models.insertRow(r)
                self.models.setItem(r, 0, QTableWidgetItem(m.id))
                det = ", ".join(f"{k}: {v}" for k, v in m.details.items() if v and not isinstance(v, (dict, list)))
                self.models.setItem(r, 1, QTableWidgetItem(det))
            self.result.setText(f"✓ {len(models)} models retrieved.")
        run_async(lambda: self.ctx.providers.get(pid).list_models(), on_done=done,
                  on_error=lambda e: self.result.setText(f"✗ {e}"))

    def add_custom(self):
        d = AddProviderDialog(self)
        if d.exec():
            try:
                p = self.ctx.providers.add_custom(d.name.text().strip(), d.url.text().strip())
            except Exception as e:
                error(self, str(e))
                return
            self.reload(p["id"])

    def remove(self):
        pid = self._pid()
        if pid and confirm(self, "Remove provider", "Remove this endpoint and its stored key?", danger=True):
            self.ctx.providers.remove(pid)
            self.reload()

    def test_all(self):
        self.list.setCurrentRow(0)
        results = []

        def work():
            out = []
            for p in self.ctx.providers.configs():
                out.append((p["name"], self.ctx.providers.get(p["id"]).test_connection()))
            return out

        def done(res):
            self.result.setText("<br>".join(f"{'✓' if r.ok else '✗'} <b>{n}</b>: {r.message}" for n, r in res))
        self.result.setText("Testing all providers…")
        run_async(work, on_done=done)
        return results

    def on_show(self):
        self.reload()
