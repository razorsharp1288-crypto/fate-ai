from __future__ import annotations

import sys

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from ... import __version__
from ...resources.manager import ENFORCEMENT, PRESETS, apply_preset, set_own_priority
from ...updater.updater import Updater
from ..components.widgets import Banner, Page, confirm, error, hbox, info
from ..components.worker import run_async


def tab(form=True):
    w = QWidget()
    lay = QFormLayout(w) if form else QVBoxLayout(w)
    return w, lay


class SettingsPage(Page):
    def __init__(self, ctx, on_delete_all=None):
        super().__init__("Settings", "Preferences are stored locally in settings.json (no secrets).")
        self.ctx = ctx
        self.on_delete_all = on_delete_all
        s = ctx.settings.settings
        tabs = QTabWidget()
        tabs.setMinimumHeight(560)
        self.body.addWidget(tabs)

        w, f = tab()
        self.theme = QComboBox()
        self.theme.addItems(["dark", "midnight"])
        self.theme.setCurrentText(s.general.theme)
        self.lang = QComboBox()
        self.lang.addItem("English", "en")
        self.notify = QCheckBox("Show desktop notifications")
        self.notify.setChecked(s.general.notifications)
        self.tray = QCheckBox("Keep running in the system tray when the window is closed")
        self.tray.setChecked(s.general.minimize_to_tray)
        self.start_min = QCheckBox("Start minimised")
        self.start_min.setChecked(s.general.start_minimized)
        self.autostart = QCheckBox("Launch FATE AI when I sign in to Windows")
        self.autostart.setChecked(self._autostart_enabled())
        self.autostart.setEnabled(sys.platform == "win32")
        f.addRow("Theme", self.theme)
        f.addRow("Language", self.lang)
        for x in (self.notify, self.tray, self.start_min, self.autostart):
            f.addRow("", x)
        tabs.addTab(w, "General")

        w, f = tab()
        self.def_provider = QComboBox()
        for p in ctx.providers.configs():
            self.def_provider.addItem(p["name"], p["id"])
        self.def_provider.setCurrentIndex(max(0, self.def_provider.findData(s.ai.default_provider)))
        self.def_model = QLineEdit(s.ai.default_model)
        self.sys_prompt = QPlainTextEdit(s.ai.default_system_prompt)
        self.sys_prompt.setFixedHeight(90)
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0, 2)
        self.temp.setSingleStep(0.1)
        self.temp.setValue(s.ai.temperature)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(16, 200000)
        self.max_tokens.setValue(s.ai.max_tokens)
        self.doc_confirm = QCheckBox("Ask before sending documents to cloud providers")
        self.doc_confirm.setChecked(s.ai.confirm_cloud_document_upload)
        f.addRow("Default provider", self.def_provider)
        f.addRow("Default model", self.def_model)
        f.addRow("Default system prompt", self.sys_prompt)
        f.addRow("Temperature", self.temp)
        f.addRow("Max output tokens", self.max_tokens)
        f.addRow("", self.doc_confirm)
        tabs.addTab(w, "AI")

        w, f = tab()
        self.ollama_url = QLineEdit(s.local.ollama_url)
        self.llama_url = QLineEdit(s.local.llamacpp_url)
        self.keep_alive = QLineEdit(s.local.keep_alive)
        self.gpu_layers = QSpinBox()
        self.gpu_layers.setRange(-1, 999)
        self.gpu_layers.setValue(-1 if s.local.num_gpu_layers is None else s.local.num_gpu_layers)
        self.gpu_layers.setSpecialValueText("Automatic")
        f.addRow("Ollama URL", self.ollama_url)
        f.addRow("llama.cpp server URL", self.llama_url)
        f.addRow("Keep model loaded for", self.keep_alive)
        f.addRow("GPU layers (num_gpu)", self.gpu_layers)
        n = QLabel("Model storage is managed by Ollama. To change it, set the OLLAMA_MODELS environment variable "
                   "and restart Ollama.")
        n.setObjectName("Dim")
        n.setWordWrap(True)
        f.addRow(n)
        tabs.addTab(w, "Local models")

        w, f = tab()
        self.vm_storage = QLineEdit(s.vm.default_storage)
        b = QPushButton("Browse…")
        b.clicked.connect(lambda: self.vm_storage.setText(QFileDialog.getExistingDirectory(self, "VM storage")))
        self.vm_cpus = QSpinBox()
        self.vm_cpus.setRange(1, 256)
        self.vm_cpus.setValue(s.vm.default_cpus)
        self.vm_ram = QSpinBox()
        self.vm_ram.setRange(256, 1_048_576)
        self.vm_ram.setSingleStep(256)
        self.vm_ram.setValue(s.vm.default_ram_mb)
        self.vm_bg = QCheckBox("Let VMs keep running when FATE AI is closed")
        self.vm_bg.setChecked(s.vm.keep_running_in_background)
        f.addRow("Default VM storage", hbox(self.vm_storage, b))
        f.addRow("Default vCPUs", self.vm_cpus)
        f.addRow("Default RAM (MB)", self.vm_ram)
        f.addRow("", self.vm_bg)
        tabs.addTab(w, "Virtual machines")

        w, f = tab()
        self.sb_level = QComboBox()
        for k, label in (("process", "Level 1 — Restricted process"), ("container", "Level 2 — Container"),
                         ("vm", "Level 3 — Virtual machine")):
            self.sb_level.addItem(label, k)
        self.sb_level.setCurrentIndex(self.sb_level.findData(s.sandbox.default_level))
        self.sb_cpu = QDoubleSpinBox()
        self.sb_cpu.setRange(0.1, 256)
        self.sb_cpu.setValue(s.sandbox.cpu_limit)
        self.sb_mem = QSpinBox()
        self.sb_mem.setRange(32, 1_048_576)
        self.sb_mem.setValue(s.sandbox.memory_limit_mb)
        self.sb_timeout = QSpinBox()
        self.sb_timeout.setRange(1, 86400)
        self.sb_timeout.setValue(s.sandbox.timeout_seconds)
        self.sb_net = QCheckBox("Allow network access by default")
        self.sb_net.setChecked(s.sandbox.allow_network)
        self.sb_image = QLineEdit(s.sandbox.container_image)
        self.sb_cleanup = QCheckBox("Delete sandbox files when a sandbox is deleted")
        self.sb_cleanup.setChecked(s.sandbox.cleanup_on_delete)
        f.addRow("Default isolation level", self.sb_level)
        f.addRow("CPU limit (cores)", self.sb_cpu)
        f.addRow("Memory limit (MB)", self.sb_mem)
        f.addRow("Timeout (s)", self.sb_timeout)
        f.addRow("Container image", self.sb_image)
        f.addRow("", self.sb_net)
        f.addRow("", self.sb_cleanup)
        tabs.addTab(w, "Sandbox")

        w, lay = tab(form=False)
        self.preset = QComboBox()
        for k, p in PRESETS.items():
            self.preset.addItem(f"{p.label} — {p.description}", k)
        self.preset.addItem("Custom — set limits manually", "custom")
        self.preset.setCurrentIndex(self.preset.findData(s.resources.preset))
        self.preset.activated.connect(self._preset)
        rf = QFormLayout()
        self.cpu_pct = QSpinBox()
        self.cpu_pct.setRange(5, 100)
        self.cpu_pct.setSuffix(" %")
        self.cpu_pct.setValue(s.resources.max_cpu_percent)
        self.ram_budget = QSpinBox()
        self.ram_budget.setRange(256, 1_048_576)
        self.ram_budget.setSingleStep(256)
        self.ram_budget.setSuffix(" MB")
        self.ram_budget.setValue(s.resources.ram_budget_mb)
        self.prio = QComboBox()
        self.prio.addItems(["low", "normal", "high"])
        self.prio.setCurrentText(s.resources.background_priority)
        self.gpu_idx = QSpinBox()
        self.gpu_idx.setRange(-1, 16)
        self.gpu_idx.setSpecialValueText("Automatic")
        self.gpu_idx.setValue(-1 if s.resources.gpu_index is None else s.resources.gpu_index)
        rf.addRow("Preset", self.preset)
        rf.addRow("Max CPU for local inference", self.cpu_pct)
        rf.addRow("RAM budget for workloads", self.ram_budget)
        rf.addRow("FATE AI process priority", self.prio)
        rf.addRow("Inference GPU index", self.gpu_idx)
        lay.addLayout(rf)
        t = QTableWidget(len(ENFORCEMENT), 2)
        t.setHorizontalHeaderLabels(["Control", "Status"])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.verticalHeader().hide()
        for i, (name, enforced) in enumerate(ENFORCEMENT):
            t.setItem(i, 0, QTableWidgetItem(name))
            t.setItem(i, 1, QTableWidgetItem("Enforced" if enforced else "Estimate only"))
        lay.addWidget(t)
        lay.addWidget(Banner("FATE AI never modifies Windows system processes, antivirus, Defender, firewall, "
                             "updates or essential services to free resources."))
        tabs.addTab(w, "Resources")

        w, lay = tab(form=False)
        self.store_hist = QCheckBox("Store chat history on this PC")
        self.store_hist.setChecked(s.privacy.store_chat_history)
        lay.addWidget(self.store_hist)
        lay.addWidget(QLabel(f"Data folder: {ctx.paths.root}"))
        lay.addWidget(QLabel(f"API keys: {ctx.credentials.backend.name}"))
        open_btn = QPushButton("Open data folder")
        open_btn.clicked.connect(self._open_data)
        dele = QPushButton("Delete all local data…")
        dele.setObjectName("Danger")
        dele.clicked.connect(self._delete_all)
        lay.addLayout(hbox(open_btn, None, dele))
        lay.addStretch(1)
        tabs.addTab(w, "Privacy")

        w, f = tab()
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level.setCurrentText(s.advanced.log_level)
        self.dev = QCheckBox("Developer mode")
        self.dev.setChecked(s.advanced.developer_mode)
        self.channel = QComboBox()
        self.channel.addItems(["stable", "beta"])
        self.channel.setCurrentText(s.advanced.update_channel)
        self.repo = QLineEdit(s.advanced.update_repository)
        self.repo.setPlaceholderText("owner/repo on GitHub that publishes FATE AI releases")
        upd = QPushButton("Check for updates")
        upd.clicked.connect(self.check_updates)
        self.upd_label = QLabel(f"Current version {__version__}")
        self.upd_label.setWordWrap(True)
        f.addRow("Log level", self.log_level)
        f.addRow("", self.dev)
        f.addRow("Update channel", self.channel)
        f.addRow("Update source", self.repo)
        f.addRow(upd, self.upd_label)
        tabs.addTab(w, "Advanced")

        save = QPushButton("Save settings")
        save.setObjectName("Primary")
        save.clicked.connect(self.save)
        self.body.addLayout(hbox(None, save))

    def _preset(self):
        k = self.preset.currentData()
        if k in PRESETS:
            apply_preset(self.ctx.settings, k)
            r = self.ctx.settings.settings.resources
            self.cpu_pct.setValue(r.max_cpu_percent)
            self.ram_budget.setValue(r.ram_budget_mb)
            self.prio.setCurrentText(r.background_priority)

    def save(self):
        try:
            self.ctx.settings.update(
                general={"theme": self.theme.currentText(), "notifications": self.notify.isChecked(),
                         "minimize_to_tray": self.tray.isChecked(), "start_minimized": self.start_min.isChecked()},
                ai={"default_provider": self.def_provider.currentData(), "default_model": self.def_model.text().strip(),
                    "default_system_prompt": self.sys_prompt.toPlainText(), "temperature": self.temp.value(),
                    "max_tokens": self.max_tokens.value(),
                    "confirm_cloud_document_upload": self.doc_confirm.isChecked()},
                local={"ollama_url": self.ollama_url.text().strip(), "llamacpp_url": self.llama_url.text().strip(),
                       "keep_alive": self.keep_alive.text().strip() or "5m",
                       "num_gpu_layers": None if self.gpu_layers.value() < 0 else self.gpu_layers.value()},
                vm={"default_storage": self.vm_storage.text().strip(), "default_cpus": self.vm_cpus.value(),
                    "default_ram_mb": self.vm_ram.value(), "keep_running_in_background": self.vm_bg.isChecked()},
                sandbox={"default_level": self.sb_level.currentData(), "cpu_limit": self.sb_cpu.value(),
                         "memory_limit_mb": self.sb_mem.value(), "timeout_seconds": self.sb_timeout.value(),
                         "allow_network": self.sb_net.isChecked(), "container_image": self.sb_image.text().strip(),
                         "cleanup_on_delete": self.sb_cleanup.isChecked()},
                resources={"preset": self.preset.currentData(), "max_cpu_percent": self.cpu_pct.value(),
                           "ram_budget_mb": self.ram_budget.value(), "background_priority": self.prio.currentText(),
                           "gpu_index": None if self.gpu_idx.value() < 0 else self.gpu_idx.value()},
                privacy={"store_chat_history": self.store_hist.isChecked()},
                advanced={"log_level": self.log_level.currentText(), "developer_mode": self.dev.isChecked(),
                          "update_channel": self.channel.currentText(), "update_repository": self.repo.text().strip()})
        except Exception as e:
            error(self, f"Invalid setting: {e}")
            return
        # keep provider endpoints in sync with local engine URLs
        for pid, url in (("ollama", self.ollama_url.text().strip()), ("llamacpp", self.llama_url.text().strip())):
            p = self.ctx.provider_repo.get(pid)
            if p and url:
                self.ctx.provider_repo.upsert(pid, p["kind"], p["name"], url, p["default_model"], p["enabled"],
                                              p["options"])
        set_own_priority(self.prio.currentText())
        self._set_autostart(self.autostart.isChecked())
        import logging
        logging.getLogger().setLevel(self.log_level.currentText())
        info(self, "Settings saved.")

    # -- autostart (per-user Run key, no elevation) -------------------------
    @staticmethod
    def _autostart_enabled() -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, "FATE AI")
                return True
        except OSError:
            return False

    @staticmethod
    def _set_autostart(on: bool) -> None:
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            return
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "FATE AI", 0, winreg.REG_SZ, f'"{sys.executable}" --minimized')
            else:
                try:
                    winreg.DeleteValue(k, "FATE AI")
                except OSError:
                    pass

    def _open_data(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.root)))

    def _delete_all(self):
        if not confirm(self, "Delete all local data", "This permanently deletes all conversations, prompts, "
                       "projects registered in FATE AI (files you opened from elsewhere are kept), sandboxes, settings "
                       "and stored API keys.\n\nFATE AI will close afterwards. Continue?", danger=True):
            return
        if self.on_delete_all:
            self.on_delete_all()

    def check_updates(self):
        repo = self.repo.text().strip()
        self.upd_label.setText("Checking…")
        up = Updater(repo, self.ctx.paths.updates)

        def done(i):
            if not i.available:
                self.upd_label.setText(f"You're up to date ({i.current}).")
                return
            self.upd_label.setText(f"Version {i.latest} is available.")
            if confirm(self, "Update available", f"FATE AI {i.latest} is available.\n\n{i.notes[:1200]}\n\n"
                                                 "Download and verify it now?"):
                self._download(up, i)
        run_async(lambda: up.check(self.channel.currentText() == "beta"), on_done=done,
                  on_error=lambda e: self.upd_label.setText(str(e)))

    def _download(self, up, i):
        def done(path):
            if confirm(self, "Install update", f"The installer was downloaded and verified:\n{path}\n\n"
                                               "Close FATE AI and run it now?"):
                import os
                os.startfile(str(path)) if sys.platform == "win32" else None
                from PySide6.QtWidgets import QApplication
                QApplication.instance().quit()
        run_async(lambda progress: up.download(i, progress=lambda d, t: progress((d, t))), on_progress=lambda p: self.upd_label.setText(
            f"Downloading… {p[0] / 2**20:.1f} / {p[1] / 2**20:.1f} MB" if p[1] else "Downloading…"),
                  on_done=done, on_error=lambda e: error(self, str(e)))
