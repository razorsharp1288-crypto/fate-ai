from __future__ import annotations

import base64
import html
import threading

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from ...computer.agent import ComputerAgent
from ...computer.tools import Toolbox
from ...core.task_manager import CancelToken
from ..components.mic import MicButton
from ..components.widgets import Badge, Banner, Card, Page, confirm, error, hbox
from ..components.worker import run_async
from ..themes import C

EXAMPLES = ["Open Notepad and write a short poem about the ocean",
            "Open YouTube and search for lo-fi music",
            "How much free disk space do I have? Make a list of my 10 biggest files in Downloads",
            "Take a screenshot and tell me what's on my screen",
            "Create a folder called 'Projects' on my Desktop with a README.txt inside"]


class _Bridge(QObject):
    """Lets the worker thread ask the GUI thread for screenshots and approvals (blocking)."""
    askShot = Signal(int)
    askApproval = Signal(str)

    def __init__(self, page):
        super().__init__()
        self.page = page
        self._ev = threading.Event()
        self._val = None
        self.askShot.connect(self._shot, Qt.QueuedConnection)
        self.askApproval.connect(self._approve, Qt.QueuedConnection)

    def screenshot(self, max_w: int):
        self._ev.clear()
        self.askShot.emit(max_w)
        if not self._ev.wait(30):
            raise RuntimeError("Screen capture timed out")
        if isinstance(self._val, Exception):
            raise self._val
        return self._val

    def approve(self, desc: str) -> str:
        self._ev.clear()
        self.askApproval.emit(desc)
        self._ev.wait()
        return self._val

    @Slot(int)
    def _shot(self, max_w):
        try:
            self._val = self.page.grab_screen(max_w)
        except Exception as e:  # noqa: BLE001
            self._val = e
        self._ev.set()

    @Slot(str)
    def _approve(self, desc):
        self._val = ApprovalDialog.ask(desc)
        self._ev.set()


class ApprovalDialog(QDialog):
    @classmethod
    def ask(cls, desc: str) -> str:
        d = cls(desc)
        d.exec()
        return d.answer

    def __init__(self, desc: str):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.answer = "deny"
        self.setWindowTitle("FATE AI wants to do something")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        t = QLabel("<b>Allow this action?</b>")
        lay.addWidget(t)
        body = QPlainTextEdit(desc)
        body.setReadOnly(True)
        body.setMaximumHeight(220)
        lay.addWidget(body)
        deny = QPushButton("Deny")
        deny.setObjectName("Danger")
        allow = QPushButton("Allow")
        allow.setObjectName("Primary")
        allow_all = QPushButton("Allow everything for this task")
        deny.clicked.connect(self.reject)
        allow.clicked.connect(lambda: self._done("allow"))
        allow_all.clicked.connect(lambda: self._done("allow_all"))
        lay.addLayout(hbox(deny, None, allow_all, allow))
        allow.setDefault(True)

    def _done(self, a):
        self.answer = a
        self.accept()


class StopOverlay(QWidget):
    """Always-on-top bar shown while FATE AI is operating the PC."""

    def __init__(self, on_stop):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setStyleSheet(f"QWidget{{background:{C['card_hi']};border:1px solid {C['accent']};border-radius:10px;}}"
                           "QLabel{border:none;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 6, 6)
        self.label = QLabel("FATE AI is controlling your PC")
        stop = QPushButton("Stop")
        stop.setObjectName("Danger")
        stop.clicked.connect(on_stop)
        lay.addWidget(self.label)
        lay.addWidget(stop)
        self.adjustSize()
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.center().x() - 200, g.top() + 6)
        self.setFixedWidth(400)


class ComputerPage(Page):
    def __init__(self, ctx):
        super().__init__("PC Control", "Tell FATE AI what to do on your computer — it can look at your screen, open "
                                       "apps and websites, edit files, run commands and use the mouse and keyboard.",
                         scroll=False)
        self.ctx = ctx
        self.cancel: CancelToken | None = None
        self.overlay = None
        self.bridge = _Bridge(self)
        self.state = Badge("")
        self.state.setFixedHeight(24)
        self.header_actions.addWidget(self.state, 0, Qt.AlignVCenter)
        settings_btn = QPushButton("Permissions…")
        settings_btn.clicked.connect(self._open_settings)
        self.header_actions.addWidget(settings_btn)

        self.off_banner = Banner("")
        self.off_banner.setObjectName("WarnBanner")
        self.body.addWidget(self.off_banner)
        self.enable_btn = QPushButton("Turn on PC Control")
        self.enable_btn.setObjectName("Primary")
        self.enable_btn.clicked.connect(self.turn_on)
        self.body.addLayout(hbox(self.enable_btn, None))

        task = Card()
        self.provider = QComboBox()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumWidth(240)
        self.provider.currentIndexChanged.connect(self._load_models)
        vis = QLabel("Use a model that can see images (e.g. GPT-4o, Claude, Gemini, Llama 3.2 Vision, Qwen-VL) for "
                     "screen tasks.")
        vis.setObjectName("Dim")
        task.add(hbox(QLabel("Model"), self.provider, self.model, vis, None))
        self.task = QPlainTextEdit()
        self.task.setPlaceholderText("What should FATE AI do? e.g. " + EXAMPLES[0])
        self.task.setFixedHeight(80)
        self.mic = MicButton(ctx)
        self.mic.transcribed.connect(self._heard)
        self.run_btn = QPushButton("▶ Do it")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setMinimumHeight(40)
        self.run_btn.clicked.connect(self.run)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        self.hide_me = QCheckBox("Minimise FATE AI while working")
        self.hide_me.setChecked(True)
        ex = QComboBox()
        ex.addItem("Examples…")
        ex.addItems(EXAMPLES)
        ex.activated.connect(lambda i: i and self.task.setPlainText(EXAMPLES[i - 1]))
        task.add(hbox(self.task, self.mic))
        task.add(hbox(self.run_btn, self.stop_btn, self.hide_me, None, ex))
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        self.mic.status.connect(self.status.setText)
        task.add(self.status)
        self.body.addWidget(task)

        split = QSplitter()
        self.log = QTextBrowser()
        self.log.setOpenExternalLinks(False)
        split.addWidget(self.log)
        self.preview = QLabel("Latest screenshot appears here")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumWidth(320)
        self.preview.setStyleSheet(f"background:{C['panel']};border:1px solid {C['border']};border-radius:10px;"
                                   f"color:{C['dim']};")
        split.addWidget(self.preview)
        split.setSizes([600, 500])
        self.body.addWidget(split, 1)
        self.body.addWidget(QLabel("<span style='color:#6B6485'>Emergency stop: click Stop, or slam your mouse into "
                                   "the top-left corner of the screen. Every action is recorded in Security Center → "
                                   "Audit log.</span>"))

    # ------------------------------------------------------------------ state
    def on_show(self):
        self._refresh_state()
        cur = self.provider.currentData()
        self.provider.blockSignals(True)
        self.provider.clear()
        for p in self.ctx.providers.configs():
            if p["enabled"]:
                self.provider.addItem(p["name"], p["id"])
        i = self.provider.findData(cur or self.ctx.settings.settings.ai.default_provider)
        self.provider.setCurrentIndex(max(0, i))
        self.provider.blockSignals(False)
        self._load_models()

    def _refresh_state(self):
        c = self.ctx.settings.settings.computer
        mode = {"ask": "asks before each action", "auto_safe": "auto-approves opening apps/sites; asks for changes",
                "auto_all": "FULL AUTO — no confirmations"}[c.approval]
        if c.enabled:
            self.state.set("ON · " + {"ask": "Ask", "auto_safe": "Auto (safe)", "auto_all": "Full auto"}[c.approval],
                           "warn" if c.approval == "auto_all" else "ok")
            self.off_banner.hide()
            self.enable_btn.hide()
            self.status.setText(f"PC Control is on and {mode}. Change this under Permissions…")
        else:
            self.state.set("OFF", "muted")
            self.off_banner.setText("<b>PC Control is off.</b> When it's on, the AI model you choose can see your "
                                    "screen and operate your computer — only during tasks you start here, and only "
                                    "with the permissions you allow.")
            self.off_banner.show()
            self.enable_btn.show()
        self.run_btn.setEnabled(c.enabled)

    def turn_on(self):
        if confirm(self, "Turn on PC Control?",
                   "FATE AI will be able to look at your screen and control this PC (apps, files, commands, mouse "
                   "and keyboard) while it works on a task you give it.\n\n"
                   "• By default it asks you before each action.\n"
                   "• Screenshots are sent to the AI model you pick — use a local model to keep them on this PC.\n"
                   "• You can stop it any time, or narrow the permissions in Settings.\n\nTurn it on?"):
            self.ctx.settings.update(computer={"enabled": True})
            self.ctx.audit.log("pc_control", "enabled", "")
            self._refresh_state()

    def _open_settings(self):
        win = self.window()
        if hasattr(win, "navigate"):
            win.navigate("settings")
            page = win.page("settings")
            if hasattr(page, "show_tab"):
                page.show_tab("PC Control & Power")

    def _load_models(self, *_):
        pid = self.provider.currentData()
        if not pid:
            return
        ai = self.ctx.settings.settings.ai
        default = ai.default_model if pid == ai.default_provider else (self.ctx.provider_repo.get(pid) or {}).get(
            "default_model", "")
        self.model.clear()
        if default:
            self.model.addItem(default)

        def done(res):
            if self.provider.currentData() != pid:
                return
            cur = self.model.currentText()
            self.model.clear()
            self.model.addItems(res[0])
            if cur:
                self.model.setCurrentText(cur)
        run_async(lambda: self.ctx.providers.models(pid), on_done=done, on_error=lambda e: None)

    def _heard(self, text):
        self.task.setPlainText(text)
        if self.ctx.settings.settings.voice.send_after_speaking:
            self.run()

    # ------------------------------------------------------------------ screen
    def grab_screen(self, max_w: int) -> tuple[str, int, int]:
        overlay_visible = self.overlay is not None and self.overlay.isVisible()
        if overlay_visible:
            self.overlay.hide()
        QApplication.processEvents()
        try:
            screen = QGuiApplication.primaryScreen()
            pm: QPixmap = screen.grabWindow(0)
        finally:
            if overlay_visible:
                self.overlay.show()
        real_w = pm.width()
        try:
            from ...computer import winput
            if winput.IS_WIN:
                real_w = winput.screen_size()[0]
        except Exception:
            pass
        if pm.width() > max_w:
            pm = pm.scaledToWidth(max_w, Qt.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        pm.toImage().save(buf, "JPEG", 72)
        self.preview.setPixmap(pm.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return base64.b64encode(bytes(ba)).decode(), pm.width(), real_w

    # ------------------------------------------------------------------ run
    def run(self):
        c = self.ctx.settings.settings.computer
        task = self.task.toPlainText().strip()
        if not c.enabled or not task or self.cancel is not None:
            return
        pid, model = self.provider.currentData(), self.model.currentText().strip()
        if not model:
            error(self, "Choose a model first.")
            return
        self.cancel = CancelToken()
        tok = self.cancel
        self.log.clear()
        self._log(f"<b>Task:</b> {html.escape(task)}<br><span style='color:#6B6485'>{html.escape(model)}</span>")
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        win = self.window()
        if self.hide_me.isChecked():
            win.showMinimized()
        self.overlay = StopOverlay(self.stop)
        self.overlay.show()
        toolbox = Toolbox(self.ctx.settings.settings, self.ctx.paths.root / "pc-control-backups", self.bridge.screenshot)
        agent = ComputerAgent(self.ctx.providers, pid, model, toolbox, self.ctx.settings.settings,
                              confirm=self.bridge.approve, audit=self.ctx.audit)

        def work(progress):
            agent.on_step = progress
            return agent.run(task, cancel=tok)

        run_async(work, on_progress=self._step, on_done=self._done, on_error=self._fail)

    def _log(self, h: str):
        self.log.append(f"<div style='margin:6px 0;'>{h}</div>")

    def _step(self, step):
        colour = {"ok": C["ok"], "denied": C["warn"], "error": C["err"], "done": C["accent_hi"]}[step.status]
        if self.overlay:
            self.overlay.label.setText(f"Step {step.n}: {step.tool}")
        args = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in step.args.items()) if step.tool != "done" else ""
        h = (f"<b>{step.n}.</b> {html.escape(step.thought[:400])}<br>"
             f"<span style='color:{colour}'>▸ {html.escape(step.tool)}({html.escape(args)})</span>")
        if step.result:
            h += f"<br><span style='color:#9A93B3'>{html.escape(step.result[:600])}</span>"
        if step.image_b64:
            h += f"<br><img src='data:image/jpeg;base64,{step.image_b64}' width='360'>"
        self._log(h)

    def _end(self):
        self.cancel = None
        self.run_btn.setEnabled(self.ctx.settings.settings.computer.enabled)
        self.stop_btn.setEnabled(False)
        if self.overlay:
            self.overlay.close()
            self.overlay = None
        w = self.window()
        w.showNormal()
        w.raise_()
        w.activateWindow()

    def _done(self, res):
        self._end()
        msg = res.summary or res.stopped or "Finished."
        self._log(f"<b style='color:{C['accent_hi']}'>✓ {html.escape(msg)}</b>"
                  + (f"<br><span style='color:{C['warn']}'>{html.escape(res.stopped)}</span>"
                     if res.stopped and res.summary else ""))
        self.status.setText(msg)
        if self.ctx.settings.settings.voice.speak_replies and res.summary:
            from ...voice.speak import speak
            speak(res.summary)

    def _fail(self, e):
        self._end()
        self._log(f"<b style='color:{C['err']}'>✗ {html.escape(str(e))}</b>")
        self.status.setText(str(e))

    def stop(self):
        if self.cancel:
            self.cancel.cancel()
            self.status.setText("Stopping after the current step…")
            if self.overlay:
                self.overlay.label.setText("Stopping…")
