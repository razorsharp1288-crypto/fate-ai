from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QLineEdit, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ...ai.local_engine.catalog import CATALOG, assess, recommended_tier
from ...core.task_manager import CancelToken
from ...hardware.detection import detect_all
from ..components.widgets import Badge, Banner, Card, Page, confirm, error, fmt_bytes, hbox
from ..components.worker import run_async

VERDICT = {"gpu": ("Runs on GPU", "ok"), "cpu": ("Runs on CPU", "info"), "tight": ("Tight fit", "warn"),
           "too_large": ("Too large", "err")}


def ro(text) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


class ModelsPage(Page):
    def __init__(self, ctx):
        super().__init__("AI Models", "Download, load and manage local models with Ollama or llama.cpp. "
                                      "Everything runs on your PC — no cloud required.")
        self.ctx = ctx
        self.hw = None
        self.pull_token: CancelToken | None = None

        self.status_card = Card("Local engines")
        self.ollama_badge = Badge("Checking…")
        self.llama_badge = Badge("Checking…")
        self.status_card.add(hbox(QLabel("Ollama"), self.ollama_badge, None, QLabel("llama.cpp server"),
                                  self.llama_badge, None))
        self.engine_hint = QLabel("")
        self.engine_hint.setObjectName("Muted")
        self.engine_hint.setWordWrap(True)
        self.engine_hint.setOpenExternalLinks(True)
        self.status_card.add(self.engine_hint)
        self.body.addWidget(self.status_card)

        tabs = QTabWidget()
        self.body.addWidget(tabs, 1)

        # Installed
        inst = QWidget()
        il = QVBoxLayout(inst)
        self.installed = QTableWidget(0, 6)
        self.installed.setHorizontalHeaderLabels(["Model", "Size", "Parameters", "Quantization", "Family", "Status"])
        self.installed.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.installed.setSelectionBehavior(QTableWidget.SelectRows)
        self.installed.verticalHeader().hide()
        il.addWidget(self.installed, 1)
        b_load, b_unload, b_del, b_info, b_ref, b_default = (QPushButton(t) for t in (
            "Load into memory", "Unload", "Delete", "Details", "Refresh", "Set as default"))
        b_del.setObjectName("Danger")
        b_load.clicked.connect(lambda: self._model_op("load"))
        b_unload.clicked.connect(lambda: self._model_op("unload"))
        b_del.clicked.connect(self.delete_model)
        b_info.clicked.connect(self.details)
        b_ref.clicked.connect(self.refresh)
        b_default.clicked.connect(self.set_default)
        il.addLayout(hbox(b_load, b_unload, b_info, b_default, None, b_ref, b_del))
        self.details_label = QLabel("")
        self.details_label.setObjectName("Muted")
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        il.addWidget(self.details_label)
        tabs.addTab(inst, "Installed")

        # Discover
        disc = QWidget()
        dl = QVBoxLayout(disc)
        self.tier_banner = Banner("Detecting hardware to recommend models…")
        dl.addWidget(self.tier_banner)
        self.catalog = QTableWidget(0, 7)
        self.catalog.setHorizontalHeaderLabels(["Model", "Family", "Tier", "Download", "Est. RAM", "Est. VRAM",
                                                "Fit on this PC"])
        self.catalog.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.catalog.horizontalHeader().setStretchLastSection(True)
        self.catalog.setSelectionBehavior(QTableWidget.SelectRows)
        self.catalog.verticalHeader().hide()
        dl.addWidget(self.catalog, 1)
        self.custom_tag = QLineEdit(placeholderText="…or any Ollama tag, e.g. qwen2.5-coder:1.5b")
        b_pull = QPushButton("Download selected")
        b_pull.setObjectName("Primary")
        b_pull.clicked.connect(self.pull_selected)
        b_pull_c = QPushButton("Download tag")
        b_pull_c.clicked.connect(lambda: self.pull(self.custom_tag.text().strip()))
        dl.addLayout(hbox(b_pull, self.custom_tag, b_pull_c))
        note = QLabel("Sizes and memory needs are estimates for the default 4-bit quantisation. Availability "
                      "depends on the Ollama library; errors from Ollama are shown as-is.")
        note.setObjectName("Dim")
        note.setWordWrap(True)
        dl.addWidget(note)
        tabs.addTab(disc, "Discover && download")

        # Running
        run = QWidget()
        rl = QVBoxLayout(run)
        self.running = QTableWidget(0, 4)
        self.running.setHorizontalHeaderLabels(["Model", "Memory", "In VRAM", "Expires"])
        self.running.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.running.verticalHeader().hide()
        rl.addWidget(self.running)
        tabs.addTab(run, "Loaded now")

        self.progress = QProgressBar()
        self.progress.hide()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("Muted")
        self.cancel_btn = QPushButton("Cancel download")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(lambda: self.pull_token and self.pull_token.cancel())
        self.body.addLayout(hbox(self.progress_label, self.progress, self.cancel_btn))

        run_async(detect_all, on_done=self._hw_ready)

    @property
    def ollama(self):
        return self.ctx.providers.get("ollama")

    def on_show(self):
        self.refresh()

    def refresh(self):
        def work():
            o = self.ollama
            v = o.version()
            models = o.list_models() if v else []
            running = o.running_models() if v else []
            try:
                lc = self.ctx.providers.get("llamacpp").health()
            except Exception:
                lc = False
            return v, models, running, lc
        run_async(work, on_done=self._refreshed, on_error=lambda e: self.engine_hint.setText(str(e)))

    def _refreshed(self, data):
        v, models, running, lc = data
        if v:
            self.ollama_badge.set(f"Running · v{v}", "ok")
            self.engine_hint.setText(f"{len(models)} models installed. Models are stored by Ollama "
                                     f"(default %USERPROFILE%\\.ollama\\models; change with OLLAMA_MODELS).")
        else:
            self.ollama_badge.set("Not running", "err")
            self.engine_hint.setText('Ollama is not running. Install it from <a href="https://ollama.com/download">'
                                     'ollama.com/download</a>, start it, then click Refresh. FATE AI does not '
                                     'bundle model weights.')
        self.llama_badge.set("Running" if lc else "Not detected", "ok" if lc else "muted")
        running_names = {r.get("name") for r in running}
        self.installed.setRowCount(0)
        for m in models:
            r = self.installed.rowCount()
            self.installed.insertRow(r)
            d = m.details
            vals = [m.id, fmt_bytes(m.size_bytes), d.get("parameter_size", "—"), d.get("quantization_level", "—"),
                    d.get("family", "—"), "Loaded" if m.id in running_names else "On disk"]
            for c, val in enumerate(vals):
                self.installed.setItem(r, c, ro(val))
        self.running.setRowCount(0)
        for x in running:
            r = self.running.rowCount()
            self.running.insertRow(r)
            for c, val in enumerate([x.get("name"), fmt_bytes(x.get("size")), fmt_bytes(x.get("size_vram")),
                                     x.get("expires_at", "")[:19]]):
                self.running.setItem(r, c, ro(val))

    def _hw_ready(self, hw):
        self.hw = hw
        vram = hw.best_gpu_vram_gb
        tier = recommended_tier(hw.memory.total_gb, vram)
        names = {"lightweight": "Lightweight", "balanced": "Balanced", "high": "High performance"}
        self.tier_banner.setText(
            f"<b>Recommended tier: {names[tier]}</b> — detected {hw.memory.total_gb:.0f} GB RAM, "
            + (f"{vram:.0f} GB VRAM ({hw.gpus[0].name})" if vram else "no dedicated GPU memory detected (CPU inference)")
            + ".")
        disk = hw.storage[0].free_gb if hw.storage else None
        self.catalog.setRowCount(0)
        order = {"lightweight": 0, "balanced": 1, "high": 2}
        for m in sorted(CATALOG, key=lambda m: (order[m.tier], m.download_gb)):
            fit = assess(m, hw.memory.total_gb, hw.memory.available_gb, vram, disk)
            r = self.catalog.rowCount()
            self.catalog.insertRow(r)
            label, kind = VERDICT[fit.verdict]
            for c, val in enumerate([m.tag, m.family, names[m.tier], f"{m.download_gb} GB", f"{m.est_ram_gb} GB",
                                     f"{m.est_vram_gb} GB", label]):
                it = ro(val)
                it.setToolTip(f"{m.description}\n{fit.reason}")
                self.catalog.setItem(r, c, it)
            self.catalog.item(r, 0).setData(Qt.UserRole, (m, fit))
            from PySide6.QtGui import QColor
            self.catalog.item(r, 6).setForeground(QColor(Badge.COLORS[kind]))

    def _selected_installed(self) -> str | None:
        r = self.installed.currentRow()
        return self.installed.item(r, 0).text() if r >= 0 else None

    def pull_selected(self):
        r = self.catalog.currentRow()
        if r < 0:
            error(self, "Select a model in the list first.")
            return
        m, fit = self.catalog.item(r, 0).data(Qt.UserRole)
        if fit.verdict in ("too_large", "tight"):
            if not confirm(self, "Model may not fit", f"{m.tag}: {fit.reason}\n\nDownload anyway?", danger=True):
                return
        self.pull(m.tag)

    def pull(self, tag: str):
        if not tag:
            return
        if not all(c.isalnum() or c in ":._-/" for c in tag):
            error(self, "Invalid model tag.")
            return
        if self.pull_token:
            error(self, "A download is already in progress.")
            return
        self.pull_token = CancelToken()
        tok = self.pull_token
        self.progress.show()
        self.cancel_btn.show()
        self.progress.setRange(0, 0)
        self.progress_label.setText(f"Downloading {tag}…")

        def work(progress):
            self.ollama.pull(tag, progress=lambda s, c, t: progress((s, c, t)), cancel=tok)

        def prog(p):
            status, done, total = p
            if total:
                self.progress.setRange(0, 1000)
                self.progress.setValue(int(done / total * 1000) if done else 0)
                self.progress_label.setText(f"{tag}: {status} — {fmt_bytes(done)} / {fmt_bytes(total)}")
            else:
                self.progress_label.setText(f"{tag}: {status}")

        def finish(msg):
            self.pull_token = None
            self.progress.hide()
            self.cancel_btn.hide()
            self.progress_label.setText(msg)
            self.refresh()

        run_async(work, on_progress=prog, on_done=lambda _: finish(f"✓ {tag} installed."),
                  on_error=lambda e: (finish(f"Download stopped: {e}" if str(e) else "Download cancelled."),
                                      None if tok.cancelled else error(self, str(e), "Download failed")))

    def delete_model(self):
        tag = self._selected_installed()
        if tag and confirm(self, "Delete model", f"Delete {tag} from disk?", danger=True):
            run_async(self.ollama.delete, tag, on_done=lambda _: self.refresh(), on_error=lambda e: error(self, str(e)))

    def _model_op(self, op):
        tag = self._selected_installed()
        if not tag:
            return
        self.progress_label.setText(f"{'Loading' if op == 'load' else 'Unloading'} {tag}…")
        fn = (lambda: self.ollama.load(tag, self.ctx.settings.settings.local.keep_alive)) if op == "load" \
            else (lambda: self.ollama.unload(tag))
        run_async(fn, on_done=lambda _: (self.progress_label.setText(f"{tag}: {op} complete."), self.refresh()),
                  on_error=lambda e: error(self, str(e)))

    def details(self):
        tag = self._selected_installed()
        if not tag:
            return

        def done(d):
            info = d.get("model_info", {})
            ctx_len = next((v for k, v in info.items() if k.endswith("context_length")), None)
            det = d.get("details", {})
            self.details_label.setText(
                f"<b>{tag}</b> · format {det.get('format', '—')} · family {det.get('family', '—')} · "
                f"parameters {det.get('parameter_size', '—')} · quantisation {det.get('quantization_level', '—')}"
                + (f" · context window {ctx_len:,}" if isinstance(ctx_len, int) else "")
                + (f"<br>License: {str(d.get('license', ''))[:160]}…" if d.get("license") else ""))
        run_async(self.ollama.show, tag, on_done=done, on_error=lambda e: error(self, str(e)))

    def set_default(self):
        tag = self._selected_installed()
        if tag:
            self.ctx.settings.update(ai={"default_provider": "ollama", "default_model": tag})
            self.progress_label.setText(f"{tag} is now the default model.")
