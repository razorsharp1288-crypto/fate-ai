"""Local document parsers. All content is treated as untrusted data."""
from .base import (CODE_EXT, MAX_FILE_BYTES, MAX_TEXT_CHARS, SUPPORTED, TEXT_EXT, ParsedDocument, parse,  # noqa: F401
                   wrap_untrusted)
from .docx import docx_text  # noqa: F401
from .pdf import pdf_text  # noqa: F401

__all__ = ["CODE_EXT", "MAX_FILE_BYTES", "MAX_TEXT_CHARS", "SUPPORTED", "TEXT_EXT", "ParsedDocument", "parse",
           "wrap_untrusted", "docx_text", "pdf_text"]
