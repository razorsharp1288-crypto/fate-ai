from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout)

from ...security.permissions import Capability
from ..components.widgets import confirm, error, hbox


class AgentsDialog(QDialog):
    """Create and edit agents: instructions, preferred model, permissions and approved folders."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.aid = None
        self.setWindowTitle("Agents")
        self.resize(860, 560)
        row = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setFixedWidth(220)
        self.list.currentItemChanged.connect(self._select)
        new = QPushButton("+ New agent")
        new.clicked.connect(self.new)
        left.addWidget(self.list, 1)
        left.addWidget(new)
        row.addLayout(left)
        f = QFormLayout()
        self.name = QLineEdit()
        self.instructions = QPlainTextEdit()
        self.provider = QComboBox()
        self.provider.addItem("(default)", "")
        for p in ctx.providers.configs():
            self.provider.addItem(p["name"], p["id"])
        self.model = QLineEdit(placeholderText="(default model)")
        self.caps = {c: QCheckBox(c.value.replace("_", " ").title()) for c in Capability}
        self.paths = QListWidget()
        self.paths.setMaximumHeight(90)
        addp = QPushButton("Add folder")
        addp.clicked.connect(self._add_path)
        rmp = QPushButton("Remove")
        rmp.clicked.connect(lambda: self.paths.takeItem(self.paths.currentRow()))
        f.addRow("Name", self.name)
        f.addRow("Instructions", self.instructions)
        f.addRow("Preferred provider", self.provider)
        f.addRow("Preferred model", self.model)
        caps = QVBoxLayout()
        for cb in self.caps.values():
            caps.addWidget(cb)
        f.addRow("Permissions", caps)
        f.addRow("Approved folders", self.paths)
        f.addRow("", hbox(addp, rmp, None))
        save = QPushButton("Save")
        save.setObjectName("Primary")
        save.clicked.connect(self.save)
        delete = QPushButton("Delete")
        delete.setObjectName("Danger")
        delete.clicked.connect(self.delete)
        f.addRow(hbox(save, None, delete))
        row.addLayout(f, 1)
        self.reload()

    def reload(self):
        self.list.clear()
        for a in self.ctx.agents.list():
            it = QListWidgetItem(a["name"])
            it.setData(Qt.UserRole, a["id"])
            self.list.addItem(it)
            if a["id"] == self.aid:
                self.list.setCurrentItem(it)

    def _select(self, cur, _=None):
        if not cur:
            return
        a = self.ctx.agents.repo.get(cur.data(Qt.UserRole))
        self.aid = a["id"]
        self.name.setText(a["name"])
        self.instructions.setPlainText(a["instructions"])
        self.provider.setCurrentIndex(max(0, self.provider.findData(a["provider"])))
        self.model.setText(a["model"])
        for c, cb in self.caps.items():
            cb.setChecked(bool(a["permissions"].get(c.value)))
        self.paths.clear()
        self.paths.addItems(a["allowed_paths"])

    def new(self):
        self.aid = None
        self.list.clearSelection()
        self.name.clear()
        self.instructions.clear()
        self.model.clear()
        self.paths.clear()
        for cb in self.caps.values():
            cb.setChecked(False)

    def _add_path(self):
        d = QFileDialog.getExistingDirectory(self, "Approve folder for this agent")
        if d:
            self.paths.addItem(d)

    def save(self):
        name = self.name.text().strip()
        if not name:
            error(self, "Name is required.")
            return
        fields = dict(name=name, instructions=self.instructions.toPlainText(), provider=self.provider.currentData(),
                      model=self.model.text().strip(), permissions={c.value: cb.isChecked() for c, cb in self.caps.items()},
                      allowed_paths=[self.paths.item(i).text() for i in range(self.paths.count())])
        try:
            if self.aid:
                self.ctx.agents.repo.update(self.aid, **fields)
            else:
                self.aid = self.ctx.agents.repo.create(role="custom", **fields)
        except Exception as e:
            error(self, f"Could not save: {e}")
            return
        self.ctx.audit.log("agent", "configured", f"{name}: {fields['permissions']}")
        self.reload()

    def delete(self):
        if self.aid and confirm(self, "Delete agent", "Delete this agent?", danger=True):
            self.ctx.agents.repo.delete(self.aid)
            self.new()
            self.reload()
