"""Microphone capture with Qt Multimedia → 16-bit mono WAV."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .wav import float32_to_int16, int32_to_int16, level, make_wav, to_mono


class Recorder(QObject):
    levelChanged = Signal(float)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self._dev = None
        self._chunks: list[bytes] = []
        self._fmt = None

    @staticmethod
    def available() -> bool:
        try:
            from PySide6.QtMultimedia import QMediaDevices
            return not QMediaDevices.defaultAudioInput().isNull()
        except Exception:
            return False

    @property
    def recording(self) -> bool:
        return self._source is not None

    def start(self) -> None:
        from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
        dev = QMediaDevices.defaultAudioInput()
        if dev.isNull():
            raise RuntimeError("No microphone found. Plug one in or check Windows sound settings.")
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        if not dev.isFormatSupported(fmt):
            fmt = dev.preferredFormat()
        self._fmt = fmt
        self._chunks = []
        self._source = QAudioSource(dev, fmt, self)
        self._dev = self._source.start()
        if self._dev is None:
            self._source = None
            raise RuntimeError("Could not open the microphone. Check Windows privacy settings → Microphone.")
        self._dev.readyRead.connect(self._read)

    def _pcm16(self, data: bytes) -> bytes:
        from PySide6.QtMultimedia import QAudioFormat
        sf = self._fmt.sampleFormat()
        if sf == QAudioFormat.Float:
            data = float32_to_int16(data)
        elif sf == QAudioFormat.Int32:
            data = int32_to_int16(data)
        elif sf == QAudioFormat.UInt8:
            data = bytes(b for v in data for b in int((v - 128) << 8).to_bytes(2, "little", signed=True))
        return to_mono(data, self._fmt.channelCount())

    def _read(self):
        if self._dev is None:
            return
        data = bytes(self._dev.readAll())
        if data:
            pcm = self._pcm16(data)
            self._chunks.append(pcm)
            self.levelChanged.emit(level(pcm))

    def stop(self) -> bytes:
        """Stop and return the recording as WAV bytes."""
        if self._source is None:
            return b""
        self._read()
        self._source.stop()
        self._source.deleteLater()
        self._source = self._dev = None
        return make_wav(b"".join(self._chunks), self._fmt.sampleRate())

    def cancel(self) -> None:
        if self._source is not None:
            self._source.stop()
            self._source.deleteLater()
        self._source = self._dev = None
        self._chunks = []
