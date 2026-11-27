"""Microphone button: click to talk, click again to stop → text."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QPushButton

from .icons import icon
from .worker import run_async


class MicButton(QPushButton):
    transcribed = Signal(str)
    status = Signal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.rec = None
        self._t0 = 0.0
        self._level = 0.0
        self.setIcon(icon("mic"))
        self.setObjectName("Ghost")
        self.setToolTip("Talk instead of typing (click to start, click again to send)")
        self.clicked.connect(self.toggle)
        self.timer = QTimer(self, interval=200, timeout=self._tick)
        self.busy = False

    def toggle(self):
        if self.busy:
            return
        if self.rec is not None and self.rec.recording:
            self.finish()
        else:
            self.begin()

    def begin(self):
        from ...voice.recorder import Recorder
        self.rec = Recorder(self)
        self.rec.levelChanged.connect(lambda v: setattr(self, "_level", v))
        try:
            self.rec.start()
        except Exception as e:
            self.rec = None
            self.status.emit(f"🎤 {e}")
            return
        self._t0 = time.time()
        self.setIcon(icon("stop", "#F87171"))
        self.setStyleSheet("QPushButton{background:rgba(248,113,113,0.18);border:1px solid #F87171;"
                           "border-radius:9px;}")
        self.timer.start()
        self.status.emit("🎤 Listening… click the mic again when you're done.")

    def _tick(self):
        secs = int(time.time() - self._t0)
        bars = "▁▂▃▄▅▆▇█"[min(7, int(self._level * 8))]
        self.status.emit(f"🎤 Listening {secs // 60}:{secs % 60:02d}  {bars * 3}")
        if secs >= 120:
            self.finish()

    def _reset(self):
        self.timer.stop()
        self.setIcon(icon("mic"))
        self.setStyleSheet("")

    def finish(self):
        wav = self.rec.stop() if self.rec else b""
        self.rec = None
        self._reset()
        from ...voice.wav import duration_s
        if not wav or duration_s(wav) < 0.4:
            self.status.emit("🎤 Didn't catch that — hold on a little longer.")
            return
        self.busy = True
        self.setEnabled(False)
        self.status.emit("🎤 Transcribing…")
        v = self.ctx.settings.settings.voice

        def done(t):
            self.busy = False
            self.setEnabled(True)
            if not t.text:
                self.status.emit("🎤 No speech recognised.")
                return
            self.status.emit(f"🎤 Heard via {t.engine}.")
            self.transcribed.emit(t.text)

        def fail(e):
            self.busy = False
            self.setEnabled(True)
            self.status.emit(f"🎤 {e}")
        from ...voice.transcribe import transcribe
        run_async(lambda: transcribe(self.ctx, wav, v.engine, v.language), on_done=done, on_error=fail)
