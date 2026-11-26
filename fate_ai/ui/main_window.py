from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QMessageBox, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from .. import __version__
from .components.icons import app_icon, icon, logo_pixmap

log = logging.getLogger(__name__)

NAV = [
    ("home", "Home", "home"), ("chat", "Chat", "chat"), ("models", "AI Models", "models"),
    ("providers", "Providers", "providers"), ("keys", "API Keys", "key"), ("vms", "Virtual Machines", "vm"),
    ("sandbox", "Sandbox", "sandbox"), ("projects", "Projects", "projects"), ("prompts", "Prompt Library", "prompts"),
    ("compare", "Model Comparison", "compare"), ("usage", "Usage Dashboard", "usage"),
    ("hardware", "Hardware Monitor", "hardware"), ("dev", "Developer Tools", "dev"),
    ("security", "Security Center", "security"), ("settings", "Settings", "settings"), ("about", "About FATE AI", "about"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._really_quit = False
        self.setWindowTitle("FATE AI")
        self.setWindowIcon(app_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1100, 680)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 18, 12, 14)
        brand = QHBoxLayout()
        lg = QLabel()
        lg.setPixmap(logo_pixmap(34))
        bt = QVBoxLayout()
        bt.setSpacing(0)
        n = QLabel("FATE AI")
        n.setObjectName("Brand")
        s = QLabel("LOCAL-FIRST AI")
        s.setObjectName("BrandSub")
        bt.addWidget(n)
        bt.addWidget(s)
        brand.addWidget(lg)
        brand.addLayout(bt)
        brand.addStretch(1)
        sl.addLayout(brand)
        sl.addSpacing(14)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setIconSize(QSize(18, 18))
        for key, label, ic in NAV:
            it = QListWidgetItem(icon(ic), "  " + label)
            it.setData(Qt.UserRole, key)
            self.nav.addItem(it)
        self.nav.currentRowChanged.connect(self._nav_changed)
        sl.addWidget(self.nav, 1)
        self.bg_status = QLabel("")
        self.bg_status.setObjectName("Dim")
        self.bg_status.setWordWrap(True)
        sl.addWidget(self.bg_status)
        ver = QLabel(f"v{__version__} · data stays on this PC")
        ver.setObjectName("Dim")
        sl.addWidget(ver)
        root.addWidget(side)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.pages: dict[str, QWidget] = {}
        self._factories = self._page_factories()
        for key, _, _ in NAV:
            placeholder = QWidget()
            self.pages[key] = placeholder
            self.stack.addWidget(placeholder)
        self.statusBar().showMessage("Ready")
        self._tray()
        self.bg_timer = QTimer(self, interval=15000, timeout=self._bg_check)
        self.bg_timer.start()
        self.navigate("home")

    def _page_factories(self):
        from .pages import (about, api_keys, chat, comparison, devtools, hardware, home, models, projects, prompts,
                            providers, sandbox, security, settings, usage, vms)
        c = self.ctx
        return {
            "home": lambda: home.HomePage(c, self.navigate),
            "chat": lambda: chat.ChatPage(c),
            "models": lambda: models.ModelsPage(c),
            "providers": lambda: providers.ProvidersPage(c),
            "keys": lambda: api_keys.APIKeysPage(c),
            "vms": lambda: vms.VMsPage(c),
            "sandbox": lambda: sandbox.SandboxPage(c),
            "projects": lambda: self._projects_page(projects),
            "prompts": lambda: prompts.PromptsPage(c, use_in_chat=self._use_prompt),
            "compare": lambda: comparison.ComparisonPage(c),
            "usage": lambda: usage.UsagePage(c),
            "hardware": lambda: hardware.HardwarePage(c),
            "dev": lambda: devtools.DevToolsPage(c),
            "security": lambda: security.SecurityPage(c),
            "settings": lambda: settings.SettingsPage(c, on_delete_all=self.delete_all_data),
            "about": lambda: about.AboutPage(c),
        }

    def _projects_page(self, mod):
        p = mod.ProjectsPage(self.ctx)
        b = QPushButton("Manage agents")
        b.clicked.connect(self._agents)
        p.header_actions.insertWidget(0, b)
        return p

    def _agents(self):
        from .dialogs.agents import AgentsDialog
        AgentsDialog(self.ctx, self).exec()
        page = self.pages.get("projects")
        if hasattr(page, "on_show"):
            page.on_show()

    def page(self, key: str):
        """Create pages lazily the first time they are opened (fast start-up)."""
        w = self.pages[key]
        if type(w) is QWidget:
            idx = self.stack.indexOf(w)
            try:
                real = self._factories[key]()
            except Exception as e:  # never crash the app because one page failed
                log.exception("failed to build page %s", key)
                real = QLabel(f"This page failed to load: {e}")
                real.setAlignment(Qt.AlignCenter)
            self.stack.removeWidget(w)
            w.deleteLater()
            self.stack.insertWidget(idx, real)
            self.pages[key] = real
            w = real
        return w

    def navigate(self, key: str):
        row = next(i for i, (k, _, _) in enumerate(NAV) if k == key)
        if self.nav.currentRow() != row:
            self.nav.setCurrentRow(row)
        else:
            self._nav_changed(row)

    def _nav_changed(self, row):
        key = NAV[row][0]
        w = self.page(key)
        self.stack.setCurrentWidget(w)
        if hasattr(w, "on_show"):
            try:
                w.on_show()
            except Exception:
                log.exception("on_show failed for %s", key)

    def _use_prompt(self, text):
        self.navigate("chat")
        self.page("chat").use_prompt(text)

    # -- tray & background operation ---------------------------------------
    def _tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        m = QMenu()
        m.addAction("Open FATE AI", self._restore)
        m.addAction("New chat", lambda: (self._restore(), self.navigate("chat")))
        m.addSeparator()
        m.addAction("Emergency stop all VMs & sandboxes", self.emergency_stop)
        m.addSeparator()
        m.addAction("Quit FATE AI", self.quit_app)
        self.tray.setContextMenu(m)
        self.tray.setToolTip("FATE AI")
        self.tray.activated.connect(lambda r: self._restore() if r == QSystemTrayIcon.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _bg_check(self):
        if self.ctx._vm_manager is None:
            return
        from .components.worker import run_async
        run_async(self.ctx.vm_manager.running, on_done=lambda vms: self.bg_status.setText(
            f"● {len(vms)} VM/container(s) running" if vms else ""))

    def emergency_stop(self):
        self.ctx.sandboxes.stop_all()
        if self.ctx._vm_manager is not None:
            errs = self.ctx.vm_manager.stop_all(force=True)
            if errs:
                QMessageBox.warning(self, "Emergency stop", "Some environments could not be stopped:\n" + "\n".join(errs))
        self.statusBar().showMessage("Emergency stop complete.", 5000)

    def quit_app(self):
        self._really_quit = True
        self.close()

    def closeEvent(self, e: QCloseEvent):
        s = self.ctx.settings.settings
        if not self._really_quit and s.general.minimize_to_tray and QSystemTrayIcon.isSystemTrayAvailable():
            e.ignore()
            self.hide()
            if s.general.notifications:
                self.tray.showMessage("FATE AI is still running", "Running VMs and tasks continue. Right-click the "
                                      "tray icon to quit or stop everything.", QSystemTrayIcon.Information, 4000)
            return
        running = []
        if self.ctx._vm_manager is not None:
            try:
                running = self.ctx.vm_manager.running()
            except Exception:
                running = []
        if running:
            box = QMessageBox(self)
            box.setWindowTitle("Virtual machines are running")
            box.setText(f"{len(running)} VM/container(s) are running: {', '.join(v.name for v in running)}.\n\n"
                        "Closing FATE AI does not stop them — they keep running in the background.")
            keep = box.addButton("Quit, keep them running", QMessageBox.AcceptRole)
            stop = box.addButton("Stop them and quit", QMessageBox.DestructiveRole)
            cancel = box.addButton("Cancel", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is cancel:
                self._really_quit = False
                e.ignore()
                return
            if box.clickedButton() is stop:
                self.ctx.vm_manager.stop_all(force=False)
            del keep
        self.tray.hide()
        e.accept()
        QApplication.instance().quit()

    def delete_all_data(self):
        try:
            self.ctx.delete_all_local_data()
        finally:
            QMessageBox.information(self, "FATE AI", "All local data has been deleted. FATE AI will now close.")
            self._really_quit = True
            self.tray.hide()
            QApplication.instance().quit()
