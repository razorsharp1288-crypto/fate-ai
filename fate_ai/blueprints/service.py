"""Blueprint persistence, import/export."""
from __future__ import annotations

import json
from pathlib import Path

from ..core.exceptions import ValidationError
from .geometry import Part, export_obj, export_stl, sanitize
from .generator import spec_markdown


class BlueprintService:
    FORMAT = "fate-ai-blueprint"

    def __init__(self, db, audit=None):
        self.db = db
        self.audit = audit

    def create(self, name: str, category: str = "General", prompt: str = "", spec: dict | None = None,
               parts: list[Part] | None = None) -> int:
        return self.db.execute(
            "INSERT INTO blueprints(name, category, prompt, spec_json, parts_json) VALUES (?,?,?,?,?)",
            (name[:120] or "Untitled", category[:60], prompt, json.dumps(spec or {}),
             json.dumps([p.to_dict() for p in parts or []]))).lastrowid

    def save(self, bid: int, **f) -> None:
        cols, vals = [], []
        for k in ("name", "category", "prompt", "notes"):
            if k in f:
                cols.append(f"{k}=?")
                vals.append(str(f[k]))
        if "spec" in f:
            cols.append("spec_json=?")
            vals.append(json.dumps(f["spec"]))
        if "parts" in f:
            cols.append("parts_json=?")
            vals.append(json.dumps([p.to_dict() for p in f["parts"]]))
        if cols:
            self.db.execute(f"UPDATE blueprints SET {', '.join(cols)}, updated_at=datetime('now') WHERE id=?",
                            (*vals, bid))

    def get(self, bid: int) -> dict | None:
        r = self.db.one("SELECT * FROM blueprints WHERE id=?", (bid,))
        if not r:
            return None
        d = dict(r)
        d["spec"] = json.loads(d.pop("spec_json") or "{}")
        d["parts"] = sanitize(json.loads(d.pop("parts_json") or "[]"))
        return d

    def list(self, search: str = "") -> list[dict]:
        sql = "SELECT id, name, category, updated_at FROM blueprints"
        params: tuple = ()
        if search:
            sql += " WHERE name LIKE ? OR category LIKE ? OR prompt LIKE ?"
            params = (f"%{search}%",) * 3
        return [dict(r) for r in self.db.query(sql + " ORDER BY updated_at DESC, id DESC", params)]

    def delete(self, bid: int) -> None:
        self.db.execute("DELETE FROM blueprints WHERE id=?", (bid,))

    def duplicate(self, bid: int) -> int:
        b = self.get(bid)
        return self.create(b["name"] + " (copy)", b["category"], b["prompt"], b["spec"], b["parts"])

    # -- files ---------------------------------------------------------------
    def export_file(self, bid: int, path: Path) -> Path:
        b = self.get(bid)
        data = {"format": self.FORMAT, "version": 1, "name": b["name"], "category": b["category"],
                "prompt": b["prompt"], "notes": b["notes"], "spec": b["spec"], "parts": [p.to_dict() for p in b["parts"]]}
        Path(path).write_text(json.dumps(data, indent=2), "utf-8")
        return Path(path)

    def import_file(self, path: Path) -> int:
        try:
            data = json.loads(Path(path).read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ValidationError(f"Not a readable blueprint file: {e}") from None
        if data.get("format") != self.FORMAT:
            raise ValidationError("Not a FATE AI blueprint file.")
        return self.create(str(data.get("name", "Imported")), str(data.get("category", "General")),
                           str(data.get("prompt", "")), data.get("spec") if isinstance(data.get("spec"), dict) else {},
                           sanitize(data.get("parts")))

    def export_stl(self, bid: int, path: Path) -> int:
        b = self.get(bid)
        return export_stl(b["parts"], Path(path), b["name"])

    def export_obj(self, bid: int, path: Path) -> Path:
        return export_obj(self.get(bid)["parts"], Path(path))

    def export_markdown(self, bid: int, path: Path) -> Path:
        b = self.get(bid)
        spec = dict(b["spec"])
        spec.setdefault("title", b["name"])
        Path(path).write_text(spec_markdown(spec) + (f"\n## Notes\n{b['notes']}\n" if b["notes"] else ""), "utf-8")
        return Path(path)
