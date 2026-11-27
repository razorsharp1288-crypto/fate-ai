from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QMessageBox, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from .. import __version__
from .components.icons import app_icon, icon, logo_pixmap

log = logging.getLogger(__name__)

NAV = [
    ("home", "Home", "home"), ("chat", "Chat", "chat"), ("computer", "PC Control", "cursor"),
    ("blueprints", "Blueprints", "blueprint"),
    ("projects", "Projects", "projects"), ("prompts", "Prompt Library", "prompts"),
    ("models", "AI Models", "models"), ("providers", "Providers", "providers"), ("keys", "API Keys", "key"),
    ("compare", "Model Comparison", "compare"),
    ("vms", "Virtual Machines", "vm"), ("sandbox", "Sandbox", "sandbox"),
    ("usage", "Usage Dashboard", "usage"), ("hardware", "Hardware Monitor", "hardware"),
    ("dev", "Developer Tools", "dev"), ("security", "Security Center", "security"),
    ("settings", "Settings", "settings"), ("about", "About FATE AI", "about"),
]
SECTION_BEFORE = {"home": "CREATE", "models": "AI", "vms": "RUN & TEST", "usage": "SYSTEM"}


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
        sl.addSpacing(10)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setIconSize(QSize(18, 18))
        self._row_of: dict[str, int] = {}
        for key, label, ic in NAV:
            if key in SECTION_BEFORE:
                h = QListWidgetItem(SECTION_BEFORE[key])
                h.setFlags(Qt.NoItemFlags)
                f = h.font()
                f.setPointSizeF(7.5)
                f.setBold(True)
                f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 1.5)
                h.setFont(f)
                h.setForeground(QColor("#6B6485"))
                h.setSizeHint(QSize(10, 30))
                self.nav.addItem(h)
            it = QListWidgetItem(icon(ic), "  " + label)
            it.setData(Qt.UserRole, key)
            self._row_of[key] = self.nav.count()
            self.nav.addItem(it)
        search = QPushButton("  Search or jump…   Ctrl+K")
        search.setObjectName("Ghost")
        search.setStyleSheet("text-align:left; border:1px solid #2A2440; border-radius:8px; padding:7px 10px;")
        search.clicked.connect(self.command_palette)
        self._search_btn = search
        self.nav.currentRowChanged.connect(self._nav_changed)
        sl.addWidget(self._search_btn)
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
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.command_palette)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: (self.navigate("chat"), self.page("chat").new_chat()))
        for i, (key, _, _) in enumerate(NAV[:9]):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda k=key: self.navigate(k))
        self._tray()
        self.bg_timer = QTimer(self, interval=15000, timeout=self._bg_check)
        self.bg_timer.start()
        # automatic update checks: shortly after start, then every N hours
        self._update_info = None
        self.update_btn = QPushButton("  Update available")
        self.update_btn.setIcon(icon("update", "#FFFFFF"))
        self.update_btn.setObjectName("Primary")
        self.update_btn.hide()
        self.update_btn.clicked.connect(self.show_update)
        side.layout().insertWidget(side.layout().count() - 2, self.update_btn)
        hours = self.ctx.settings.settings.advanced.update_check_hours
        self.update_timer = QTimer(self, interval=hours * 3600 * 1000, timeout=self.check_updates_background)
        if self.ctx.settings.settings.advanced.auto_update_check:
            self.update_timer.start()
            QTimer.singleShot(20000, self.check_updates_background)
        self.navigate("home")

    def _page_factories(self):
        from .pages import (about, api_keys, blueprints, chat, computer, comparison, devtools, hardware, home, models, projects, prompts,
                            providers, sandbox, security, settings, usage, vms)
        c = self.ctx
        return {
            "home": lambda: home.HomePage(c, self.navigate),
            "chat": lambda: chat.ChatPage(c),
            "blueprints": lambda: blueprints.BlueprintsPage(c),
            "computer": lambda: computer.ComputerPage(c),
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
        row = self._row_of[key]
        if self.nav.currentRow() != row:
            self.nav.setCurrentRow(row)
        else:
            self._nav_changed(row)

    def _nav_changed(self, row):
        it = self.nav.item(row)
        key = it.data(Qt.UserRole) if it else None
        if not key:
            return
        w = self.page(key)
        self.stack.setCurrentWidget(w)
        if hasattr(w, "on_show"):
            try:
                w.on_show()
            except Exception:
                log.exception("on_show failed for %s", key)

    def command_palette(self):
        from .dialogs.command_palette import CommandPalette
        commands = [(f"Go to {label}", lambda k=key: self.navigate(k)) for key, label, _ in NAV]
        commands += [
            ("New chat", lambda: (self.navigate("chat"), self.page("chat").new_chat())),
            ("New blueprint", lambda: (self.navigate("blueprints"), self.page("blueprints").new())),
            ("Add an AI service / API key", lambda: self.navigate("keys")),
            ("Download a local model", lambda: self.navigate("models")),
            ("Check for updates", self.check_updates_now),
            ("Emergency stop all VMs & sandboxes", self.emergency_stop),
        ]
        for c in self.ctx.conversations.list()[:30]:
            commands.append((f"Open chat: {c.title}", lambda cid=c.id: (self.navigate("chat"),
                                                                       self.page("chat").open_conversation(cid))))
        CommandPalette(commands, self).exec()

    def _updater(self):
        from ..updater.updater import Updater
        return Updater(self.ctx.settings.settings.advanced.update_repository, self.ctx.paths.updates)

    def check_updates_background(self, manual: bool = False):
        from .components.worker import run_async
        adv = self.ctx.settings.settings.advanced
        if not manual and not adv.auto_update_check:
            return
        up = self._updater()

        def done(info):
            if not info.available:
                if manual:
                    self.toast(f"You're up to date (FATE AI {info.current}).")
                return
            if not manual and info.latest == adv.skipped_version:
                return
            self._update_info = (up, info)
            self.update_btn.setText(f"  Update to {info.latest}")
            self.update_btn.show()
            if manual or not self.isVisible():
                self.show_update()
            else:
                self.toast(f"FATE AI {info.latest} is available — click “Update” in the sidebar.", 7000)
            if self.ctx.settings.settings.general.notifications and self.tray.isVisible():
                self.tray.showMessage("FATE AI update available", f"Version {info.latest} is ready to install.",
                                      QSystemTrayIcon.Information, 6000)

        def fail(e):
            log.info("update check failed: %s", e)
            if manual:
                self.toast(f"Update check failed: {e}", 6000)
        run_async(lambda: up.check(adv.update_channel == "beta"), on_done=done, on_error=fail)

    def check_updates_now(self):
        self.check_updates_background(manual=True)

    def show_update(self):
        if not self._update_info:
            self.check_updates_now()
            return
        from .dialogs.update import UpdateDialog
        up, info = self._update_info
        self._restore()
        UpdateDialog(self.ctx, up, info, self).exec()

    def toast(self, text: str, ms: int = 4000):
        from .components.toast import Toast
        Toast(self, text, ms)

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
        m.addAction("Check for updates", self.check_updates_now)
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
