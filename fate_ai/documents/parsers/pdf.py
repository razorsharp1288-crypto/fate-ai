"""PDF text extraction via pypdf (pure Python, no JavaScript execution)."""
from __future__ import annotations

from pathlib import Path

from ...core.exceptions import ValidationError


def pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValidationError("PDF support requires the 'pypdf' package.") from None
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise ValidationError("PDF is password protected.") from None
    return "\n\n".join((page.extract_text() or "") for page in reader.pages[:500])
