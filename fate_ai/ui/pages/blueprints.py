from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ...blueprints.generator import generate, spec_markdown, template_spec
from ...blueprints.geometry import SHAPES, Part, mirror_x
from ...blueprints.service import BlueprintService
from ...blueprints.templates import BY_ID as TEMPLATES, TEMPLATES as TEMPLATE_LIST, build, match_template
from ...core.task_manager import CancelToken
from ..components.markdown_view import render
from ..components.viewer3d import Viewer3D
from ..components.widgets import Banner, Page, confirm, error, hbox, info
from ..components.worker import run_async
from ..themes import chat_css

IDEAS = ["An Iron Man–style armor suit with chest reactor and flight thrusters",
         "A foldable delivery drone with 6 arms", "A desktop robot arm that can sort LEGO bricks",
         "A Mars rover for a science fair", "A 4 m tall cargo-loader mech", "A tiny off-grid cabin"]


class ColorButton(QPushButton):
    def __init__(self, color: str):
        super().__init__()
        self.setFixedWidth(46)
        self.set(color)
        self.clicked.connect(self._pick)

    def set(self, c: str):
        self.color = c
        self.setStyleSheet(f"background:{c}; border-radius:6px; min-height:22px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Choose colour")
        if c.isValid():
            self.set(c.name())


class BlueprintsPage(Page):
    def __init__(self, ctx):
        super().__init__("Blueprints", "Describe anything you want to create — a suit of armor, a drone, a robot, a "
                                       "vehicle — and FATE AI drafts a design spec and an auto-generated 3D model "
                                       "you can export to STL/OBJ.", scroll=False)
        self.ctx = ctx
        self.svc = BlueprintService(ctx.db, ctx.audit)
        self.bid: int | None = None
        self.parts: list[Part] = []
        self.spec: dict = {}
        self.cancel: CancelToken | None = None
        new = QPushButton("+ New blueprint")
        new.setObjectName("Primary")
        new.clicked.connect(self.new)
        imp = QPushButton("Import")
        imp.clicked.connect(self.import_file)
        exp = QPushButton("Export ▾")
        m = QMenu(exp)
        m.addAction("3D model — STL (3D printing, mm)", lambda: self.export("stl"))
        m.addAction("3D model — OBJ + MTL (Blender, colours)", lambda: self.export("obj"))
        m.addAction("Spec — Markdown", lambda: self.export("md"))
        m.addAction("Screenshot — PNG", lambda: self.export("png"))
        m.addAction("Blueprint file (.fateblueprint)", lambda: self.export("fate"))
        exp.setMenu(m)
        for b in (imp, exp, new):
            self.header_actions.addWidget(b)

        split = QSplitter()
        self.body.addWidget(split, 1)

        # left: library
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit(placeholderText="Search blueprints…")
        self.search.textChanged.connect(lambda: self.reload())
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._select)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        ll.addWidget(self.search)
        ll.addWidget(self.list, 1)
        left.setMinimumWidth(200)
        left.setMaximumWidth(320)
        split.addWidget(left)

        # centre: viewport
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("No blueprint selected")
        self.title.setObjectName("H2")
        bar = QHBoxLayout()
        bar.addWidget(self.title, 1)
        for v in ("Front", "Side", "Top", "Iso"):
            b = QPushButton(v)
            b.setObjectName("Ghost")
            b.clicked.connect(lambda _=False, v=v: self.viewer.set_view(v.lower()))
            bar.addWidget(b)
        self.spin = QCheckBox("Spin")
        self.wire = QCheckBox("Wireframe")
        self.grid_cb = QCheckBox("Grid")
        self.grid_cb.setChecked(True)
        for cb in (self.spin, self.wire, self.grid_cb):
            bar.addWidget(cb)
        ml.addLayout(bar)
        self.viewer = Viewer3D()
        self.viewer.partClicked.connect(self._part_clicked)
        self.spin.toggled.connect(self.viewer.set_auto_rotate)
        self.wire.toggled.connect(lambda on: (setattr(self.viewer, "wireframe", on), self.viewer.update()))
        self.grid_cb.toggled.connect(lambda on: (setattr(self.viewer, "show_grid", on), self.viewer.update()))
        ml.addWidget(self.viewer, 1)
        self.status = QLabel("")
        self.status.setObjectName("Dim")
        self.status.setWordWrap(True)
        ml.addWidget(self.status)
        split.addWidget(mid)

        # right: tabs
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(380)
        self.tabs.addTab(self._create_tab(), "Create")
        self.spec_view = QTextBrowser()
        self.spec_view.setOpenExternalLinks(True)
        self.spec_view.document().setDefaultStyleSheet(chat_css())
        self.tabs.addTab(self.spec_view, "Spec")
        self.tabs.addTab(self._parts_tab(), "Parts")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Your notes, measurements, ideas…")
        self.notes.textChanged.connect(self._save_notes)
        self.tabs.addTab(self.notes, "Notes")
        split.addWidget(self.tabs)
        split.setSizes([220, 760, 420])
        split.setStretchFactor(1, 1)
        self.reload()

    # ------------------------------------------------------------------ tabs
    def _create_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Describe what you want to create</b>"))
        self.idea = QPlainTextEdit()
        self.idea.setPlaceholderText("e.g. " + IDEAS[0])
        self.idea.setFixedHeight(90)
        lay.addWidget(self.idea)
        ideas = QComboBox()
        ideas.addItem("Need inspiration?")
        ideas.addItems(IDEAS)
        ideas.activated.connect(lambda i: i and self.idea.setPlainText(IDEAS[i - 1]))
        lay.addWidget(ideas)

        lay.addWidget(QLabel("<b>Generate with AI</b> — full spec + 3D model"))
        self.provider = QComboBox()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.provider.currentIndexChanged.connect(self._load_models)
        lay.addLayout(hbox(self.provider, self.model))
        self.gen_btn = QPushButton("✦ Generate with AI")
        self.gen_btn.setObjectName("Primary")
        self.gen_btn.clicked.connect(self.generate_ai)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(lambda: self.cancel and self.cancel.cancel())
        lay.addLayout(hbox(self.gen_btn, self.stop_btn))
        self.revision = QLineEdit(placeholderText="Revise: e.g. make it gold, add shoulder missiles as props, taller")
        rev = QPushButton("Revise with AI")
        rev.clicked.connect(self.revise_ai)
        lay.addLayout(hbox(self.revision, rev))

        lay.addWidget(QLabel("<b>Auto 3D (offline)</b> — instant model from a built-in generator"))
        self.template = QComboBox()
        self.template.addItem("Auto-detect from description", "")
        for t in TEMPLATE_LIST:
            self.template.addItem(t.name, t.id)
        self.template.currentIndexChanged.connect(self._template_params)
        lay.addWidget(self.template)
        self.param_form = QFormLayout()
        lay.addLayout(self.param_form)
        self.c1 = ColorButton("#B91C1C")
        self.c2 = ColorButton("#D4A017")
        self.c3 = ColorButton("#7DD3FC")
        lay.addLayout(hbox(QLabel("Colours"), self.c1, self.c2, self.c3, None))
        auto = QPushButton("⚡ Auto 3D")
        auto.clicked.connect(self.auto_3d)
        lay.addWidget(auto)
        lay.addWidget(Banner("Blueprints are concept designs for visualisation, props, cosplay and hobby builds — "
                             "always validate real builds with proper engineering."))
        lay.addStretch(1)
        self.param_widgets: dict = {}
        self._template_params()
        return w

    def _parts_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Name", "Shape", "Position x,y,z", "Size x,y,z", "Rotation°", "Colour",
                                              "Group"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.itemSelectionChanged.connect(lambda: self.viewer.set_selected(self.table.currentRow()))
        lay.addWidget(self.table, 1)
        add = QPushButton("Add part")
        add.clicked.connect(self.add_part)
        dup = QPushButton("Duplicate")
        dup.clicked.connect(self.dup_part)
        mir = QPushButton("Mirror L↔R")
        mir.clicked.connect(self.mirror_part)
        rm = QPushButton("Delete")
        rm.setObjectName("Danger")
        rm.clicked.connect(self.delete_part)
        apply = QPushButton("Apply edits")
        apply.setObjectName("Primary")
        apply.clicked.connect(self.apply_table)
        lay.addLayout(hbox(add, dup, mir, rm, None, apply))
        hint = QLabel(f"Shapes: {', '.join(SHAPES)} · metres · Y is up · colours as #RRGGBB")
        hint.setObjectName("Dim")
        lay.addWidget(hint)
        return w

    # ------------------------------------------------------------------ library
    def on_show(self):
        cur = self.provider.currentData()
        self.provider.blockSignals(True)
        self.provider.clear()
        for p in self.ctx.providers.configs():
            if p["enabled"]:
                self.provider.addItem(p["name"], p["id"])
        idx = self.provider.findData(cur or self.ctx.settings.settings.ai.default_provider)
        self.provider.setCurrentIndex(max(0, idx))
        self.provider.blockSignals(False)
        self._load_models()
        self.reload()

    def _load_models(self, *_):
        pid = self.provider.currentData()
        if not pid:
            return
        default = self.ctx.settings.settings.ai.default_model if pid == self.ctx.settings.settings.ai.default_provider \
            else (self.ctx.provider_repo.get(pid) or {}).get("default_model", "")
        self.model.clear()
        if default:
            self.model.addItem(default)

        def done(models):
            if self.provider.currentData() != pid:
                return
            cur = self.model.currentText()
            self.model.clear()
            self.model.addItems([m.id for m in models])
            if cur:
                self.model.setCurrentText(cur)
        run_async(lambda: self.ctx.providers.get(pid).list_models(), on_done=done, on_error=lambda e: None)

    def reload(self, select: int | None = None):
        cur = select or self.bid
        self.list.blockSignals(True)
        self.list.clear()
        for b in self.svc.list(self.search.text().strip()):
            it = QListWidgetItem(f"{b['name']}\n{b['category']}")
            it.setData(Qt.UserRole, b["id"])
            self.list.addItem(it)
            if b["id"] == cur:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        if self.list.currentItem():
            self._select()
        elif self.list.count() == 0:
            self.bid = None
            self._show(None)

    def _select(self, *_):
        it = self.list.currentItem()
        if it:
            self.bid = it.data(Qt.UserRole)
            self._show(self.svc.get(self.bid))

    def _show(self, b: dict | None):
        if not b:
            self.title.setText("No blueprint selected — click “New blueprint” or just describe an idea and generate")
            self.parts, self.spec = [], {}
            self.viewer.set_parts([])
            self.spec_view.setHtml("")
            self.table.setRowCount(0)
            return
        self.title.setText(b["name"])
        self.parts, self.spec = b["parts"], b["spec"]
        if b["prompt"] and not self.idea.toPlainText().strip():
            self.idea.setPlainText(b["prompt"])
        self.notes.blockSignals(True)
        self.notes.setPlainText(b["notes"])
        self.notes.blockSignals(False)
        self.viewer.set_parts(self.parts)
        self._fill_spec()
        self._fill_table()

    def _fill_spec(self):
        md = spec_markdown(self.spec) if self.spec else "*No spec yet — use Generate with AI.*"
        self.spec_view.setHtml(f"<style>{chat_css()}</style>{render(md)}")

    def _fmt(self, v):
        return ", ".join(f"{x:g}" for x in v)

    def _fill_table(self, select: int | None = None):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for p in self.parts:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [p.name, p.shape, self._fmt(p.position), self._fmt(p.size), self._fmt(p.rotation), p.color, p.group]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 5:
                    it.setBackground(QColor(p.color))
                    it.setForeground(QColor("#000000" if QColor(p.color).lightness() > 140 else "#FFFFFF"))
                self.table.setItem(r, c, it)
        self.table.blockSignals(False)
        if select is not None and self.parts:
            row = max(0, min(select, len(self.parts) - 1))
            self.table.selectRow(row)
            self.viewer.set_selected(row)

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        bid = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Rename", lambda: self.rename(bid))
        m.addAction("Duplicate", lambda: self.reload(self.svc.duplicate(bid)))
        m.addSeparator()
        m.addAction("Delete", lambda: self.delete(bid))
        m.exec(self.list.mapToGlobal(pos))

    def new(self):
        name, ok = QInputDialog.getText(self, "New blueprint", "Name:", text="My design")
        if ok and name.strip():
            self.bid = self.svc.create(name.strip(), prompt=self.idea.toPlainText().strip())
            self.reload(self.bid)

    def rename(self, bid):
        b = self.svc.get(bid)
        name, ok = QInputDialog.getText(self, "Rename", "Name:", text=b["name"])
        if ok and name.strip():
            self.svc.save(bid, name=name.strip())
            self.reload(bid)

    def delete(self, bid):
        if confirm(self, "Delete blueprint", "Delete this blueprint permanently?", danger=True):
            self.svc.delete(bid)
            if bid == self.bid:
                self.bid = None
            self.reload()

    def _ensure(self, name_hint: str) -> int:
        if self.bid is None:
            self.bid = self.svc.create(name_hint[:60] or "Untitled", prompt=self.idea.toPlainText().strip())
        return self.bid

    def _save_notes(self):
        if self.bid:
            self.svc.save(self.bid, notes=self.notes.toPlainText())

    # ------------------------------------------------------------------ generation
    def _busy(self, on: bool, msg: str = ""):
        self.gen_btn.setEnabled(not on)
        self.stop_btn.setEnabled(on)
        self.status.setText(msg)

    def generate_ai(self, revision: str = ""):
        idea = self.idea.toPlainText().strip()
        if not idea and not revision:
            error(self, "Describe what you want to create first.")
            return
        pid, model = self.provider.currentData(), self.model.currentText().strip()
        if not model:
            error(self, "Choose a model. Add any AI service on the API Keys page, or install a local model.")
            return
        existing = None
        if revision:
            existing = dict(self.spec, parts=[p.to_dict() for p in self.parts])
        self.cancel = CancelToken()
        tok = self.cancel
        self._busy(True, f"Designing with {model}…")
        received = [0]

        def work(progress):
            return generate(self.ctx.providers, pid, model, idea, existing, revision, cancel=tok,
                            on_token=lambda t: progress(len(t)))

        def prog(n):
            received[0] += n
            self.status.setText(f"Designing with {model}… {received[0]:,} characters received")

        def done(result):
            spec, parts = result
            bid = self._ensure(spec.get("title") or idea)
            self.svc.save(bid, name=spec.get("title") or idea[:60], category=spec.get("category", "General"),
                          prompt=idea, spec=spec, parts=parts)
            self._busy(False, f"✓ Generated {len(parts)} parts with {model}.")
            self.reload(bid)
            self.tabs.setCurrentIndex(1)

        def fail(e):
            self._busy(False, f"Generation failed: {e}")
            if not tok.cancelled:
                error(self, f"{e}\n\nTip: larger models produce better blueprints. You can always use Auto 3D "
                            f"(offline) instead.", "Blueprint generation failed")
        run_async(work, on_progress=prog, on_done=done, on_error=fail)

    def revise_ai(self):
        if not self.parts:
            error(self, "Generate a blueprint first, then revise it.")
            return
        r = self.revision.text().strip()
        if r:
            self.generate_ai(revision=r)

    def _template_params(self, *_):
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self.param_widgets = {}
        tid = self.template.currentData() or match_template(self.idea.toPlainText()).id
        tpl = TEMPLATES[tid]
        for k, (default, lo, hi, label) in tpl.params.items():
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setDecimals(0 if isinstance(default, int) else 2)
            sb.setSingleStep(1 if isinstance(default, int) else 0.05)
            sb.setValue(default)
            self.param_widgets[k] = (sb, type(default))
            self.param_form.addRow(label, sb)

    def auto_3d(self):
        idea = self.idea.toPlainText().strip()
        tid = self.template.currentData() or match_template(idea).id
        tpl = TEMPLATES[tid]
        if not self.template.currentData():
            self._template_params()
        params = {k: t(sb.value()) for k, (sb, t) in self.param_widgets.items() if k in tpl.params}
        colours = {"primary": self.c1.color, "secondary": self.c2.color, "glow": self.c3.color,
                   "color": self.c1.color, "body": self.c1.color, "accent": self.c2.color}
        parts = build(tid, **params, **colours)
        spec = template_spec(tpl, parts, idea or tpl.name, params)
        bid = self._ensure(idea or tpl.name)
        b = self.svc.get(bid)
        keep_spec = b["spec"] if b["spec"].get("build_steps") else spec
        self.svc.save(bid, parts=parts, spec=keep_spec, prompt=idea,
                      name=b["name"] if b["name"] != "Untitled" else (idea[:60] or tpl.name),
                      category=keep_spec.get("category", tpl.name))
        self.status.setText(f"⚡ Auto 3D: {tpl.name} — {len(parts)} parts, built offline.")
        self.reload(bid)

    # ------------------------------------------------------------------ parts editing
    def _part_clicked(self, i: int):
        if i >= 0:
            self.table.selectRow(i)
            self.tabs.setCurrentIndex(2)
            p = self.parts[i]
            self.status.setText(f"Selected: {p.name} ({p.shape}) — size {self._fmt(p.size)} m")

    def apply_table(self):
        parts = []
        for r in range(self.table.rowCount()):
            def cell(c):
                it = self.table.item(r, c)
                return it.text() if it else ""

            def vec(c):
                return [x.strip() for x in cell(c).split(",")]
            parts.append({"name": cell(0), "shape": cell(1), "position": vec(2), "size": vec(3),
                          "rotation": vec(4), "color": cell(5), "group": cell(6)})
        from ...blueprints.geometry import sanitize
        self.parts = sanitize(parts)
        self._commit(self.table.currentRow() if self.table.currentRow() >= 0 else None)

    def _commit(self, select: int | None = None):
        if self.bid is None:
            self._ensure("Untitled")
        self.svc.save(self.bid, parts=self.parts)
        self.viewer.set_parts(self.parts, frame=False)
        self._fill_table(select)

    def add_part(self):
        self.parts.append(Part(f"Part {len(self.parts) + 1}", "box", [0, 0.25, 0], [0.5, 0.5, 0.5]))
        self._commit(len(self.parts) - 1)

    def _row(self):
        r = self.table.currentRow()
        return r if 0 <= r < len(self.parts) else None

    def dup_part(self):
        r = self._row()
        if r is not None:
            p = self.parts[r]
            self.parts.append(Part(p.name + " copy", p.shape, [p.position[0] + 0.1, *p.position[1:]], list(p.size),
                                   list(p.rotation), p.color, p.material, p.group))
            self._commit(len(self.parts) - 1)

    def mirror_part(self):
        r = self._row()
        if r is not None:
            self.parts += mirror_x([self.parts[r]])
            self._commit(len(self.parts) - 1)

    def delete_part(self):
        r = self._row()
        if r is not None:
            del self.parts[r]
            self.viewer.set_selected(-1)
            self._commit(r if self.parts else None)

    # ------------------------------------------------------------------ import/export
    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import blueprint", "", "FATE blueprint (*.fateblueprint *.json)")
        if path:
            try:
                self.reload(self.svc.import_file(Path(path)))
            except Exception as e:
                error(self, str(e))

    def export(self, kind: str):
        if not self.bid:
            error(self, "Select a blueprint first.")
            return
        b = self.svc.get(self.bid)
        stem = "".join(c if c.isalnum() or c in " -_" else "_" for c in b["name"]).strip() or "blueprint"
        ext = {"stl": "STL (*.stl)", "obj": "OBJ (*.obj)", "md": "Markdown (*.md)", "png": "PNG (*.png)",
               "fate": "FATE blueprint (*.fateblueprint)"}[kind]
        suffix = {"fate": "fateblueprint"}.get(kind, kind)
        path, _ = QFileDialog.getSaveFileName(self, "Export", str(self.ctx.paths.exports / f"{stem}.{suffix}"), ext)
        if not path:
            return
        try:
            if kind == "stl":
                n = self.svc.export_stl(self.bid, Path(path))
                info(self, f"Exported {n:,} triangles to {path}\nUnits: millimetres, Z-up (ready for slicers).")
            elif kind == "obj":
                self.svc.export_obj(self.bid, Path(path))
                info(self, f"Exported {path} (+ .mtl with colours). Units: metres, Y-up.")
            elif kind == "md":
                self.svc.export_markdown(self.bid, Path(path))
            elif kind == "png":
                self.viewer.grab().save(path)
            else:
                self.svc.export_file(self.bid, Path(path))
            self.status.setText(f"Exported {path}")
        except Exception as e:
            error(self, str(e))
