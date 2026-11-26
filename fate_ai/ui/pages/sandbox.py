from __future__ import annotations

import time
from pathlib import Path

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ...sandbox.base import ISOLATION_DESCRIPTIONS
from ..components.icons import icon
from ..components.widgets import Badge, Banner, Card, Page, StatTile, confirm, error, hbox
from ..components.worker import run_async
from ..themes import MONO_STACK


class NewSandboxDialog(QDialog):
    def __init__(self, ctx, parent=None, existing: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sandbox settings" if existing else "Create sandbox")
        self.setMinimumWidth(560)
        s = ctx.settings.settings.sandbox
        cfg = (existing or {}).get("config", {})
        f = QFormLayout(self)
        self.name = QLineEdit(existing["name"] if existing else "")
        self.name.setEnabled(existing is None)
        self.level = QComboBox()
        for key, (label, _) in ISOLATION_DESCRIPTIONS.items():
            self.level.addItem(label, key)
        self.level.setCurrentIndex(self.level.findData(existing["level"] if existing else s.default_level))
        self.level.setEnabled(existing is None)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setObjectName("Muted")
        self.level.currentIndexChanged.connect(self._level_changed)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 86400)
        self.timeout.setValue(cfg.get("timeout_s", s.timeout_seconds))
        self.timeout.setSuffix(" s")
        self.cpu = QDoubleSpinBox()
        self.cpu.setRange(0.1, psutil.cpu_count() or 1)
        self.cpu.setValue(min(cfg.get("cpu_limit", s.cpu_limit), psutil.cpu_count() or 1))
        self.cpu.setSuffix(" cores")
        self.mem = QSpinBox()
        self.mem.setRange(32, int(psutil.virtual_memory().total // 2 ** 20 * 0.75))
        self.mem.setValue(cfg.get("memory_mb", s.memory_limit_mb))
        self.mem.setSuffix(" MB")
        self.procs = QSpinBox()
        self.procs.setRange(1, 4096)
        self.procs.setValue(cfg.get("max_processes", 64))
        self.network = QCheckBox("Allow network access (off by default)")
        self.network.setChecked(cfg.get("allow_network", s.allow_network))
        self.image = QLineEdit(cfg.get("image", s.container_image))
        self.vm_backend = QComboBox()
        self.vm_backend.addItem("VirtualBox", "virtualbox")
        self.vm_backend.addItem("Hyper-V", "hyperv")
        if cfg.get("vm_backend"):
            self.vm_backend.setCurrentIndex(self.vm_backend.findData(cfg["vm_backend"]))
        self.vm_id = QLineEdit(cfg.get("vm_id", ""))
        self.vm_id.setPlaceholderText("Name of a prepared VM (with Guest Additions / PowerShell Direct)")
        self.vm_user = QLineEdit(cfg.get("vm_user", ""))
        self.vm_pass = QLineEdit()
        self.vm_pass.setEchoMode(QLineEdit.Password)
        self.vm_pass.setPlaceholderText("Stored in Windows Credential Manager")
        self.revert = QCheckBox("Revert to clean snapshot after each run (disposable)")
        self.revert.setChecked(cfg.get("revert_after", True))
        f.addRow("Name", self.name)
        f.addRow("Isolation level", self.level)
        f.addRow(self.desc)
        f.addRow("Timeout", self.timeout)
        f.addRow("CPU limit", self.cpu)
        f.addRow("Memory limit", self.mem)
        f.addRow("Max processes", self.procs)
        f.addRow("", self.network)
        self.container_rows = [("Container image", self.image)]
        self.vm_rows = [("VM backend", self.vm_backend), ("VM name", self.vm_id), ("Guest user", self.vm_user),
                        ("Guest password", self.vm_pass), ("", self.revert)]
        for label, w in self.container_rows + self.vm_rows:
            f.addRow(label, w)
        self.form = f
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._level_changed()

    def _level_changed(self):
        lvl = self.level.currentData()
        self.desc.setText(ISOLATION_DESCRIPTIONS[lvl][1])
        for _, w in self.container_rows:
            self.form.setRowVisible(w, lvl == "container")
        for _, w in self.vm_rows:
            self.form.setRowVisible(w, lvl == "vm")

    def config(self) -> dict:
        cfg = {"timeout_s": self.timeout.value(), "cpu_limit": self.cpu.value(), "memory_mb": self.mem.value(),
               "max_processes": self.procs.value(), "allow_network": self.network.isChecked(),
               "image": self.image.text().strip() or "python:3.12-slim"}
        if self.level.currentData() == "vm":
            cfg.update(vm_backend=self.vm_backend.currentData(), vm_id=self.vm_id.text().strip(),
                       vm_user=self.vm_user.text().strip(), revert_after=self.revert.isChecked())
        return cfg


class SandboxPage(Page):
    def __init__(self, ctx):
        super().__init__("Fate Sandbox", "Safely run code, scripts and AI-generated projects with clear isolation "
                                         "levels and enforced limits.", scroll=False)
        self.ctx = ctx
        self.sid: int | None = None
        self.running = False
        self._t0 = 0.0
        new = QPushButton(" Create sandbox")
        new.setIcon(icon("plus", "#FFFFFF"))
        new.setObjectName("Primary")
        new.clicked.connect(self.create)
        estop = QPushButton(" Emergency stop")
        estop.setIcon(icon("power", "#FCA5A5"))
        estop.setObjectName("Danger")
        estop.clicked.connect(self.emergency)
        self.header_actions.addWidget(estop)
        self.header_actions.addWidget(new)

        row = QHBoxLayout()
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setFixedWidth(250)
        self.list.currentItemChanged.connect(self._select)
        left.addWidget(self.list, 1)
        self.files = QListWidget()
        self.files.setFixedWidth(250)
        lab = QLabel("Files")
        lab.setObjectName("Muted")
        left.addWidget(lab)
        left.addWidget(self.files, 1)
        row.addLayout(left)

        right = QVBoxLayout()
        top = QHBoxLayout()
        self.title = QLabel("No sandbox selected")
        self.title.setObjectName("H2")
        self.level_badge = Badge("")
        top.addWidget(self.title)
        top.addWidget(self.level_badge)
        top.addStretch(1)
        right.addLayout(top)
        top = QHBoxLayout()
        self.btns = {}
        for key, label in (("import", "Import project"), ("importfile", "Import file"), ("settings", "Settings"),
                           ("reset", "Reset"), ("export", "Export results"), ("open", "Open folder"),
                           ("delete", "Delete")):
            b = QPushButton(label)
            if key == "delete":
                b.setObjectName("Danger")
            b.clicked.connect(lambda _=False, k=key: self.action(k))
            self.btns[key] = b
            top.addWidget(b)
        top.insertStretch(5, 1)
        right.addLayout(top)
        self.iso_banner = Banner("")
        right.addWidget(self.iso_banner)
        cmd_row = QHBoxLayout()
        self.cmd = QLineEdit(placeholderText="Command, e.g.  python main.py   or   python -m pytest   (runs in the "
                                             "sandbox folder)")
        self.cmd.returnPressed.connect(self.run)
        self.run_btn = QPushButton(" Run")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.clicked.connect(lambda: self.sid and self.ctx.sandboxes.stop(self.sid))
        self.stop_btn.setEnabled(False)
        cmd_row.addWidget(self.cmd, 1)
        cmd_row.addWidget(self.run_btn)
        cmd_row.addWidget(self.stop_btn)
        right.addLayout(cmd_row)
        tiles = QHBoxLayout()
        self.t_status = StatTile("Exit status")
        self.t_time = StatTile("Execution time")
        self.t_cpu = StatTile("CPU (live)")
        self.t_mem = StatTile("Memory (live/peak)")
        self.t_disk = StatTile("Sandbox disk")
        for t in (self.t_status, self.t_time, self.t_cpu, self.t_mem, self.t_disk):
            tiles.addWidget(t)
        right.addLayout(tiles)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(f"font-family: {MONO_STACK}; font-size: 12px; background:#05040A;")
        right.addWidget(self.console, 1)
        self.limits = QLabel("")
        self.limits.setObjectName("Dim")
        self.limits.setWordWrap(True)
        right.addWidget(self.limits)
        row.addLayout(right, 1)
        self.body.addLayout(row, 1)
        self.mon = QTimer(self, interval=700, timeout=self._monitor)
        self.reload()

    def on_show(self):
        self.reload()

    def reload(self, select: int | None = None):
        cur = select or self.sid
        self.list.blockSignals(True)
        self.list.clear()
        for sb in self.ctx.sandboxes.list():
            it = QListWidgetItem(f"{sb['name']}  ·  {ISOLATION_DESCRIPTIONS[sb['level']][0].split('—')[0].strip()}")
            it.setData(Qt.UserRole, sb["id"])
            self.list.addItem(it)
            if sb["id"] == cur:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        if self.list.currentItem():
            self._select()
        else:
            self.sid = None
            for b in self.btns.values():
                b.setEnabled(False)
            self.run_btn.setEnabled(False)
            self.iso_banner.setText("Create a sandbox to get started. Level 2 (container) is recommended for "
                                    "untrusted code.")

    def _select(self, *_):
        it = self.list.currentItem()
        if not it:
            return
        self.sid = it.data(Qt.UserRole)
        sb = self.ctx.sandboxes.get(self.sid)
        self.title.setText(sb["name"])
        lvl = sb["level"]
        self.level_badge.set(ISOLATION_DESCRIPTIONS[lvl][0], {"process": "warn", "container": "ok", "vm": "ok"}[lvl])
        self.iso_banner.setText(ISOLATION_DESCRIPTIONS[lvl][1])
        for b in self.btns.values():
            b.setEnabled(not self.running)
        self.run_btn.setEnabled(not self.running)
        c = sb["config"]
        self.limits.setText(f"Limits: timeout {c.get('timeout_s')}s · CPU {c.get('cpu_limit')} cores · memory "
                            f"{c.get('memory_mb')} MB · ≤{c.get('max_processes', 64)} processes · network "
                            f"{'allowed' if c.get('allow_network') else 'blocked' if lvl != 'process' else 'not blocked (Level 1)'}")
        self._refresh_files()
        runs = self.ctx.sandboxes.runs.list(self.sid)
        if runs and not self.running:
            r = runs[0]
            self.console.setPlainText(f"$ {r['command']}\n{r['stdout']}{r['stderr']}\n[exit {r['exit_code']}]")
            self.t_status.set(str(r["exit_code"]), "timed out" if r["timed_out"] else "last run")
            self.t_time.set(f"{r['duration_ms'] / 1000:.2f}s")
        elif not self.running:
            self.console.clear()
            self.t_status.set("—", "")
            self.t_time.set("—")

    def _refresh_files(self):
        if not self.sid:
            return
        files = self.ctx.sandboxes.files(self.sid)
        self.files.clear()
        self.files.addItems(files[:2000])
        wd = Path(self.ctx.sandboxes.get(self.sid)["workdir"])
        size = sum(p.stat().st_size for p in wd.rglob("*") if p.is_file())
        from ..components.widgets import fmt_bytes
        self.t_disk.set(fmt_bytes(size), f"{len(files)} files")

    def create(self):
        d = NewSandboxDialog(self.ctx, self)
        if d.exec():
            name = d.name.text().strip() or "sandbox"
            try:
                sb = self.ctx.sandboxes.create(name, d.level.currentData(), d.config())
                if d.level.currentData() == "vm" and d.vm_pass.text():
                    self.ctx.credentials.set_api_key(f"sandbox-vm-{sb['id']}", d.vm_pass.text())
            except Exception as e:
                error(self, str(e))
                return
            self.reload(sb["id"])

    def action(self, key):
        if not self.sid:
            return
        sb = self.ctx.sandboxes.get(self.sid)
        if key == "import":
            p = QFileDialog.getExistingDirectory(self, "Import project folder (copied into the sandbox)")
            if p:
                n = self.ctx.sandboxes.import_project(self.sid, Path(p))
                self.console.appendPlainText(f"[FATE] Imported {Path(p).name} — {n} files in sandbox.")
        elif key == "importfile":
            p, _ = QFileDialog.getOpenFileName(self, "Import file")
            if p:
                self.ctx.sandboxes.import_project(self.sid, Path(p))
        elif key == "settings":
            d = NewSandboxDialog(self.ctx, self, existing=sb)
            if d.exec():
                self.ctx.sandboxes.update_config(self.sid, **d.config())
                if d.vm_pass.text():
                    self.ctx.credentials.set_api_key(f"sandbox-vm-{self.sid}", d.vm_pass.text())
        elif key == "reset":
            if confirm(self, "Reset sandbox", "Delete all files in this sandbox" +
                       (" and revert the VM to its clean snapshot" if sb["level"] == "vm" else "") + "?", danger=True):
                run_async(self.ctx.sandboxes.reset, self.sid, on_done=lambda _: self._select(),
                          on_error=lambda e: error(self, str(e)))
        elif key == "export":
            p, _ = QFileDialog.getSaveFileName(self, "Export results", str(self.ctx.paths.exports / f"{sb['name']}.zip"),
                                               "Zip (*.zip)")
            if p:
                self.ctx.sandboxes.export_results(self.sid, Path(p))
                self.console.appendPlainText(f"[FATE] Exported to {p}")
        elif key == "open":
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(sb["workdir"]))
        elif key == "delete":
            if confirm(self, "Delete sandbox", f"Delete sandbox '{sb['name']}' and all its files?", danger=True):
                self.ctx.sandboxes.delete(self.sid)
                self.ctx.credentials.delete_api_key(f"sandbox-vm-{self.sid}")
                self.sid = None
                self.reload()
        self._refresh_files()

    def run(self):
        if not self.sid or self.running:
            return
        cmd = self.cmd.text().strip()
        if not cmd:
            return
        sb = self.ctx.sandboxes.get(self.sid)
        consent = False
        if sb["level"] == "process":
            consent = confirm(self, "Run on this PC?",
                              "Level 1 runs the command directly on your PC with limits but WITHOUT a security "
                              "boundary: it can read your files and use the network.\n\nOnly continue for code you "
                              "trust. Use a container sandbox for untrusted code.\n\nRun now?", danger=True)
            if not consent:
                return
        self.running = True
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        for b in self.btns.values():
            b.setEnabled(False)
        self.console.setPlainText(f"$ {cmd}\n")
        self.t_status.set("running", "")
        self._t0 = time.perf_counter()
        self._peak = 0.0
        self.mon.start()
        sid = self.sid

        def work(progress):
            return self.ctx.sandboxes.run(sid, cmd, on_output=lambda s, t: progress(t), host_consent=consent)

        run_async(work, on_progress=self._out, on_done=self._done, on_error=self._fail)

    def _out(self, text):
        self.console.moveCursor(self.console.textCursor().MoveOperation.End)
        self.console.insertPlainText(text)
        self.console.ensureCursorVisible()

    def _end(self):
        self.running = False
        self.mon.stop()
        self.stop_btn.setEnabled(False)
        self.run_btn.setEnabled(True)
        for b in self.btns.values():
            b.setEnabled(True)
        self._refresh_files()

    def _done(self, res):
        self._end()
        tail = []
        if res.timed_out:
            tail.append("timed out — process tree killed")
        if res.killed:
            tail.append("stopped by user")
        if res.truncated:
            tail.append("output truncated")
        self.console.appendPlainText(f"\n[exit {res.exit_code}] {' · '.join(tail)}")
        self.t_status.set(str(res.exit_code), "success" if res.ok else "failed")
        self.t_time.set(f"{res.duration_ms / 1000:.2f}s")
        if res.peak_memory_mb:
            self.t_mem.set(f"{res.peak_memory_mb:.0f} MB", "peak (job object)")
        self.limits.setText("Enforced: " + ", ".join(res.enforced) +
                            ("<br>Not enforced at this level: " + ", ".join(res.not_enforced) if res.not_enforced else ""))
        self.limits.setTextFormat(Qt.RichText)

    def _fail(self, e):
        self._end()
        self.t_status.set("error")
        self.console.appendPlainText(f"\n[FATE] {e}")

    def _monitor(self):
        self.t_time.set(f"{time.perf_counter() - self._t0:.1f}s")
        try:
            me = psutil.Process()
            cpu = mem = 0.0
            for c in me.children(recursive=True):
                try:
                    cpu += c.cpu_percent(None)
                    mem += c.memory_info().rss / 2 ** 20
                except psutil.Error:
                    pass
            self._peak = max(self._peak, mem)
            self.t_cpu.set(f"{cpu:.0f}%", "of one core = 100%")
            self.t_mem.set(f"{mem:.0f} MB", f"peak {self._peak:.0f} MB (host view)")
        except psutil.Error:
            pass

    def emergency(self):
        self.ctx.sandboxes.stop_all()
        self.console.appendPlainText("\n[FATE] Emergency stop issued to all running sandboxes.")
