"""Resource presets and enforcement for FATE-managed workloads.

Enforced (really applied):
* Ollama inference: ``num_thread`` and ``num_gpu`` options per request.
* Sandboxes: CPU/memory/process caps (Job Object / rlimits / container flags).
* VMs/containers: vCPU count, RAM, CPU execution cap (VirtualBox/Hyper-V).
* FATE AI's own process priority.
Estimates only (shown, not enforced): global GPU %, VRAM budgets for cloud models.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    max_cpu_percent: int
    ram_fraction: float
    background_priority: str
    description: str


PRESETS = {
    "low": Preset("low", "Low resource", 25, 0.25, "low",
                  "Minimal background usage; your other apps come first."),
    "balanced": Preset("balanced", "Balanced", 60, 0.5, "low",
                       "Reasonable AI workloads while keeping Windows responsive."),
    "high": Preset("high", "High performance", 90, 0.75, "normal",
                   "More resources for local inference, development and testing."),
    "max": Preset("max", "Maximum — use everything", 100, 0.9, "high",
                  "All CPU threads, every GPU layer and high priority for FATE AI. Other apps may slow down."),
}

ENFORCEMENT = [
    ("Local inference CPU threads (Ollama num_thread)", True),
    ("Sandbox CPU / memory / process caps", True),
    ("VM & container vCPU / RAM allocation", True),
    ("VM CPU execution cap (VirtualBox, Hyper-V)", True),
    ("FATE AI process priority", True),
    ("Global RAM budget for new VMs/sandboxes (validation)", True),
    ("GPU usage percentage", False),
    ("VRAM budget (estimate for model recommendations)", False),
]


def apply_preset(settings_store, key: str) -> None:
    p = PRESETS[key]
    total_mb = psutil.virtual_memory().total // 2 ** 20
    budget = int(total_mb * p.ram_fraction)
    if key == "max":
        budget = max(256, total_mb - 2048)  # everything except what Windows itself needs
    settings_store.update(resources={"preset": key, "max_cpu_percent": p.max_cpu_percent, "ram_budget_mb": budget,
                                     "background_priority": p.background_priority},
                          local={"num_gpu_layers": 999 if key == "max" else None})
    set_own_priority(p.background_priority)


def inference_threads(max_cpu_percent: int) -> int:
    logical = psutil.cpu_count(logical=True) or 1
    return max(1, round(logical * max_cpu_percent / 100))


def ollama_options(settings) -> dict:
    opts = {"num_thread": inference_threads(settings.resources.max_cpu_percent)}
    if settings.local.num_gpu_layers is not None:
        opts["num_gpu"] = settings.local.num_gpu_layers
    if settings.resources.gpu_index is not None:
        opts["main_gpu"] = settings.resources.gpu_index
    return opts


def set_own_priority(level: str) -> bool:
    try:
        p = psutil.Process()
        if sys.platform == "win32":
            mapping = {"low": psutil.BELOW_NORMAL_PRIORITY_CLASS, "normal": psutil.NORMAL_PRIORITY_CLASS,
                       "high": psutil.ABOVE_NORMAL_PRIORITY_CLASS}
            p.nice(mapping[level])
        else:
            target = {"low": 10, "normal": 0, "high": 0}[level]
            if target >= p.nice():
                p.nice(target)
        return True
    except (psutil.Error, OSError, KeyError):
        return False


def sandbox_cpu_cores(max_cpu_percent: int) -> float:
    logical = psutil.cpu_count(logical=True) or 1
    return round(max(0.5, logical * max_cpu_percent / 100), 1)
