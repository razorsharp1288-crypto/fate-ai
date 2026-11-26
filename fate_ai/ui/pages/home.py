from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton

from ...ai.providers.registry import KINDS
from ...hardware.detection import detect_cpu, detect_gpus, detect_memory
from ..components.icons import icon
from ..components.widgets import Card, Page, StatTile, hbox
from ..components.worker import run_async


class HomePage(Page):
    def __init__(self, ctx, navigate):
        super().__init__("", "")
        self.ctx = ctx
        self.navigate = navigate
        hero = Card(accent=True)
        self.greet = QLabel()
        self.greet.setObjectName("PageTitle")
        sub = QLabel("Your private AI workstation — chat, local models, sandboxes and virtual machines in one place.")
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        hero.add(self.greet)
        hero.add(sub)
        actions = QHBoxLayout()
        for label, page, ic, primary in (("New chat", "chat", "chat", True), ("Get a local model", "models", "models", False),
                                         ("Add API key", "keys", "key", False), ("Open sandbox", "sandbox", "sandbox", False),
                                         ("Virtual machines", "vms", "vm", False)):
            b = QPushButton(" " + label)
            b.setIcon(icon(ic, "#FFFFFF" if primary else "#B8B0D6"))
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(lambda _=False, p=page: self.navigate(p))
            actions.addWidget(b)
        actions.addStretch(1)
        hero.add(actions)
        self.body.addWidget(hero)

        g = QGridLayout()
        self.t_conv = StatTile("Conversations")
        self.t_prov = StatTile("Cloud providers ready")
        self.t_local = StatTile("Local models")
        self.t_vms = StatTile("Running VMs")
        for i, t in enumerate((self.t_conv, self.t_prov, self.t_local, self.t_vms)):
            g.addWidget(t, 0, i)
        self.body.addLayout(g)

        row = QHBoxLayout()
        self.sys_card = Card("This PC")
        self.sys_label = QLabel("Detecting…")
        self.sys_label.setWordWrap(True)
        self.sys_card.add(self.sys_label)
        hw_btn = QPushButton("Hardware monitor")
        hw_btn.clicked.connect(lambda: self.navigate("hardware"))
        self.sys_card.add(hbox(hw_btn, None))
        row.addWidget(self.sys_card, 1)
        self.recent = Card("Recent chats")
        self.recent_label = QLabel("")
        self.recent_label.setWordWrap(True)
        self.recent.add(self.recent_label)
        row.addWidget(self.recent, 1)
        self.body.addLayout(row)
        self.bg = Card("Background activity")
        self.bg_label = QLabel("")
        self.bg_label.setWordWrap(True)
        self.bg.add(self.bg_label)
        self.body.addWidget(self.bg)
        self.body.addStretch(1)

    def on_show(self):
        h = datetime.now().hour
        self.greet.setText("Good " + ("morning" if h < 12 else "afternoon" if h < 18 else "evening") + ".")
        convs = self.ctx.conversations.list()
        self.t_conv.set(str(len(convs)))
        cloud = [p for p in self.ctx.providers.configs() if not KINDS[p["kind"]].is_local]
        ready = sum(1 for p in cloud if self.ctx.credentials.has_api_key(p["id"]))
        self.t_prov.set(f"{ready} / {len(cloud)}", "keys configured")
        self.recent_label.setText("<br>".join(f"• {c.title} <span style='color:#6B6485'>({c.model})</span>"
                                              for c in convs[:6]) or "No chats yet.")

        def work():
            o = self.ctx.providers.get("ollama")
            n = len(o.list_models()) if o.version() else None
            cpu, mem, gpus = detect_cpu(sample=False), detect_memory(), detect_gpus()
            vms = self.ctx.vm_manager.running() if self.ctx._vm_manager is not None else None
            return n, cpu, mem, gpus, vms

        def done(r):
            n, cpu, mem, gpus, vms = r
            self.t_local.set("—" if n is None else str(n), "Ollama not running" if n is None else "installed")
            self.t_vms.set("—" if vms is None else str(len(vms)), "open VM page to detect" if vms is None else "")
            gpu = ", ".join(f"{g.name}" + (f" ({g.vram_total_gb:.0f} GB)" if g.vram_total_gb else "") for g in gpus)
            self.sys_label.setText(f"<b>CPU</b> {cpu.model or 'Unknown'} · {cpu.physical_cores or '?'} cores / "
                                   f"{cpu.logical_threads} threads<br><b>RAM</b> {mem.total_gb:.1f} GB "
                                   f"({mem.available_gb:.1f} GB free)<br><b>GPU</b> {gpu or 'none detected'}")
            act = []
            if vms:
                act.append("VMs running in the background: " + ", ".join(v.name for v in vms))
            if self.ctx.sandboxes._active:
                act.append(f"{len(self.ctx.sandboxes._active)} sandbox run(s) in progress")
            self.bg_label.setText("<br>".join(act) or "Nothing running in the background.")
        run_async(work, on_done=done)
