"""Curated local model catalogue with hardware-based recommendations.

Sizes are approximate download sizes of the default Ollama quantisation
(usually Q4_K_M). Memory needs are estimates: weights + KV cache + overhead.
Availability of a tag in the Ollama library can change; the UI reports pull
errors from Ollama verbatim rather than assuming success.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogModel:
    tag: str
    family: str
    params_b: float
    download_gb: float
    tier: str  # lightweight | balanced | high
    description: str

    @property
    def est_ram_gb(self) -> float:
        """RAM needed for CPU-only inference (weights + ~20% + 1 GB runtime)."""
        return round(self.download_gb * 1.2 + 1.0, 1)

    @property
    def est_vram_gb(self) -> float:
        """VRAM for full GPU offload at moderate context."""
        return round(self.download_gb * 1.15 + 0.6, 1)


CATALOG: list[CatalogModel] = [
    CatalogModel("qwen2.5:0.5b", "Qwen", 0.5, 0.4, "lightweight", "Tiny, fast; simple tasks and testing."),
    CatalogModel("llama3.2:1b", "Llama", 1.2, 1.3, "lightweight", "Meta's small model for low-end PCs."),
    CatalogModel("gemma2:2b", "Gemma", 2.6, 1.6, "lightweight", "Google's compact model, good quality for size."),
    CatalogModel("llama3.2:3b", "Llama", 3.2, 2.0, "lightweight", "Good general assistant on modest hardware."),
    CatalogModel("phi3:mini", "Phi", 3.8, 2.2, "lightweight", "Microsoft Phi-3 Mini; reasoning for its size."),
    CatalogModel("qwen2.5:7b", "Qwen", 7.6, 4.7, "balanced", "Strong multilingual all-rounder."),
    CatalogModel("qwen2.5-coder:7b", "Qwen", 7.6, 4.7, "balanced", "Code generation and review."),
    CatalogModel("llama3.1:8b", "Llama", 8.0, 4.9, "balanced", "Popular general-purpose 8B model."),
    CatalogModel("mistral:7b", "Mistral", 7.2, 4.1, "balanced", "Efficient general model from Mistral AI."),
    CatalogModel("gemma2:9b", "Gemma", 9.2, 5.4, "balanced", "High quality mid-size Google model."),
    CatalogModel("deepseek-r1:8b", "DeepSeek", 8.0, 4.9, "balanced", "Distilled reasoning model (thinks aloud)."),
    CatalogModel("phi4:14b", "Phi", 14.7, 9.1, "high", "Microsoft Phi-4, strong reasoning."),
    CatalogModel("qwen2.5:14b", "Qwen", 14.8, 9.0, "high", "Larger Qwen for better quality."),
    CatalogModel("deepseek-r1:14b", "DeepSeek", 14.8, 9.0, "high", "Larger distilled reasoning model."),
    CatalogModel("mistral-small:24b", "Mistral", 24.0, 14.0, "high", "Mistral Small 3, workstation class."),
    CatalogModel("gemma2:27b", "Gemma", 27.0, 16.0, "high", "Large Gemma 2 for high-end GPUs."),
    CatalogModel("qwen2.5:32b", "Qwen", 32.8, 20.0, "high", "Needs 24 GB VRAM or lots of RAM."),
    CatalogModel("llama3.3:70b", "Llama", 70.6, 43.0, "high", "Very large; 48 GB+ VRAM or 64 GB+ RAM."),
]


@dataclass
class Fit:
    model: CatalogModel
    verdict: str  # "gpu", "cpu", "tight", "too_large"
    reason: str


def assess(model: CatalogModel, ram_total_gb: float, ram_available_gb: float, vram_gb: float | None,
           free_disk_gb: float | None) -> Fit:
    if free_disk_gb is not None and free_disk_gb < model.download_gb * 1.1:
        return Fit(model, "too_large", f"Needs ~{model.download_gb} GB disk; {free_disk_gb:.1f} GB free.")
    if vram_gb and vram_gb >= model.est_vram_gb:
        return Fit(model, "gpu", f"Fits in GPU memory ({model.est_vram_gb} of {vram_gb:.1f} GB VRAM).")
    if ram_total_gb >= model.est_ram_gb * 1.5:
        return Fit(model, "cpu", f"Runs on CPU/RAM (~{model.est_ram_gb} GB); slower than GPU.")
    if ram_total_gb >= model.est_ram_gb:
        return Fit(model, "tight", f"May run but will use most of your {ram_total_gb:.0f} GB RAM.")
    return Fit(model, "too_large", f"Needs ~{model.est_ram_gb} GB RAM; you have {ram_total_gb:.0f} GB.")


def recommended_tier(ram_total_gb: float, vram_gb: float | None) -> str:
    if (vram_gb or 0) >= 12 or ram_total_gb >= 32:
        return "high"
    if (vram_gb or 0) >= 6 or ram_total_gb >= 16:
        return "balanced"
    return "lightweight"


def recommendations(hw) -> list[Fit]:
    """Return catalogue entries assessed against detected hardware ``hw`` (HardwareSnapshot)."""
    vram = hw.best_gpu_vram_gb
    disk = hw.storage[0].free_gb if hw.storage else None
    return [assess(m, hw.memory.total_gb, hw.memory.available_gb, vram, disk) for m in CATALOG]
