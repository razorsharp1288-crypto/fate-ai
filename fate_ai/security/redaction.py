"""Redact secrets from any text before it is logged, displayed or exported."""
from __future__ import annotations

import logging
import re

_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-(?:proj-|live-|test-)?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gsk_[A-Za-z0-9]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)((?:x-api-key|api[_-]?key|authorization|password|secret|token)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{6,}"),
]
REDACTED = "[REDACTED]"

_known_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Remember an exact secret value so it is redacted even if it has no known pattern."""
    if value and len(value) >= 6:
        _known_secrets.add(value)


def redact(text: str) -> str:
    if not text:
        return text
    for s in sorted(_known_secrets, key=len, reverse=True):
        text = text.replace(s, REDACTED)
    for p in _PATTERNS:
        if p.groups:
            text = p.sub(lambda m: m.group(1) + REDACTED, text)
        else:
            text = p.sub(REDACTED, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        record.msg = redact(msg)
        record.args = ()
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True
