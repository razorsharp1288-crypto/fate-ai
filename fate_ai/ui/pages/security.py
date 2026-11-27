from __future__ import annotations

import sys

from PySide6.QtWidgets import QGridLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from ..components.widgets import Badge, Card, Page


def is_admin() -> bool | None:
    try:
        if sys.platform == "win32":
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        import os
        return os.geteuid() == 0
    except Exception:
        return None


class SecurityPage(Page):
    def __init__(self, ctx):
        super().__init__("Security Center", "How FATE AI protects your keys, data and computer.")
        self.ctx = ctx
        self.status = Card("Status")
        self.grid = QGridLayout()
        self.status.add(self.grid)
        self.body.addWidget(self.status)

        agents = Card("Agent permissions")
        self.agents = QTableWidget(0, 6)
        self.agents.setHorizontalHeaderLabels(["Agent", "Read files", "Write files (asks)", "Sandbox (asks)",
                                               "Network", "System info"])
        self.agents.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.agents.verticalHeader().hide()
        self.agents.setMinimumHeight(200)
        agents.add(self.agents)
        n = QLabel("Agents can only access the folder of the project you open them in. Destructive actions always "
                   "require your confirmation and are written to the audit log.")
        n.setObjectName("Dim")
        n.setWordWrap(True)
        agents.add(n)
        self.body.addWidget(agents)

        audit = Card("Audit log")
        self.audit = QTableWidget(0, 4)
        self.audit.setHorizontalHeaderLabels(["Time (UTC)", "Category", "Action", "Detail"])
        self.audit.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.audit.verticalHeader().hide()
        self.audit.setMinimumHeight(300)
        audit.add(self.audit)
        self.body.addWidget(audit)

    def _row(self, r, title, ok, text):
        while (it := self.grid.itemAtPosition(r, 0)) is not None:
            for c in range(3):
                w = self.grid.itemAtPosition(r, c)
                if w and w.widget():
                    w.widget().deleteLater()
                    self.grid.removeItem(w)
            break
        kind = {True: "ok", False: "warn", None: "muted"}[ok]
        label = {True: "OK", False: "Attention", None: "Info"}[ok]
        t = QLabel(f"<b>{title}</b>")
        d = QLabel(text)
        d.setWordWrap(True)
        d.setObjectName("Muted")
        self.grid.addWidget(t, r, 0)
        self.grid.addWidget(Badge(label, kind), r, 1)
        self.grid.addWidget(d, r, 2)
        self.grid.setColumnStretch(2, 1)

    def on_show(self):
        vault = self.ctx.credentials.backend
        admin = is_admin()
        s = self.ctx.settings.settings
        cloud = [p["name"] for p in self.ctx.providers.configs()
                 if not self.ctx.providers.is_local(p) and self.ctx.credentials.has_api_key(p["id"])]
        rows = [
            ("API credentials", vault.persistent, f"Stored in {vault.name}. Never in the database, settings or logs; "
                                                  f"secrets are redacted from logs and diagnostics."),
            ("Privileges", admin is False, "Running as a standard user (least privilege)." if admin is False else
             "FATE AI is running elevated. It does not need administrator rights — restart it normally."),
            ("Local data", None, f"All chats, settings and projects are stored in {self.ctx.paths.root}. Delete "
                                 f"everything in Settings → Privacy."),
            ("Cloud data flow", None, ("Messages are sent only to providers you configured: " + ", ".join(cloud))
             if cloud else "No cloud provider has a key — everything stays on this PC."),
            ("Document uploads", s.ai.confirm_cloud_document_upload,
             "You are asked before any document is sent to a cloud model." if s.ai.confirm_cloud_document_upload
             else "Confirmation before sending documents to the cloud is OFF."),
            ("Sandbox defaults", not s.sandbox.allow_network,
             f"Default level: {s.sandbox.default_level}. Network {'blocked' if not s.sandbox.allow_network else 'ALLOWED'}"
             f" for container/VM sandboxes; {s.sandbox.memory_limit_mb} MB / {s.sandbox.timeout_seconds}s limits."),
            ("Prompt injection", True, "Imported documents are wrapped as untrusted data and suspicious instructions "
                                       "are flagged."),
            ("Updates", None, "Updates are verified against SHA-256 checksums (and a signature when configured) and "
                              "never executed without your confirmation."),
        ]
        for i, r in enumerate(rows):
            self._row(i, *r)
        self.agents.setRowCount(0)
        for a in self.ctx.agents.list():
            r = self.agents.rowCount()
            self.agents.insertRow(r)
            p = a.get("permissions", {})
            vals = [a["name"]] + ["✓" if p.get(k) else "—" for k in ("read_files", "write_files", "run_sandbox",
                                                                     "network", "system_info")]
            for c, v in enumerate(vals):
                self.agents.setItem(r, c, QTableWidgetItem(v))
        self.audit.setRowCount(0)
        for e in self.ctx.audit.recent():
            r = self.audit.rowCount()
            self.audit.insertRow(r)
            for c, k in enumerate(("created_at", "category", "action", "detail")):
                self.audit.setItem(r, c, QTableWidgetItem(str(e[k])))
