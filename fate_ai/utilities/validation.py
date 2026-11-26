"""Input validation shared by services and UI. Raises ``ValidationError`` with user-readable text."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..core.exceptions import ValidationError

_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]*(:[A-Za-z0-9._\-]+)?$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def validate_url(url: str) -> str:
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValidationError("URL must start with http:// or https:// and include a host.")
    if p.username or p.password:
        raise ValidationError("Do not put credentials in the URL; use the API Keys page.")
    return url.rstrip("/")


def is_local_url(url: str) -> bool:
    return (urlparse(url).hostname or "") in _LOCAL_HOSTS


def is_insecure_remote(url: str) -> bool:
    """Plain HTTP to a non-local host — API keys would travel unencrypted."""
    return urlparse(url).scheme == "http" and not is_local_url(url)


def validate_model_tag(tag: str) -> str:
    tag = (tag or "").strip()
    if not tag or len(tag) > 200 or not _TAG_RE.match(tag):
        raise ValidationError(f"Invalid model tag: {tag!r}")
    return tag


def validate_env_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise ValidationError("Name must be 1-64 characters: letters, digits, space, - _ . (starting with a "
                              "letter or digit).")
    return name


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
