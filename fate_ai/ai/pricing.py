"""Estimated API cost from a user-editable pricing table.

Prices change often. The bundled table is a starting point with an ``as_of``
date; users can edit ``pricing.json`` in their data folder. Costs are always
displayed as *estimates* — only the provider's own billing is authoritative.
"""
from __future__ import annotations

import json
from pathlib import Path

# USD per 1M tokens: (input, output). Verify against provider pricing pages.
BUNDLED = {
    "as_of": "2025-06",
    "note": "Estimates only. Edit this file to match current provider pricing.",
    "models": {
        "openai:gpt-4o": [2.50, 10.00],
        "openai:gpt-4o-mini": [0.15, 0.60],
        "openai:gpt-4.1": [2.00, 8.00],
        "openai:gpt-4.1-mini": [0.40, 1.60],
        "openai:gpt-4.1-nano": [0.10, 0.40],
        "anthropic:claude-3-5-haiku": [0.80, 4.00],
        "anthropic:claude-sonnet-4": [3.00, 15.00],
        "anthropic:claude-opus-4": [15.00, 75.00],
    },
}


class PricingTable:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.data = BUNDLED
        if path is not None:
            if path.exists():
                try:
                    self.data = json.loads(path.read_text("utf-8"))
                except (OSError, json.JSONDecodeError):
                    self.data = BUNDLED
            else:
                try:
                    path.write_text(json.dumps(BUNDLED, indent=2), "utf-8")
                except OSError:
                    pass

    def price(self, kind: str, model: str) -> tuple[float, float] | None:
        models = self.data.get("models", {})
        key = f"{kind}:{model}"
        if key in models:
            return tuple(models[key])
        # longest prefix match handles dated snapshots, e.g. gpt-4o-2024-08-06
        best = None
        for k, v in models.items():
            if key.startswith(k) and (best is None or len(k) > len(best[0])):
                best = (k, v)
        return tuple(best[1]) if best else None

    def estimate(self, kind: str, model: str, input_tokens: int, output_tokens: int) -> float | None:
        p = self.price(kind, model)
        if p is None:
            return None
        return (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000
