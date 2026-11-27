from __future__ import annotations

from PySide6.QtWidgets import (QGridLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem)

from ...ai.providers.catalog import BY_ID, detect_from_key
from ..components.widgets import Banner, Card, Page, confirm, error, hbox
from ..components.worker import run_async
from ..dialogs.add_provider import CatalogGrid, CustomEndpointDialog, PresetSetupDialog


class APIKeysPage(Page):
    def __init__(self, ctx):
        super().__init__("API Keys", "Connect any AI service with your own key — OpenAI, Claude, Gemini, Grok, "
                                     "Mistral, DeepSeek, Groq, OpenRouter and 25+ more, or any custom endpoint.")
        self.ctx = ctx
        vault = ctx.credentials.backend
        custom = QPushButton("+ Custom endpoint")
        custom.clicked.connect(self.add_custom)
        self.header_actions.addWidget(custom)
        self.body.addWidget(Banner(
            f"🔒 Keys are stored in <b>{vault.name}</b> — never in FATE AI's database, settings or logs, and only "
            f"sent to the service they belong to. FATE AI never scans your PC for keys." +
            ("" if vault.persistent else " <b>No OS credential vault is available, so keys are forgotten when the "
                                         "app closes.</b>"), warn=not vault.persistent))

        # paste any key
        paste = Card("Paste any API key", accent=True)
        hint = QLabel("FATE AI recognises the key format and suggests which service it belongs to.")
        hint.setObjectName("Muted")
        paste.add(hint)
        self.any_key = QLineEdit()
        self.any_key.setEchoMode(QLineEdit.Password)
        self.any_key.setPlaceholderText("sk-…, sk-ant-…, AIza…, gsk_…, xai-…, sk-or-…, hf_…")
        self.any_key.textChanged.connect(self.detect)
        paste.add(self.any_key)
        self.suggest_label = QLabel("")
        self.suggest_label.setObjectName("Dim")
        paste.add(self.suggest_label)
        self.suggest_row = QGridLayout()
        paste.add(self.suggest_row)
        self.body.addWidget(paste)

        # your providers
        self.mine = Card("Your connected services")
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.mine.add(self.grid)
        self.body.addWidget(self.mine)

        cat = Card("Add a service")
        self.catalog = CatalogGrid(ctx)
        self.catalog.picked.connect(self.setup)
        cat.add(self.catalog)
        self.body.addWidget(cat)

        assist = Card("Setup assistant")
        d = QLabel("Checks every service configured in FATE AI: key present, authentication valid, models retrievable.")
        d.setObjectName("Muted")
        d.setWordWrap(True)
        assist.add(d)
        run_btn = QPushButton("Run readiness check")
        run_btn.clicked.connect(self.check_all)
        assist.add(hbox(run_btn, None))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Service", "Key", "Connection", "Advice"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(220)
        assist.add(self.table)
        self.body.addWidget(assist)
        self.body.addStretch(1)
        self.build_rows()

    # -- paste & detect -----------------------------------------------------
    def detect(self, text: str):
        while self.suggest_row.count():
            w = self.suggest_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        key = text.strip()
        if len(key) < 8:
            self.suggest_label.setText("")
            return
        hits = detect_from_key(key)
        self.suggest_label.setText("Looks like:" if hits else "Unknown format — pick the service from the list below, "
                                                              "or add a custom endpoint.")
        for i, p in enumerate(hits):
            b = QPushButton(f"Use as {p.name}")
            b.setObjectName("Primary" if i == 0 else "")
            b.clicked.connect(lambda _=False, p=p: self.setup(p, key))
            self.suggest_row.addWidget(b, 0, i)

    def setup(self, preset, prefill: str = ""):
        if PresetSetupDialog(self.ctx, preset, prefill_key=prefill or "", parent=self).exec():
            self.any_key.clear()
        self.refresh()

    def add_custom(self):
        CustomEndpointDialog(self.ctx, self).exec()
        self.refresh()

    def refresh(self):
        self.build_rows()
        self.catalog.rebuild()

    # -- connected list -----------------------------------------------------
    def build_rows(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        r = 0
        for p in self.ctx.providers.configs():
            local = self.ctx.providers.is_local(p)
            needs = self.ctx.providers.requires_key(p)
            has = self.ctx.credentials.has_api_key(p["id"])
            if local and not has and not p["id"].startswith("custom_"):
                continue
            name = QLabel(f"<b>{p['name']}</b>")
            state = QLabel(self.ctx.credentials.mask(self.ctx.credentials.get_api_key(p["id"])) if has
                           else ("<span style='color:#FBBF24'>key missing</span>" if needs else "no key needed"))
            state.setObjectName("Muted")
            result = QLabel("")
            result.setWordWrap(True)
            result.setObjectName("Dim")
            edit = QPushButton("Change key")
            test = QPushButton("Test")
            rm = QPushButton("Remove")
            rm.setObjectName("Danger")
            pid = p["id"]
            edit.clicked.connect(lambda _=False, pid=pid: self._edit(pid))
            test.clicked.connect(lambda _=False, pid=pid, lab=result: self.test(pid, lab))
            rm.clicked.connect(lambda _=False, pid=pid: self.remove(pid))
            for c, w in enumerate((name, state, result, edit, test, rm)):
                self.grid.addWidget(w, r, c)
            r += 1
        self.grid.setColumnStretch(2, 1)
        if r == 0:
            self.grid.addWidget(QLabel("No cloud services connected yet — paste a key above or pick one below."), 0, 0)

    def _edit(self, pid):
        if pid in BY_ID:
            self.setup(BY_ID[pid])
            return
        from PySide6.QtWidgets import QInputDialog
        key, ok = QInputDialog.getText(self, "API key", "New key:", QLineEdit.Password)
        if ok and key.strip():
            try:
                self.ctx.credentials.set_api_key(pid, key)
            except Exception as e:
                error(self, str(e))
            self.refresh()

    def remove(self, pid):
        builtin = pid in ("ollama", "llamacpp", "openai", "anthropic")
        msg = "Remove the stored key for this service?" if builtin else "Remove this service and its stored key?"
        if confirm(self, "Remove", msg, danger=True):
            if builtin:
                self.ctx.credentials.delete_api_key(pid)
            else:
                self.ctx.providers.remove(pid)
            self.refresh()

    def test(self, pid, label):
        label.setText("Testing…")
        run_async(lambda: self.ctx.providers.get(pid).test_connection(),
                  on_done=lambda r: label.setText(("✓ " if r.ok else "✗ ") + r.message),
                  on_error=lambda e: label.setText(f"✗ {e}"))

    def check_all(self):
        def work():
            rows = []
            for p in self.ctx.providers.configs():
                needs = self.ctx.providers.requires_key(p)
                has = self.ctx.credentials.has_api_key(p["id"])
                cred = "Present" if has else ("Missing" if needs else "Not needed")
                if needs and not has:
                    rows.append((p["name"], cred, "—", "Add your API key to use this service."))
                    continue
                res = self.ctx.providers.get(p["id"]).test_connection()
                rows.append((p["name"], cred, "OK" if res.ok else "Failed",
                             "Ready." if res.ok else f"{self._advice(res.message, self.ctx.providers.is_local(p))} "
                                                     f"({res.message})"))
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
    def _advice(msg: str, local: bool) -> str:
        m = msg.lower()
        if "authentication" in m or "401" in m:
            return "The key was rejected — check it was copied fully and is active."
        if "403" in m:
            return "Key lacks permission for this API/organisation."
        if "rate" in m:
            return "Rate limited or out of credit — check your provider billing."
        if "connect" in m or "not running" in m:
            return "Server unreachable — start it or check the URL." if local else "Check internet connection."
        if "404" in m:
            return "This service may not list models — type the model name in chat instead."
        return "See the error message."

    def on_show(self):
        self.refresh()
