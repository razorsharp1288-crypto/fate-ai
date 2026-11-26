"""First-launch experience: 9 steps; cloud and local setup are both optional."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                               QPushButton, QRadioButton, QStackedWidget, QVBoxLayout, QWidget)

from ...ai.local_engine.catalog import recommendations, recommended_tier
from ...hardware.detection import detect_all
from ...resources.manager import PRESETS, apply_preset
from ..components.icons import logo_pixmap
from ..components.widgets import Banner, Card
from ..components.worker import run_async

STEPS = ["Welcome", "Hardware", "Compatibility", "Local or cloud", "API provider", "Test connection",
         "Local models", "Resources", "Finish"]


class OnboardingDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.hw = None
        self.setWindowTitle("Welcome to FATE AI")
        self.resize(820, 600)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        self.step_label = QLabel()
        self.step_label.setObjectName("Muted")
        root.addWidget(self.step_label)
        self.bar = QProgressBar()
        self.bar.setRange(0, len(STEPS) - 1)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        root.addWidget(self.bar)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        nav = QHBoxLayout()
        self.skip = QPushButton("Skip setup")
        self.skip.setObjectName("Ghost")
        self.skip.clicked.connect(self.finish)
        self.back = QPushButton("Back")
        self.back.clicked.connect(lambda: self.go(self.stack.currentIndex() - 1))
        self.next = QPushButton("Next")
        self.next.setObjectName("Primary")
        self.next.clicked.connect(self._next)
        nav.addWidget(self.skip)
        nav.addStretch(1)
        nav.addWidget(self.back)
        nav.addWidget(self.next)
        root.addLayout(nav)
        for builder in (self._welcome, self._hardware, self._compat, self._choice, self._provider, self._test,
                        self._local, self._resources, self._finish):
            self.stack.addWidget(builder())
        self.go(0)

    @staticmethod
    def _page(title: str, text: str = "") -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 18, 0, 0)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        if text:
            s = QLabel(text)
            s.setObjectName("Muted")
            s.setWordWrap(True)
            lay.addWidget(s)
        return w, lay

    def _welcome(self):
        w, lay = self._page("")
        logo = QLabel()
        logo.setPixmap(logo_pixmap(140))
        logo.setAlignment(Qt.AlignCenter)
        lay.addStretch(1)
        lay.addWidget(logo)
        t = QLabel("Welcome to FATE AI")
        t.setObjectName("PageTitle")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        s = QLabel("A private AI workstation that runs on your PC. No FATE account, no FATE servers.\n"
                   "Use free local models, your own cloud API keys, or both.")
        s.setAlignment(Qt.AlignCenter)
        s.setObjectName("Muted")
        lay.addWidget(s)
        lay.addStretch(2)
        return w

    def _hardware(self):
        w, lay = self._page("Detecting your hardware", "FATE AI reads your CPU, memory, GPU and storage locally to "
                                                       "recommend models and safe resource limits.")
        self.hw_label = QLabel("Detecting…")
        self.hw_label.setWordWrap(True)
        c = Card()
        c.add(self.hw_label)
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _compat(self):
        w, lay = self._page("Compatibility")
        self.compat_label = QLabel("")
        self.compat_label.setWordWrap(True)
        c = Card()
        c.add(self.compat_label)
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _choice(self):
        w, lay = self._page("How do you want to use AI?", "You can change this any time.")
        self.choice = QButtonGroup(self)
        for i, (label, desc) in enumerate((
                ("Local AI", "Free and private. Models run on this PC via Ollama."),
                ("Cloud AI", "Use OpenAI or Anthropic with your own API key (billed by them)."),
                ("Both", "Recommended: local for private work, cloud for the hardest tasks."))):
            rb = QRadioButton(f"{label} — {desc}")
            self.choice.addButton(rb, i)
            lay.addWidget(rb)
        self.choice.button(2).setChecked(True)
        lay.addStretch(1)
        return w

    def _provider(self):
        w, lay = self._page("Add a cloud provider (optional)", "Your key is stored in Windows Credential Manager "
                                                               "and only ever sent to the provider.")
        self.prov = QComboBox()
        self.prov.addItem("OpenAI", "openai")
        self.prov.addItem("Anthropic Claude", "anthropic")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Paste your API key (or leave empty to skip)")
        lay.addWidget(self.prov)
        lay.addWidget(self.key)
        lay.addStretch(1)
        return w

    def _test(self):
        w, lay = self._page("Test the connection")
        self.test_banner = Banner("No key entered — skipping cloud setup.")
        lay.addWidget(self.test_banner)
        self.test_btn = QPushButton("Test again")
        self.test_btn.clicked.connect(self._run_test)
        lay.addWidget(self.test_btn, 0, Qt.AlignLeft)
        lay.addStretch(1)
        return w

    def _local(self):
        w, lay = self._page("Recommended local models", "Pick one to download now, or skip and do it later on the "
                                                        "AI Models page.")
        self.ollama_state = Banner("Checking for Ollama…")
        lay.addWidget(self.ollama_state)
        self.model_pick = QComboBox()
        lay.addWidget(self.model_pick)
        self.dl_btn = QPushButton("Download selected model")
        self.dl_btn.clicked.connect(self._download)
        self.dl_progress = QProgressBar()
        self.dl_progress.hide()
        self.dl_label = QLabel("")
        self.dl_label.setObjectName("Muted")
        lay.addWidget(self.dl_btn, 0, Qt.AlignLeft)
        lay.addWidget(self.dl_progress)
        lay.addWidget(self.dl_label)
        lay.addStretch(1)
        return w

    def _resources(self):
        w, lay = self._page("Resource preference", "How much of your PC may FATE AI's workloads use?")
        self.preset = QButtonGroup(self)
        for i, (k, p) in enumerate(PRESETS.items()):
            rb = QRadioButton(f"{p.label} — {p.description}")
            rb.setProperty("key", k)
            self.preset.addButton(rb, i)
            lay.addWidget(rb)
            if k == "balanced":
                rb.setChecked(True)
        lay.addStretch(1)
        return w

    def _finish(self):
        w, lay = self._page("You're all set", "FATE AI is ready. Your dashboard is next.")
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        lay.addStretch(1)
        return w

    # -- navigation -------------------------------------------------------
    def go(self, i):
        i = max(0, min(len(STEPS) - 1, i))
        if i == 4 and self.choice.checkedId() == 0:  # local only -> skip cloud steps
            i = 6 if self.stack.currentIndex() < 4 else 3
        if i == 5 and self.choice.checkedId() == 0:
            i = 6
        if i == 6 and self.choice.checkedId() == 1 and self.stack.currentIndex() == 5:
            i = 7
        self.stack.setCurrentIndex(i)
        self.bar.setValue(i)
        self.step_label.setText(f"Step {i + 1} of {len(STEPS)} · {STEPS[i]}")
        self.back.setEnabled(i > 0)
        self.next.setText("Open dashboard" if i == len(STEPS) - 1 else "Next")
        if i == 1 and self.hw is None:
            run_async(detect_all, on_done=self._hw_done, on_error=lambda e: self.hw_label.setText(str(e)))
        if i == 5:
            self._run_test()
        if i == 6:
            self._check_ollama()
        if i == 8:
            self._summary()

    def _next(self):
        i = self.stack.currentIndex()
        if i == 4 and self.key.text().strip():
            try:
                self.ctx.credentials.set_api_key(self.prov.currentData(), self.key.text())
                self.key.clear()
            except Exception as e:
                self.test_banner.setText(f"✗ {e}")
        if i == len(STEPS) - 1:
            self.finish()
            return
        self.go(i + 1)

    def _hw_done(self, hw):
        self.hw = hw
        gpu = "; ".join(f"{g.name} ({g.vram_total_gb:.0f} GB VRAM)" if g.vram_total_gb else g.name for g in hw.gpus)
        self.hw_label.setText(
            f"<b>CPU</b>: {hw.cpu.model or 'Unknown'} — {hw.cpu.physical_cores or '?'} cores / "
            f"{hw.cpu.logical_threads} threads<br><b>Memory</b>: {hw.memory.total_gb:.1f} GB<br>"
            f"<b>GPU</b>: {gpu or 'No dedicated GPU detected'}<br>"
            f"<b>Storage</b>: {hw.storage[0].free_gb:.0f} GB free on {hw.storage[0].mount}" if hw.storage else "")
        tier = recommended_tier(hw.memory.total_gb, hw.best_gpu_vram_gb)
        v = hw.virtualization
        virt = [n for n, ok in (("Hyper-V", v.hyperv_available), ("WSL2", v.wsl_available),
                                ("VirtualBox", bool(v.virtualbox_path)), ("Docker", bool(v.docker_path)),
                                ("Podman", bool(v.podman_path))) if ok]
        self.compat_label.setText(
            f"<b>Local AI tier:</b> {tier.title()} — "
            + {"lightweight": "small 1–4B models will run well.",
               "balanced": "7–9B models are a good fit.",
               "high": "14B+ models are possible."}[tier]
            + f"<br><b>GPU acceleration:</b> {', '.join(hw.acceleration) or 'CPU only'}"
            + f"<br><b>Virtualization available:</b> {', '.join(virt) or 'none detected (sandboxes fall back to Level 1)'}")
        self.model_pick.clear()
        for fit in recommendations(hw):
            if fit.model.tier == tier and fit.verdict != "too_large":
                self.model_pick.addItem(f"{fit.model.tag} — {fit.model.description} ({fit.model.download_gb} GB)",
                                        fit.model.tag)
        if not self.model_pick.count():
            for fit in recommendations(hw):
                if fit.verdict in ("cpu", "gpu"):
                    self.model_pick.addItem(f"{fit.model.tag} ({fit.model.download_gb} GB)", fit.model.tag)

    def _run_test(self):
        pid = self.prov.currentData()
        if not self.ctx.credentials.has_api_key(pid):
            self.test_banner.setText("No key entered — skipping cloud setup. You can add one later on the API Keys page.")
            return
        self.test_banner.setText("Testing…")
        run_async(lambda: self.ctx.providers.get(pid).test_connection(),
                  on_done=lambda r: self.test_banner.setText(("✓ " if r.ok else "✗ ") + r.message),
                  on_error=lambda e: self.test_banner.setText(f"✗ {e}"))

    def _check_ollama(self):
        def done(v):
            self.ollama_state.setText(f"✓ Ollama {v} is running." if v else
                                      "Ollama is not running. Install it from <a href='https://ollama.com/download'>"
                                      "ollama.com/download</a> to use local models — or skip this step.")
            self.dl_btn.setEnabled(bool(v))
        run_async(lambda: self.ctx.providers.get("ollama").version(), on_done=done)

    def _download(self):
        tag = self.model_pick.currentData()
        if not tag:
            return
        self.dl_btn.setEnabled(False)
        self.dl_progress.show()

        def work(progress):
            self.ctx.providers.get("ollama").pull(tag, progress=lambda s, c, t: progress((s, c, t)))

        def prog(p):
            s, c, t = p
            if t:
                self.dl_progress.setRange(0, 100)
                self.dl_progress.setValue(int((c or 0) / t * 100))
            self.dl_label.setText(s)

        def done(_):
            self.dl_label.setText(f"✓ {tag} installed and set as default.")
            self.ctx.settings.update(ai={"default_provider": "ollama", "default_model": tag})
        run_async(work, on_progress=prog, on_done=done,
                  on_error=lambda e: (self.dl_label.setText(f"✗ {e}"), self.dl_btn.setEnabled(True)))

    def _summary(self):
        b = self.preset.checkedButton()
        if b:
            apply_preset(self.ctx.settings, b.property("key"))
        cloud = [p["name"] for p in self.ctx.providers.configs() if self.ctx.credentials.has_api_key(p["id"])]
        s = self.ctx.settings.settings
        self.summary.setText(f"• Cloud providers with keys: {', '.join(cloud) or 'none'}<br>"
                             f"• Default model: {s.ai.default_model or 'not set (choose one in chat)'}<br>"
                             f"• Resource preset: {PRESETS.get(s.resources.preset).label if s.resources.preset in PRESETS else 'Custom'}")

    def finish(self):
        if self.ctx.settings.settings.ai.default_provider == "ollama" and not self.ctx.settings.settings.ai.default_model \
                and self.ctx.credentials.has_api_key("openai"):
            self.ctx.settings.update(ai={"default_provider": "openai"})
        self.ctx.settings.update(onboarding_complete=True)
        self.accept()
