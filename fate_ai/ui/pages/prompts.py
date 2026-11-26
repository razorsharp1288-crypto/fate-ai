from __future__ import annotations

import json
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from ..components.widgets import Card, Page, confirm, error, hbox, info

VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][\w]*)\s*\}\}")
CATEGORIES = ["Coding", "Research", "Business", "Writing", "Development", "Automation", "Image generation", "General"]


def fill_variables(body: str, values: dict[str, str]) -> str:
    return VAR_RE.sub(lambda m: values.get(m.group(1), m.group(0)), body)


class PromptsPage(Page):
    def __init__(self, ctx, use_in_chat=None):
        super().__init__("Prompt Library", "Reusable prompts with {{variables}}, categories, tags and favourites.",
                         scroll=False)
        self.ctx = ctx
        self.use_in_chat = use_in_chat
        self.pid = None
        for label, fn in (("Import", self.import_), ("Export", self.export)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            self.header_actions.addWidget(b)
        newb = QPushButton("+ New prompt")
        newb.setObjectName("Primary")
        newb.clicked.connect(self.new)
        self.header_actions.addWidget(newb)

        row = QHBoxLayout()
        left = QVBoxLayout()
        self.search = QLineEdit(placeholderText="Search prompts, tags…")
        self.search.textChanged.connect(self.reload)
        self.cat = QComboBox()
        self.cat.addItem("All categories", "")
        for c in CATEGORIES:
            self.cat.addItem(c, c)
        self.cat.currentIndexChanged.connect(self.reload)
        self.fav_only = QCheckBox("★ Favourites")
        self.fav_only.toggled.connect(self.reload)
        left.addWidget(self.search)
        left.addLayout(hbox(self.cat, self.fav_only))
        self.list = QListWidget()
        self.list.setFixedWidth(320)
        self.list.currentItemChanged.connect(self._select)
        left.addWidget(self.list, 1)
        row.addLayout(left)

        ed = Card()
        f = QFormLayout()
        self.title = QLineEdit()
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(CATEGORIES)
        self.tags = QLineEdit(placeholderText="comma,separated,tags")
        self.fav = QCheckBox("Favourite")
        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText("Prompt text. Use {{variable}} placeholders.")
        f.addRow("Title", self.title)
        f.addRow("Category", self.category)
        f.addRow("Tags", self.tags)
        f.addRow("", self.fav)
        ed.add(f)
        ed.add(self.body_edit)
        self.vars_label = QLabel("")
        self.vars_label.setObjectName("Dim")
        ed.add(self.vars_label)
        self.body_edit.textChanged.connect(self._vars)
        save = QPushButton("Save")
        save.setObjectName("Primary")
        save.clicked.connect(self.save)
        copy = QPushButton("Copy")
        copy.clicked.connect(self.copy)
        use = QPushButton("Use in chat")
        use.clicked.connect(self.use)
        delete = QPushButton("Delete")
        delete.setObjectName("Danger")
        delete.clicked.connect(self.delete)
        self.history = QLabel("")
        self.history.setObjectName("Dim")
        ed.add(hbox(save, copy, use, None, self.history, delete))
        row.addWidget(ed, 1)
        self.body.addLayout(row, 1)
        self.reload()

    def reload(self, *_):
        cur = self.pid
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.ctx.prompts.list(self.search.text().strip(), self.cat.currentData() or "",
                                       self.fav_only.isChecked()):
            it = QListWidgetItem(("★ " if p["favorite"] else "") + p["title"] + f"   ·  {p['category']}")
            it.setData(Qt.UserRole, p["id"])
            self.list.addItem(it)
            if p["id"] == cur:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _select(self, cur, _=None):
        if not cur:
            return
        p = self.ctx.prompts.get(cur.data(Qt.UserRole))
        self.pid = p["id"]
        self.title.setText(p["title"])
        self.category.setCurrentText(p["category"])
        self.tags.setText(p["tags"])
        self.fav.setChecked(bool(p["favorite"]))
        self.body_edit.setPlainText(p["body"])
        self.history.setText(f"Used {p['use_count']}× · updated {p['updated_at']}")

    def _vars(self):
        v = sorted(set(VAR_RE.findall(self.body_edit.toPlainText())))
        self.vars_label.setText("Variables: " + ", ".join(v) if v else "")

    def new(self):
        self.pid = None
        self.list.clearSelection()
        for w in (self.title, self.tags):
            w.clear()
        self.body_edit.clear()
        self.fav.setChecked(False)
        self.title.setFocus()

    def save(self):
        t, b = self.title.text().strip(), self.body_edit.toPlainText()
        if not t or not b.strip():
            error(self, "Title and prompt text are required.")
            return
        fields = dict(title=t, body=b, category=self.category.currentText().strip() or "General",
                      tags=self.tags.text().strip(), favorite=int(self.fav.isChecked()))
        if self.pid:
            self.ctx.prompts.update(self.pid, **fields)
        else:
            self.pid = self.ctx.prompts.create(**fields)
        self.reload()

    def delete(self):
        if self.pid and confirm(self, "Delete prompt", "Delete this prompt?", danger=True):
            self.ctx.prompts.delete(self.pid)
            self.new()
            self.reload()

    def _filled(self) -> str | None:
        body = self.body_edit.toPlainText()
        names = sorted(set(VAR_RE.findall(body)))
        if not names:
            return body
        d = QDialog(self)
        d.setWindowTitle("Fill variables")
        f = QFormLayout(d)
        edits = {}
        for n in names:
            edits[n] = QPlainTextEdit()
            edits[n].setFixedHeight(60)
            f.addRow(n, edits[n])
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if not d.exec():
            return None
        return fill_variables(body, {k: e.toPlainText() for k, e in edits.items()})

    def copy(self):
        text = self._filled()
        if text is not None:
            QGuiApplication.clipboard().setText(text)
            if self.pid:
                self.ctx.prompts.mark_used(self.pid)

    def use(self):
        text = self._filled()
        if text is not None and self.use_in_chat:
            if self.pid:
                self.ctx.prompts.mark_used(self.pid)
            self.use_in_chat(text)

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export prompts", str(self.ctx.paths.exports / "prompts.json"),
                                              "JSON (*.json)")
        if path:
            data = [{k: p[k] for k in ("title", "body", "category", "tags", "favorite")} for p in self.ctx.prompts.list()]
            Path(path).write_text(json.dumps({"format": "fate-ai-prompts", "prompts": data}, indent=2), "utf-8")
            info(self, f"Exported {len(data)} prompts.")

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import prompts", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text("utf-8"))
            items = data["prompts"] if isinstance(data, dict) else data
            n = 0
            for p in items:
                if p.get("title") and p.get("body"):
                    self.ctx.prompts.create(str(p["title"])[:200], str(p["body"]), str(p.get("category", "General")),
                                            str(p.get("tags", "")), bool(p.get("favorite")))
                    n += 1
        except Exception as e:
            error(self, f"Import failed: {e}")
            return
        self.reload()
        info(self, f"Imported {n} prompts.")
