"""Markdown → HTML with syntax highlighting, safe for untrusted model output."""
from __future__ import annotations

import html
import re

try:
    import markdown as _md
except ImportError:  # pragma: no cover
    _md = None

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer
    _FORMATTER = HtmlFormatter(noclasses=True, style="monokai", nowrap=True)
except ImportError:  # pragma: no cover
    highlight = None

_FENCE = re.compile(r"```([\w+#.-]*)[ \t]*\n(.*?)(?:```|\Z)", re.S)


def _code_html(lang: str, code: str) -> str:
    if highlight is not None:
        try:
            lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
        except Exception:
            lexer = TextLexer()
        body = highlight(code, lexer, _FORMATTER)
    else:
        body = html.escape(code)
    label = f'<div style="color:#8C84A8;font-size:11px;">{html.escape(lang or "code")}</div>' if lang else ""
    return f'{label}<pre>{body}</pre>'


def render(text: str) -> str:
    """Render markdown. Raw HTML from the model is escaped (never interpreted)."""
    blocks: list[str] = []

    def stash(m):
        blocks.append(_code_html(m.group(1), m.group(2).rstrip("\n")))
        return f"\n\nFATECODEBLOCK{len(blocks) - 1}END\n\n"

    text = _FENCE.sub(stash, text)
    escaped = html.escape(text, quote=False)
    if _md is not None:
        out = _md.markdown(escaped, extensions=["tables", "sane_lists"], output_format="html")
    else:
        out = "<p>" + escaped.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    # Block links to anything other than http(s)
    out = re.sub(r'href="(?!https?://)[^"]*"', 'href="#"', out)
    out = out.replace("<table>", '<table border="1" cellspacing="0" cellpadding="5" style="border-color:#2A2440;">')
    for i, b in enumerate(blocks):
        out = out.replace(f"<p>FATECODEBLOCK{i}END</p>", b).replace(f"FATECODEBLOCK{i}END", b)
    return out
