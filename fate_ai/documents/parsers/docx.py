"""DOCX text extraction (no macros executed; ElementTree does not resolve external entities)."""
from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

from ...core.exceptions import ValidationError


def docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        info = z.getinfo("word/document.xml")
        if info.file_size > 50 * 1024 * 1024:
            raise ValidationError("DOCX content is too large")
        xml = z.read(info)
    # ElementTree does not resolve external entities, so this is safe from XXE.
    root = ET.fromstring(xml)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paras = []
    for p in root.iter(f"{ns}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{ns}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{ns}tab":
                parts.append("\t")
            elif node.tag == f"{ns}br":
                parts.append("\n")
        paras.append("".join(parts))
    return "\n".join(paras)
