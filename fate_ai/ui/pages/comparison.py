from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
                               QTextBrowser)

from ...ai.comparison import published_spec, run_one
from ...ai.providers.registry import KINDS
from ...core.task_manager import CancelToken
from ..components.markdown_view import render
from ..components.widgets import Banner, Card, Page, error, hbox
from ..components.worker import run_async
from ..themes import chat_css


class ComparisonPage(Page):
    def __init__(self, ctx):
        super().__init__("Model Comparison", "Run the same prompt against several models and compare measured "
                                             "results on your PC. Nothing here is a published benchmark.")
        self.ctx = ctx
        self.cancel = None
        self.body.addWidget(Banner("<b>Measured</b> columns are timings from this PC and your network, for this "
                                   "prompt only. <b>Published</b> columns come from provider documentation and are "
                                   "shown as “—” when unknown."))
        pick = Card("1 · Choose models")
        row = QHBoxLayout()
        self.provider = QComboBox()
        for p in ctx.providers.configs():
            self.provider.addItem(p["name"], p["id"])
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumWidth(260)
        load = QPushButton("Load models")
        load.clicked.connect(self.load_models)
        add = QPushButton("Add →")
        add.clicked.connect(self.add)
        self.selected = QListWidget()
        self.selected.setMaximumHeight(120)
        rm = QPushButton("Remove")
        rm.clicked.connect(lambda: self.selected.takeItem(self.selected.currentRow()))
        row.addWidget(self.provider)
        row.addWidget(self.model)
        row.addWidget(load)
        row.addWidget(add)
        pick.add(row)
        pick.add(hbox(self.selected, rm))
        self.body.addWidget(pick)

        pr = Card("2 · Prompt")
        self.prompt = QPlainTextEdit("Explain the difference between a process and a thread in three sentences.")
        self.prompt.setFixedHeight(90)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(16, 8192)
        self.max_tokens.setValue(400)
        self.expected = QLineEdit(placeholderText="Optional quality check: text the answer must contain")
        self.run_btn = QPushButton("Run comparison")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run)
        stop = QPushButton("Stop")
        stop.clicked.connect(lambda: self.cancel and self.cancel.cancel())
        pr.add(self.prompt)
        pr.add(hbox(QLabel("Max tokens"), self.max_tokens, self.expected, self.run_btn, stop))
        self.body.addWidget(pr)

        tabs = QTabWidget()
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["Provider", "Model", "Status", "Total time", "First token",
                                              "Output tokens", "Tokens/s", "Quality check", "Published context",
                                              "Modalities", "Tool calling"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(220)
        self.table.currentCellChanged.connect(lambda r, *_: self._show_output(r))
        tabs.addTab(self.table, "Results")
        self.output = QTextBrowser()
        self.output.document().setDefaultStyleSheet(chat_css())
        tabs.addTab(self.output, "Response")
        self.history = QTableWidget(0, 7)
        self.history.setHorizontalHeaderLabels(["When", "Provider", "Model", "OK", "Latency ms", "First token ms",
                                                "Tokens/s"])
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history.verticalHeader().hide()
        tabs.addTab(self.history, "History")
        tabs.setMinimumHeight(360)
        self.body.addWidget(tabs)
        self.results = []

    def on_show(self):
        self._history()

    def load_models(self):
        pid = self.provider.currentData()
        run_async(lambda: [m.id for m in self.ctx.providers.get(pid).list_models()],
                  on_done=lambda ids: (self.model.clear(), self.model.addItems(ids)),
                  on_error=lambda e: error(self, str(e)))

    def add(self):
        m = self.model.currentText().strip()
        if not m:
            return
        it = QListWidgetItem(f"{self.provider.currentText()} · {m}")
        it.setData(Qt.UserRole, (self.provider.currentData(), m))
        self.selected.addItem(it)

    def run(self):
        targets = [self.selected.item(i).data(Qt.UserRole) for i in range(self.selected.count())]
        if not targets:
            error(self, "Add at least one model.")
            return
        prompt = self.prompt.toPlainText().strip()
        mt = self.max_tokens.value()
        self.cancel = CancelToken()
        tok = self.cancel
        self.table.setRowCount(0)
        self.results = []
        self.run_btn.setEnabled(False)

        def work(progress):
            for pid, model in targets:
                if tok.cancelled:
                    break
                progress(("start", pid, model))
                res = run_one(self.ctx.providers, pid, model, prompt, mt, cancel=tok)
                self.ctx.benchmarks.record(prompt=prompt[:500], provider=pid, model=model, latency_ms=res.latency_ms,
                                           first_token_ms=res.first_token_ms, output_chars=len(res.text),
                                           tokens_per_sec=res.tokens_per_sec, success=res.success, error=res.error)
                progress(("done", res))

        run_async(work, on_progress=self._progress, on_done=lambda _: self._finished(),
                  on_error=lambda e: (self._finished(), error(self, str(e))))

    def _progress(self, p):
        if p[0] == "start":
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(p[1]))
            self.table.setItem(r, 1, QTableWidgetItem(p[2]))
            self.table.setItem(r, 2, QTableWidgetItem("running…"))
            return
        res = p[1]
        self.results.append(res)
        r = len(self.results) - 1
        spec = published_spec(res.model) or {}
        expected = self.expected.text().strip().lower()
        quality = "—" if not expected else ("pass" if expected in res.text.lower() else "fail")
        vals = [res.provider, res.model, "OK" if res.success else f"Error: {res.error}",
                f"{res.latency_ms} ms", f"{res.first_token_ms} ms" if res.first_token_ms is not None else "—",
                f"{res.output_tokens}{'' if res.tokens_exact else ' (est.)'}",
                f"{res.tokens_per_sec}" if res.tokens_per_sec else "—", quality,
                f"{spec['context']:,}" if spec.get("context") else "—", spec.get("modalities", "—"),
                {True: "yes", False: "no"}.get(spec.get("tools"), "—")]
        for c, v in enumerate(vals):
            self.table.setItem(r, c, QTableWidgetItem(str(v)))
        self._show_output(r)

    def _show_output(self, r):
        if 0 <= r < len(self.results):
            res = self.results[r]
            self.output.setHtml(f"<style>{chat_css()}</style><h3>{res.model}</h3>{render(res.text or '(no output)')}")

    def _finished(self):
        self.run_btn.setEnabled(True)
        self._history()

    def _history(self):
        rows = self.ctx.benchmarks.list(100)
        self.history.setRowCount(0)
        for b in rows:
            r = self.history.rowCount()
            self.history.insertRow(r)
            for c, v in enumerate([b["created_at"], b["provider"], b["model"], "yes" if b["success"] else "no",
                                   b["latency_ms"], b["first_token_ms"], b["tokens_per_sec"]]):
                self.history.setItem(r, c, QTableWidgetItem("—" if v is None else str(v)))
