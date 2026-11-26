from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QLabel, QSpinBox

from ...hardware.detection import detect_all
from ...monitoring.collector import MetricsCollector
from ..components.widgets import Card, LineChart, Page, hbox
from ..components.worker import run_async
from ..theme import C


def _v(x, unit=""):
    return "Unavailable" if x is None or x == "" else f"{x}{unit}"


class HardwarePage(Page):
    def __init__(self, ctx):
        super().__init__("Hardware Monitor", "Live resource usage and detected hardware. Values that Windows does "
                                             "not expose are shown as unavailable — never guessed.")
        self.ctx = ctx
        self.collector = MetricsCollector()
        self.interval = QSpinBox()
        self.interval.setRange(250, 60000)
        self.interval.setSingleStep(250)
        self.interval.setSuffix(" ms")
        self.interval.setValue(ctx.settings.settings.resources.monitor_interval_ms)
        self.interval.valueChanged.connect(self._interval)
        self.header_actions.addWidget(QLabel("Refresh every"))
        self.header_actions.addWidget(self.interval)

        g = QGridLayout()
        self.cpu = LineChart("CPU", color=C["accent"])
        self.ram = LineChart("Memory", color="#C084FC")
        self.gpu = LineChart("GPU", color="#F472B6")
        self.vram = LineChart("VRAM", unit=" GB", maximum=None, color="#60A5FA")
        self.disk = LineChart("Disk I/O", unit=" MB/s", maximum=None, color="#34D399")
        self.net = LineChart("Network", unit=" KB/s", maximum=None, color="#FBBF24")
        for i, w in enumerate((self.cpu, self.ram, self.gpu, self.vram, self.disk, self.net)):
            g.addWidget(w, i // 3, i % 3)
        self.body.addLayout(g)

        self.app = QLabel("")
        self.app.setObjectName("Muted")
        self.body.addWidget(self.app)
        self.workloads = Card("FATE AI workloads")
        self.workload_label = QLabel("…")
        self.workload_label.setWordWrap(True)
        self.workloads.add(self.workload_label)
        self.body.addWidget(self.workloads)

        self.hw_card = Card("Detected hardware")
        self.hw_grid = QGridLayout()
        self.hw_card.add(self.hw_grid)
        self.body.addWidget(self.hw_card)
        self.timer = QTimer(self, timeout=self.tick)
        self._interval(self.interval.value())
        self.slow = QTimer(self, interval=10000, timeout=self.workload_tick)
        run_async(detect_all, on_done=self._hw)

    def _interval(self, v):
        self.timer.setInterval(v)
        self.ctx.settings.update(resources={"monitor_interval_ms": v})

    def on_show(self):
        self.timer.start()
        self.slow.start()
        self.workload_tick()

    def hideEvent(self, e):
        # stop polling when not visible to avoid unnecessary background work
        self.timer.stop()
        self.slow.stop()
        super().hideEvent(e)

    def tick(self):
        s = self.collector.sample()
        self.cpu.push(s.cpu_percent)
        self.ram.push(s.ram_percent, f"{s.ram_used_gb:.1f} GB used")
        self.gpu.push(s.gpu_percent, "" if s.gpu_percent is not None else "NVIDIA only")
        self.vram.push(s.vram_used_gb, f"of {s.vram_total_gb:.1f} GB" if s.vram_total_gb else "")
        self.disk.push(s.disk_read_mb_s + s.disk_write_mb_s, f"R {s.disk_read_mb_s:.1f} / W {s.disk_write_mb_s:.1f}")
        self.net.push(s.net_recv_kb_s + s.net_sent_kb_s, f"↓ {s.net_recv_kb_s:.0f} / ↑ {s.net_sent_kb_s:.0f}")
        self.app.setText(f"FATE AI and its child processes: {s.app_cpu_percent:.1f}% CPU · {s.app_ram_mb:.0f} MB RAM")

    def workload_tick(self):
        def work():
            out = []
            try:
                o = self.ctx.providers.get("ollama")
                if o.version():
                    ms = o.running_models()
                    out.append("Local models loaded: " + (", ".join(m["name"] for m in ms) or "none"))
                else:
                    out.append("Local models: Ollama not running")
            except Exception as e:
                out.append(f"Local models: {e}")
            if self.ctx._vm_manager is not None:
                vms = self.ctx.vm_manager.running()
                out.append("Running VMs/containers: " + (", ".join(f"{v.name} ({v.backend})" for v in vms) or "none"))
            else:
                out.append("Running VMs/containers: open the Virtual Machines page to detect")
            tasks = self.ctx.tasks.active()
            out.append(f"Active sandboxes: {len(self.ctx.sandboxes._active)} · background tasks: {len(tasks)}")
            return "<br>".join(out)
        run_async(work, on_done=self.workload_label.setText)

    def _hw(self, hw):
        rows = [
            ("CPU", f"{_v(hw.cpu.model)} · {_v(hw.cpu.vendor)}"),
            ("Cores / threads", f"{_v(hw.cpu.physical_cores)} / {_v(hw.cpu.logical_threads)}"),
            ("Frequency", f"{_v(hw.cpu.freq_mhz, ' MHz')} (max {_v(hw.cpu.max_freq_mhz, ' MHz')})"),
            ("Memory", f"{hw.memory.total_gb:.1f} GB total · {hw.memory.available_gb:.1f} GB available"),
        ]
        if hw.gpus:
            for g in hw.gpus:
                rows.append((f"GPU {g.index}", f"{g.name} · {_v(g.vendor)} · VRAM {_v(g.vram_total_gb, ' GB')} · "
                                               f"temp {_v(g.temperature_c, ' °C')} · driver {_v(g.driver)} ({g.source})"))
        else:
            rows.append(("GPU", "No GPU detected or details unavailable"))
        for s in hw.storage:
            rows.append((f"Disk {s.mount}", f"{s.free_gb:.0f} GB free of {s.total_gb:.0f} GB"))
        rows += [
            ("System", f"{hw.system.os_name} {hw.system.os_build or ''} · {hw.system.architecture}"),
            ("Acceleration", ", ".join(hw.acceleration) or "None detected"),
            ("Virtualization", f"CPU support {_v(hw.virtualization.cpu_supports)} · hypervisor present "
                               f"{_v(hw.virtualization.hypervisor_present)} · Hyper-V {_v(hw.virtualization.hyperv_available)}"
                               f" · WSL {_v(hw.virtualization.wsl_available)}"),
        ]
        for i, (k, v) in enumerate(rows):
            a = QLabel(k)
            a.setObjectName("Muted")
            b = QLabel(v)
            b.setWordWrap(True)
            self.hw_grid.addWidget(a, i, 0)
            self.hw_grid.addWidget(b, i, 1)
        self.hw_grid.setColumnStretch(1, 1)
