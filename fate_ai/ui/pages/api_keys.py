from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem)

from ...ai.providers.autodetect import cloud_candidates, connect, connect_known
from ...ai.providers.catalog import BY_ID, PRESETS, detect_from_key
from ..components.widgets import Banner, Card, Page, confirm, error, hbox
from ..components.worker import run_async
from ..dialogs.add_provider import CatalogGrid, CustomEndpointDialog, ModelsDialog, PresetSetupDialog


class APIKeysPage(Page):
    def __init__(self, ctx):
        super().__init__("API Keys", "Connect any AI service with your own key — OpenAI, Claude, Gemini, Grok, "
                                     "Mistral, DeepSeek, Groq, OpenRouter, Inception and 30+ more, or any custom endpoint.")
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

        # paste any key -> detect -> save -> test, nothing else to fill in
        paste = Card("Paste your API key", accent=True)
        hint = QLabel("Just paste the key. FATE AI works out which service it belongs to, saves it securely, tests it "
                      "and picks a model — no URL or settings needed.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        paste.add(hint)
        self.any_key = QLineEdit()
        self.any_key.setEchoMode(QLineEdit.Password)
        self.any_key.setPlaceholderText("Paste any API key here and press Enter")
        self.any_key.setMinimumHeight(40)
        self.any_key.returnPressed.connect(self.connect_key)
        self.any_key.textChanged.connect(self._key_changed)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(lambda on: self.any_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("Primary")
        self.connect_btn.setMinimumHeight(40)
        self.connect_btn.clicked.connect(self.connect_key)
        paste.add(hbox(self.any_key, show, self.connect_btn))
        self.key_status = QLabel("")
        self.key_status.setWordWrap(True)
        self.key_status.setTextFormat(Qt.RichText)
        paste.add(self.key_status)
        self.suggest_label = QLabel("")
        self.suggest_label.setObjectName("Dim")
        paste.add(self.suggest_label)
        self.suggest_row = QGridLayout()
        paste.add(self.suggest_row)
        self.try_all_btn = QPushButton("Find it automatically (tries the key with each known service)")
        self.try_all_btn.setObjectName("Primary")
        self.try_all_btn.clicked.connect(lambda: self.connect_key(allow_all=True))
        self.try_all_btn.hide()
        self.pick = QComboBox()
        self.pick.addItem("…or choose the service yourself", None)
        for pr in PRESETS:
            if pr.requires_key and not pr.needs_url:
                self.pick.addItem(pr.name, pr.id)
        self.pick.activated.connect(self._picked)
        self.pick.hide()
        paste.add(hbox(self.try_all_btn, self.pick, None))
        self.open_chat = QPushButton("Start chatting →")
        self.open_chat.setObjectName("Primary")
        self.open_chat.hide()
        self.open_chat.clicked.connect(self._go_chat)
        self.models_btn = QPushButton("See all models")
        self.models_btn.hide()
        self.models_btn.clicked.connect(lambda: ModelsDialog(self.ctx, self._last_connected, self).exec())
        paste.add(hbox(self.open_chat, self.models_btn, None))
        self._debounce = QTimer(self, singleShot=True, interval=700, timeout=self._auto_connect)
        self._busy = False
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

    # -- paste & connect -----------------------------------------------------
    def _key_changed(self, text: str):
        for w in (self.try_all_btn, self.pick, self.open_chat, self.models_btn):
            w.hide()
        self.suggest_label.setText("")
        self._clear_suggestions()
        key = text.strip()
        if len(key) < 12:
            self.key_status.setText("")
            return
        hits = detect_from_key(key)
        if len(hits) == 1:
            self.key_status.setText(f"Looks like a <b>{hits[0].name}</b> key — connecting…")
            self._debounce.start()  # pasted a recognisable key: connect automatically
        elif hits:
            self.key_status.setText("Press <b>Connect</b> — FATE AI will check which of these it belongs to: "
                                    + ", ".join(h.name for h in hits))
        else:
            self.key_status.setText("Press <b>Connect</b> to set it up.")

    def _auto_connect(self):
        if not self._busy and len(detect_from_key(self.any_key.text().strip())) == 1:
            self.connect_key()

    def _clear_suggestions(self):
        while self.suggest_row.count():
            w = self.suggest_row.takeAt(0).widget()
            if w:
                w.deleteLater()

    def connect_key(self, allow_all: bool = False):
        key = self.any_key.text().strip()
        if not key or self._busy:
            return
        hits = detect_from_key(key)
        if not hits and not allow_all:
            self.key_status.setText("FATE AI doesn't recognise this key's format. Click below to find the service "
                                    "automatically, or choose it from the list.")
            self.try_all_btn.show()
            self.pick.show()
            return
        self._busy = True
        self.connect_btn.setEnabled(False)
        n = len(hits) if hits else len(cloud_candidates())
        self.key_status.setText(f"Checking {'your key' if n == 1 else f'{n} services'}…")

        def done(res):
            self._busy = False
            self.connect_btn.setEnabled(True)
            winner, results = res
            if winner:
                self._success(winner)
                return
            first = results[0].message if results else "no response"
            if hits and not allow_all:
                self.key_status.setText(f"✗ {', '.join(h.name for h in hits)} rejected this key ({first}). "
                                        f"Check it was copied completely, or let FATE AI search other services.")
                self.try_all_btn.show()
            else:
                self.key_status.setText("✗ No known service accepted this key. Check it is active, or add it as a "
                                        "custom endpoint (top right).")
            self.pick.show()
        run_async(lambda: connect(self.ctx, key, allow_all=allow_all), on_done=done,
                  on_error=lambda e: (setattr(self, "_busy", False), self.connect_btn.setEnabled(True),
                                      self.key_status.setText(f"✗ {e}")))

    def _success(self, winner):
        self.any_key.blockSignals(True)
        self.any_key.clear()
        self.any_key.blockSignals(False)
        model = self.ctx.provider_repo.get(winner.preset.id).get("default_model") or "—"
        self.key_status.setText(f"<span style='color:#34D399'>✓ Connected to <b>{winner.preset.name}</b></span> — "
                                f"{len(winner.models)} models available. Default model: <b>{model}</b>. "
                                f"Key saved to {self.ctx.credentials.backend.name}.")
        self.open_chat.show()
        self.models_btn.show()
        self._last_connected = winner.preset.id
        self.refresh()
        win = self.window()
        if hasattr(win, "toast"):
            win.toast(f"✓ {winner.preset.name} connected")

    def _picked(self, i: int):
        pid = self.pick.itemData(i)
        if not pid:
            return
        key = self.any_key.text().strip()
        self.key_status.setText(f"Checking with {BY_ID[pid].name}…")

        def work():
            from ...ai.providers.autodetect import find_service
            winner, results = find_service(key, candidates=[BY_ID[pid]])
            if winner:
                return connect_known(self.ctx, key, winner)
            return None, results

        def done(res):
            winner, results = res
            if winner:
                self._success(winner)
            else:
                self.key_status.setText(f"✗ {BY_ID[pid].name} rejected the key: "
                                        f"{results[0].message if results else 'no response'}")
        run_async(work, on_done=done, on_error=lambda e: self.key_status.setText(f"✗ {e}"))

    def _go_chat(self):
        win = self.window()
        if hasattr(win, "navigate"):
            win.navigate("chat")
            chat = win.page("chat")
            if hasattr(chat, "_load_providers"):
                chat._load_providers()
                i = chat.provider.findData(getattr(self, "_last_connected", ""))
                if i >= 0:
                    chat.provider.setCurrentIndex(i)

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
            models = QPushButton("Models")
            models.clicked.connect(lambda _=False, pid=p["id"]: ModelsDialog(self.ctx, pid, self).exec())
            test = QPushButton("Test")
            rm = QPushButton("Remove")
            rm.setObjectName("Danger")
            pid = p["id"]
            edit.clicked.connect(lambda _=False, pid=pid: self._edit(pid))
            test.clicked.connect(lambda _=False, pid=pid, lab=result: self.test(pid, lab))
            rm.clicked.connect(lambda _=False, pid=pid: self.remove(pid))
            for c, w in enumerate((name, state, result, models, edit, test, rm)):
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
