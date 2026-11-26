from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QPushButton, QSlider,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ...virtualization.backends.base import Cap, VMSpec
from ...virtualization.backends.virtualbox import OS_TYPES
from ...virtualization.vm_manager import host_limits, recommend
from ..components.icons import icon
from ..components.widgets import Badge, Banner, Card, Page, confirm, error, hbox, info
from ..components.worker import run_async

PRESET_ENVS = {
    "Blank VM (install from ISO)": None,
    "Python AI dev container (python:3.12-slim)": "python:3.12-slim",
    "Ubuntu 24.04 container": "ubuntu:24.04",
    "Node.js 22 container": "node:22-slim",
    "WSL2 Ubuntu": "Ubuntu",
    "WSL2 Debian": "Debian",
}


class CreateVMDialog(QDialog):
    def __init__(self, backends, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create environment")
        self.setMinimumWidth(560)
        self.backends = backends
        max_cpu, max_ram = host_limits()
        cpus, ram, disk = recommend()
        f = QFormLayout(self)
        self.backend = QComboBox()
        for b in backends:
            self.backend.addItem(f"{b.label} ({b.kind})", b.name)
        self.backend.currentIndexChanged.connect(self._backend_changed)
        self.name = QLineEdit(placeholderText="e.g. ai-dev-box")
        self.preset = QComboBox()
        self.os_type = QComboBox()
        self.os_type.addItems(list(OS_TYPES))
        self.iso = QLineEdit()
        iso_btn = QPushButton("Browse…")
        iso_btn.clicked.connect(self._browse_iso)
        self.cpus = QSpinBox()
        self.cpus.setRange(1, max_cpu)
        self.cpus.setValue(cpus)
        self.ram = QSlider(Qt.Horizontal)
        self.ram.setRange(256 // 256, max_ram // 256)
        self.ram.setValue(ram // 256)
        self.ram_label = QLabel()
        self.ram.valueChanged.connect(lambda v: self.ram_label.setText(f"{v * 256} MB"))
        self.ram.valueChanged.emit(self.ram.value())
        self.disk = QSpinBox()
        self.disk.setRange(4, 4096)
        self.disk.setValue(disk)
        self.disk.setSuffix(" GB")
        self.network = QComboBox()
        self.network.addItem("NAT (internet, isolated from LAN)", "nat")
        self.network.addItem("No network", "none")
        self.shared = QLineEdit(placeholderText="Optional host folder shared read-only")
        sh_btn = QPushButton("Browse…")
        sh_btn.clicked.connect(lambda: self.shared.setText(QFileDialog.getExistingDirectory(self, "Shared folder")))
        self.dynamic = QCheckBox("Dynamic memory (Hyper-V)")
        self.start = QCheckBox("Start after creation")
        f.addRow("Backend", self.backend)
        f.addRow("Name", self.name)
        f.addRow("Environment", self.preset)
        f.addRow("Operating system", self.os_type)
        f.addRow("ISO image", hbox(self.iso, iso_btn))
        f.addRow("vCPUs", self.cpus)
        f.addRow("RAM", hbox(self.ram, self.ram_label))
        f.addRow("Disk", self.disk)
        f.addRow("Network", self.network)
        f.addRow("Shared folder", hbox(self.shared, sh_btn))
        f.addRow("", self.dynamic)
        f.addRow("", self.start)
        self.note = QLabel(f"Limits: up to {max_cpu} vCPUs and {max_ram} MB RAM — FATE AI keeps 1 core and 2 GB for "
                           "Windows. Nothing is written to your existing partitions; disks are new files.")
        self.note.setObjectName("Dim")
        self.note.setWordWrap(True)
        f.addRow(self.note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Create")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._backend_changed()

    def _browse_iso(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select ISO", "", "Disk images (*.iso)")
        if p:
            self.iso.setText(p)

    def _backend_changed(self):
        name = self.backend.currentData()
        kind = next((b.kind for b in self.backends if b.name == name), "vm")
        self.preset.clear()
        for label, img in PRESET_ENVS.items():
            if (kind == "vm" and img is None) or (kind == "container" and img and ":" in img) or \
                    (kind == "wsl" and img and ":" not in img):
                self.preset.addItem(label, img)
        is_vm = kind == "vm"
        for w in (self.os_type, self.iso, self.disk):
            w.setEnabled(is_vm)
        self.dynamic.setEnabled(name == "hyperv")
        self.cpus.setEnabled(kind != "wsl")
        self.ram.setEnabled(kind != "wsl")

    def spec(self) -> tuple[str, VMSpec]:
        return self.backend.currentData(), VMSpec(
            name=self.name.text().strip(), os_type=self.os_type.currentText(), cpus=self.cpus.value(),
            memory_mb=self.ram.value() * 256, disk_gb=self.disk.value(), iso_path=self.iso.text().strip() or None,
            network=self.network.currentData(), shared_folder=self.shared.text().strip() or None,
            dynamic_memory=self.dynamic.isChecked(), image=self.preset.currentData(),
            start_after_create=self.start.isChecked())


class VMsPage(Page):
    def __init__(self, ctx):
        super().__init__("Virtual Machines", "Isolated environments for AI development, testing and experiments. "
                                             "FATE AI detects which technologies your PC supports.")
        self.ctx = ctx
        self.vms = []
        new = QPushButton(" New environment")
        new.setIcon(icon("plus", "#FFFFFF"))
        new.setObjectName("Primary")
        new.clicked.connect(self.create)
        stop_all = QPushButton(" Emergency stop all")
        stop_all.setIcon(icon("power", "#FCA5A5"))
        stop_all.setObjectName("Danger")
        stop_all.clicked.connect(self.stop_all)
        self.header_actions.addWidget(stop_all)
        self.header_actions.addWidget(new)

        self.backend_card = Card("Virtualization on this PC")
        self.backend_grid = QGridLayout()
        self.backend_card.add(self.backend_grid)
        self.backend_card.add(QLabel("Detecting…"))
        self.body.addWidget(self.backend_card)

        self.body.addWidget(Banner(
            "<b>GPU in VMs:</b> standard Windows VMs cannot receive a fixed share of your GPU. GPU partitioning only "
            "works with specific Hyper-V/driver combinations. Best options for AI: run inference on the host "
            "(AI Models page), use WSL2 with GPU compute, or use GPU-enabled containers. Otherwise VMs run CPU-only."))

        list_card = Card("Environments")
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Name", "Backend", "State", "OS / Image", "vCPU", "RAM",
                                              "CPU use", "Mem use"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(240)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        list_card.add(self.table)
        self.btns = {}
        for key, label in (("start", "Start"), ("stop", "Stop"), ("force", "Force stop"), ("restart", "Restart"),
                           ("pause", "Pause"), ("resume", "Resume"), ("console", "Console"),
                           ("snapshots", "Snapshots"), ("resources", "Resources"), ("clone", "Clone"),
                           ("delete", "Delete")):
            b = QPushButton(label)
            if key in ("delete", "force"):
                b.setObjectName("Danger")
            b.clicked.connect(lambda _=False, k=key: self.action(k))
            self.btns[key] = b
        list_card.add(hbox(*[self.btns[k] for k in ("start", "stop", "restart", "pause", "resume", "console")], None,
                           *[self.btns[k] for k in ("snapshots", "resources", "clone", "force", "delete")]))
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        list_card.add(self.status)
        self.body.addWidget(list_card)

        bg = Card("Background operation")
        t = QLabel("VirtualBox VMs start headless and Hyper-V/WSL/containers run independently of FATE AI, so "
                   "closing or minimising this window never stops them. Use Stop or Emergency stop to shut them "
                   "down. FATE AI never starts VMs automatically at launch.")
        t.setWordWrap(True)
        t.setObjectName("Muted")
        bg.add(t)
        self.body.addWidget(bg)
        self.body.addStretch(1)
        self.timer = QTimer(self, interval=5000, timeout=self.refresh_vms)
        self._loaded = False

    def on_show(self):
        if not self._loaded:
            self._loaded = True
            run_async(lambda: self.ctx.vm_manager.statuses(refresh=True), on_done=self._statuses)
        else:
            self.refresh_vms()
        self.timer.start()

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def _statuses(self, statuses):
        while self.backend_card.lay.count() > 2:
            w = self.backend_card.lay.takeAt(2).widget()
            if w:
                w.deleteLater()
        r = 0
        mgr = self.ctx.vm_manager
        for name, st in statuses.items():
            b = mgr.backends[name]
            title = QLabel(f"<b>{b.label}</b>")
            badge = Badge(("Available" + (f" · {st.version}" if st.version else "")) if st.available
                          else "Unavailable", "ok" if st.available else "muted")
            reason = QLabel(st.reason)
            reason.setObjectName("Muted")
            reason.setWordWrap(True)
            gpu = QLabel(b.gpu_note)
            gpu.setObjectName("Dim")
            gpu.setWordWrap(True)
            self.backend_grid.addWidget(title, r, 0)
            self.backend_grid.addWidget(badge, r, 1)
            self.backend_grid.addWidget(reason, r, 2)
            self.backend_grid.addWidget(gpu, r + 1, 2)
            r += 2
        self.backend_grid.setColumnStretch(2, 1)
        if not any(s.available for s in statuses.values()):
            self.status.setText("No virtualization backend is available. Install VirtualBox, Docker Desktop or "
                                "Podman, enable WSL2 (wsl --install), or enable Hyper-V on Windows Pro.")
        self.refresh_vms()

    def refresh_vms(self):
        run_async(self.ctx.vm_manager.list_all, on_done=self._fill, on_error=lambda e: self.status.setText(str(e)))

    def _fill(self, vms):
        sel = self._selected()
        self.vms = vms
        self.table.setRowCount(0)
        colors = {"running": Badge.COLORS["ok"], "paused": Badge.COLORS["warn"], "stopped": Badge.COLORS["muted"]}
        from PySide6.QtGui import QColor
        for v in vms:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [v.name, self.ctx.vm_manager.backends[v.backend].label, v.state, v.os_type,
                    v.cpus or "—", f"{v.memory_mb} MB" if v.memory_mb else "—",
                    f"{v.cpu_usage:.0f}%" if v.cpu_usage is not None else "—",
                    f"{v.memory_usage_mb:.0f} MB" if v.memory_usage_mb else "—"]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)
            self.table.item(r, 2).setForeground(QColor(colors.get(v.state, Badge.COLORS["muted"])))
            if sel and sel.id == v.id:
                self.table.selectRow(r)
        self._update_buttons()

    def _selected(self):
        r = self.table.currentRow()
        return self.vms[r] if 0 <= r < len(self.vms) and self.table.selectedItems() else None

    def _update_buttons(self):
        v = self._selected()
        b = self.ctx.vm_manager.backends.get(v.backend) if v else None
        need = {"start": Cap.START, "stop": Cap.STOP, "force": Cap.FORCE_STOP, "restart": Cap.STOP,
                "pause": Cap.PAUSE, "resume": Cap.PAUSE, "console": Cap.CONSOLE, "snapshots": Cap.SNAPSHOT,
                "resources": Cap.SET_RESOURCES, "clone": Cap.CLONE, "delete": Cap.DELETE}
        for k, btn in self.btns.items():
            btn.setEnabled(bool(b and b.supports(need[k])))
        if v:
            self.btns["start"].setEnabled(self.btns["start"].isEnabled() and v.state != "running")
            self.btns["stop"].setEnabled(self.btns["stop"].isEnabled() and v.state == "running")
            self.btns["resume"].setEnabled(self.btns["resume"].isEnabled() and v.state == "paused")
            self.btns["pause"].setEnabled(self.btns["pause"].isEnabled() and v.state == "running")

    def _do(self, label, fn, *args):
        self.status.setText(f"{label}…")
        run_async(fn, *args, on_done=lambda _: (self.status.setText(f"{label}: done."), self.refresh_vms()),
                  on_error=lambda e: (self.status.setText(f"{label} failed: {e}"), error(self, str(e))))

    def action(self, key):
        v = self._selected()
        if not v:
            return
        m = self.ctx.vm_manager
        if key == "start":
            self._do(f"Starting {v.name}", m.op, v.backend, "start", v.id)
        elif key == "stop":
            self._do(f"Stopping {v.name}", m.op, v.backend, "stop", v.id)
        elif key == "force":
            if confirm(self, "Force stop", f"Force-stopping {v.name} is like pulling the power cord. Unsaved data "
                                           f"in the VM will be lost. Continue?", danger=True):
                self._do(f"Force stopping {v.name}", m.op, v.backend, "stop", v.id, True)
        elif key == "restart":
            self._do(f"Restarting {v.name}", m.op, v.backend, "restart", v.id)
        elif key == "pause":
            self._do(f"Pausing {v.name}", m.op, v.backend, "pause", v.id)
        elif key == "resume":
            self._do(f"Resuming {v.name}", m.op, v.backend, "resume", v.id)
        elif key == "console":
            try:
                m.op(v.backend, "open_console", v.id)
            except Exception as e:
                error(self, str(e))
        elif key == "delete":
            if confirm(self, "Delete environment", f"Permanently delete {v.name} and its virtual disks? "
                                                   f"This cannot be undone.", danger=True):
                self._do(f"Deleting {v.name}", m.op, v.backend, "delete", v.id)
        elif key == "clone":
            name, ok = QInputDialog.getText(self, "Clone", "Name for the clone:", text=f"{v.name}-clone")
            if ok and name.strip():
                self._do(f"Cloning {v.name}", m.op, v.backend, "clone", v.id, name.strip())
        elif key == "resources":
            self.edit_resources(v)
        elif key == "snapshots":
            SnapshotDialog(self.ctx, v, self).exec()

    def edit_resources(self, v):
        b = self.ctx.vm_manager.backends[v.backend]
        if v.state == "running" and v.backend in ("virtualbox", "hyperv"):
            info(self, "Stop the VM before changing its CPU or RAM allocation.")
            return
        d = QDialog(self)
        d.setWindowTitle(f"Resources — {v.name}")
        f = QFormLayout(d)
        max_cpu, max_ram = host_limits()
        cpus = QSpinBox()
        cpus.setRange(1, max_cpu)
        cpus.setValue(v.cpus or 1)
        ram = QSpinBox()
        ram.setRange(256, max_ram)
        ram.setSingleStep(256)
        ram.setValue(v.memory_mb or 1024)
        ram.setSuffix(" MB")
        cap = QSpinBox()
        cap.setRange(1, 100)
        cap.setValue(100)
        cap.setSuffix(" %")
        f.addRow("vCPUs", cpus)
        f.addRow("RAM", ram)
        if hasattr(b, "set_cpu_limit"):
            f.addRow("CPU execution cap", cap)
        f.addRow(QLabel("Enforced by the hypervisor/container runtime."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec():
            def work():
                b.set_resources(v.id, cpus.value(), ram.value())
                if hasattr(b, "set_cpu_limit") and cap.value() < 100:
                    b.set_cpu_limit(v.id, cap.value())
            self._do("Updating resources", work)

    def create(self):
        avail = [b for b in self.ctx.vm_manager.available() if b.supports(Cap.CREATE)]
        if not avail:
            error(self, "No virtualization backend is available on this PC. See the list above for how to "
                        "enable one.", "Cannot create environment")
            return
        d = CreateVMDialog(avail, self)
        if d.exec():
            backend, spec = d.spec()
            self._do(f"Creating {spec.name}", self.ctx.vm_manager.create, backend, spec)

    def stop_all(self):
        if confirm(self, "Emergency stop", "Immediately power off ALL running VMs and FATE containers, and stop "
                                           "every sandbox? Unsaved work inside them will be lost.", danger=True):
            self.ctx.sandboxes.stop_all()
            self._do("Emergency stop", lambda: self.ctx.vm_manager.stop_all(force=True))


class SnapshotDialog(QDialog):
    def __init__(self, ctx, vm, parent=None):
        super().__init__(parent)
        self.ctx, self.vm = ctx, vm
        self.b = ctx.vm_manager.backends[vm.backend]
        self.setWindowTitle(f"Snapshots — {vm.name}")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        lay.addWidget(self.list)
        take = QPushButton("Take snapshot")
        take.setObjectName("Primary")
        restore = QPushButton("Restore")
        delete = QPushButton("Delete")
        delete.setObjectName("Danger")
        take.clicked.connect(self.take)
        restore.clicked.connect(self.restore)
        delete.clicked.connect(self.delete)
        lay.addLayout(hbox(take, restore, None, delete))
        self.msg = QLabel("")
        self.msg.setObjectName("Muted")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        if vm.backend in ("docker", "podman"):
            self.msg.setText("Container snapshots are saved as images (fate-snapshot/…). Create a new environment "
                             "from that image to restore.")
            restore.setEnabled(False)
            delete.setEnabled(False)
        self.reload()

    def reload(self):
        run_async(self.b.snapshots, self.vm.id, on_done=lambda s: (self.list.clear(),
                                                                    self.list.addItems([x.name for x in s])))

    def take(self):
        name, ok = QInputDialog.getText(self, "Snapshot", "Name:")
        if ok and name.strip():
            self.msg.setText("Taking snapshot…")
            run_async(self.b.create_snapshot, self.vm.id, name.strip(),
                      on_done=lambda _: (self.msg.setText("Snapshot created."), self.reload()),
                      on_error=lambda e: self.msg.setText(str(e)))

    def restore(self):
        it = self.list.currentItem()
        if it and confirm(self, "Restore snapshot", f"Revert {self.vm.name} to '{it.text()}'? Changes since then "
                                                    f"will be lost.", danger=True):
            self.msg.setText("Restoring…")
            run_async(self.b.restore_snapshot, self.vm.id, it.text(),
                      on_done=lambda _: self.msg.setText("Restored."), on_error=lambda e: self.msg.setText(str(e)))

    def delete(self):
        it = self.list.currentItem()
        if it and confirm(self, "Delete snapshot", f"Delete snapshot '{it.text()}'?", danger=True):
            run_async(self.b.delete_snapshot, self.vm.id, it.text(), on_done=lambda _: self.reload(),
                      on_error=lambda e: self.msg.setText(str(e)))
