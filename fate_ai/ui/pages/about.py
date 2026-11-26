from __future__ import annotations

import platform
import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ... import __version__
from ..components.icons import logo_pixmap
from ..components.widgets import Card, Page


class AboutPage(Page):
    def __init__(self, ctx):
        super().__init__("About FATE AI")
        logo = QLabel()
        logo.setPixmap(logo_pixmap(128))
        logo.setAlignment(Qt.AlignCenter)
        self.body.addWidget(logo)
        name = QLabel("FATE AI")
        name.setObjectName("PageTitle")
        name.setAlignment(Qt.AlignCenter)
        self.body.addWidget(name)
        v = QLabel(f"Version {__version__}")
        v.setObjectName("Muted")
        v.setAlignment(Qt.AlignCenter)
        self.body.addWidget(v)
        c = Card("Local-first by design")
        t = QLabel(
            "FATE AI runs entirely on your computer. There are no FATE servers: conversations, settings and projects "
            "stay in your data folder, API keys stay in the Windows Credential Manager, and cloud AI is billed by "
            "each provider directly to your own account.<br><br>"
            "Local inference is powered by <a href='https://ollama.com'>Ollama</a> and "
            "<a href='https://github.com/ggml-org/llama.cpp'>llama.cpp</a> (installed separately). Virtualization uses "
            "Hyper-V, VirtualBox, WSL2, Docker or Podman when present.")
        t.setWordWrap(True)
        t.setOpenExternalLinks(True)
        c.add(t)
        self.body.addWidget(c)
        e = Card("Environment")
        e.add(QLabel(f"Python {platform.python_version()} · PySide6 {pyside_version} · {platform.platform()}"
                     f"{' · packaged build' if getattr(sys, 'frozen', False) else ' · running from source'}"))
        e.add(QLabel(f"Data folder: {ctx.paths.root}"))
        self.body.addWidget(e)
        lic = QLabel("Released under the MIT License. Third-party components retain their own licenses.")
        lic.setObjectName("Dim")
        self.body.addWidget(lic)
        self.body.addStretch(1)
