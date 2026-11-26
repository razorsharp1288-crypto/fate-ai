from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem

from ...ai.providers.registry import KINDS
from ..components.widgets import Banner, Card, Page, confirm, error, hbox
from ..components.worker import run_async


class APIKeysPage(Page):
    def __init__(self, ctx):
        super().__init__("API Keys", "Keys are stored in the Windows Credential Manager — never in FATE AI's "
                                     "database, settings or logs, and never sent anywhere except the provider itself.")
        self.ctx = ctx
        vault = ctx.credentials.backend
        self.body.addWidget(Banner(
            f"🔒 Secure storage: <b>{vault.name}</b>" +
            ("" if vault.persistent else " — <b>keys will be forgotten when FATE AI closes</b> because no OS "
                                         "credential vault is available.")
            + "<br>FATE AI never scans your computer for keys. Enter them manually below.", warn=not vault.persistent))
        self.grid_card = Card("Your keys")
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid_card.add(self.grid)
        self.body.addWidget(self.grid_card)

        assist = Card("Setup assistant")
        d = QLabel("Checks every provider configured in FATE AI: credentials present, authentication valid, models "
                   "retrievable. It never looks for keys outside FATE AI.")
        d.setObjectName("Muted")
        d.setWordWrap(True)
        assist.add(d)
        run_btn = QPushButton("Run readiness check")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self.check_all)
        assist.add(hbox(run_btn, None))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Provider", "Credentials", "Connection", "Advice"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(220)
        assist.add(self.table)
        self.body.addWidget(assist)
        self.body.addStretch(1)
        self.rows = {}
        self.build_rows()

    def build_rows(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        r = 0
        for p in self.ctx.providers.configs():
            spec = KINDS[p["kind"]]
            if spec.is_local and not p["id"].startswith("custom_"):
                continue
            name = QLabel(f"<b>{p['name']}</b>")
            state = QLabel(self.ctx.credentials.mask(self.ctx.credentials.get_api_key(p["id"])))
            state.setObjectName("Muted")
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.Password)
            edit.setPlaceholderText("Paste API key" + ("" if spec.requires_key else " (optional)"))
            show = QPushButton("Show")
            show.setCheckable(True)
            show.toggled.connect(lambda on, e=edit: e.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
            save = QPushButton("Save")
            save.setObjectName("Primary")
            test = QPushButton("Test")
            delete = QPushButton("Remove")
            delete.setObjectName("Danger")
            result = QLabel("")
            result.setWordWrap(True)
            pid = p["id"]
            save.clicked.connect(lambda _=False, pid=pid, e=edit: self.save(pid, e))
            test.clicked.connect(lambda _=False, pid=pid, lab=result: self.test(pid, lab))
            delete.clicked.connect(lambda _=False, pid=pid: self.delete(pid))
            for c, w in enumerate((name, state, edit, show, save, test, delete)):
                self.grid.addWidget(w, r, c)
            self.grid.addWidget(result, r + 1, 0, 1, 7)
            self.grid.setColumnStretch(2, 1)
            r += 2

    def save(self, pid, edit):
        try:
            self.ctx.credentials.set_api_key(pid, edit.text())
        except Exception as e:
            error(self, str(e))
            return
        edit.clear()
        self.build_rows()

    def delete(self, pid):
        if confirm(self, "Remove key", "Remove this API key from the credential store?", danger=True):
            self.ctx.credentials.delete_api_key(pid)
            self.build_rows()

    def test(self, pid, label):
        label.setText("Testing…")
        run_async(lambda: self.ctx.providers.get(pid).test_connection(),
                  on_done=lambda r: label.setText(("✓ " if r.ok else "✗ ") + r.message),
                  on_error=lambda e: label.setText(f"✗ {e}"))

    def check_all(self):
        def work():
            rows = []
            for p in self.ctx.providers.configs():
                spec = KINDS[p["kind"]]
                has = self.ctx.credentials.has_api_key(p["id"])
                cred = "Present" if has else ("Missing" if spec.requires_key else "Not needed")
                if spec.requires_key and not has:
                    rows.append((p["name"], cred, "—", "Add your API key above to use this provider."))
                    continue
                res = self.ctx.providers.get(p["id"]).test_connection()
                advice = "Ready." if res.ok else self._advice(res.message, spec)
                rows.append((p["name"], cred, "OK" if res.ok else "Failed", advice if res.ok else
                             f"{advice} ({res.message})"))
            return rows

        def done(rows):
            self.table.setRowCount(0)
            for row in rows:
                r = self.table.rowCount()
                self.table.insertRow(r)
                for c, v in enumerate(row):
                    self.table.setItem(r, c, QTableWidgetItem(v))
        run_async(work, on_done=done)

    @staticmethod
    def _advice(msg: str, spec) -> str:
        m = msg.lower()
        if "authentication" in m or "401" in m:
            return "The key was rejected — check it was copied fully and is active."
        if "403" in m:
            return "Key lacks permission for this API/organisation."
        if "rate" in m:
            return "Rate limited or out of credit — check your provider billing."
        if "connect" in m or "not running" in m:
            return "Server unreachable — start it or check the URL." if spec.is_local else "Check internet connection."
        return "See the error message."

    def on_show(self):
        self.build_rows()
