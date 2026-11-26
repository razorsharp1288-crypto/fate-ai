from __future__ import annotations

from .redaction import redact


class AuditLog:
    """Append-only, redacted record of security-relevant actions."""

    def __init__(self, db):
        self.db = db

    def log(self, category: str, action: str, detail: str = "") -> None:
        self.db.execute("INSERT INTO audit_log(category, action, detail) VALUES (?,?,?)",
                        (category, action, redact(detail)[:2000]))

    def recent(self, limit: int = 300) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]
