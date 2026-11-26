import logging

import pytest

from fate_ai.core.exceptions import CredentialError, PermissionDeniedError
from fate_ai.security.credential_manager import CredentialManager, MemoryBackend
from fate_ai.security.paths import resolve_inside, safe_name
from fate_ai.security.redaction import RedactingFilter, redact


def test_keys_not_in_database_or_settings(ctx):
    secret = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX1234"
    ctx.credentials.set_api_key("openai", secret)
    ctx.settings.save()
    raw_db = ctx.paths.database.read_bytes()
    for f in ctx.paths.root.rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes(), f
    assert secret.encode() not in raw_db
    assert ctx.credentials.get_api_key("openai") == secret


def test_audit_log_never_contains_key(ctx):
    ctx.credentials.set_api_key("anthropic", "sk-ant-api03-supersecretvalue123")
    for row in ctx.audit.recent():
        assert "supersecret" not in row["detail"]


def test_invalid_keys_rejected():
    cm = CredentialManager(MemoryBackend())
    with pytest.raises(CredentialError):
        cm.set_api_key("openai", "")
    with pytest.raises(CredentialError):
        cm.set_api_key("openai", "abc\ndef")
    with pytest.raises(CredentialError):
        cm.set_api_key("bad\nid", "abcdefgh")


def test_mask():
    assert CredentialManager.mask("sk-1234567890abcd") == "sk-1…abcd"
    assert CredentialManager.mask(None) == "not set"


@pytest.mark.parametrize("text", [
    "Authorization: Bearer sk-abcdefghijklmnopqrstu",
    "key sk-ant-api03-abcdefghijklmnop",
    'api_key="abcdef1234567890"',
    "x-api-key: zzzzzzzzzzzzzzzz",
])
def test_redaction_patterns(text):
    out = redact(text)
    assert "[REDACTED]" in out
    assert "abcdefghijklmnop" not in out and "zzzzzzzzzzzzzzzz" not in out


def test_registered_secret_redacted_in_logs(caplog):
    cm = CredentialManager(MemoryBackend())
    cm.set_api_key("custom", "plainsecretvalue42")
    logger = logging.getLogger("fate.test")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="fate.test"):
        logger.info("calling with %s", "plainsecretvalue42")
    assert "plainsecretvalue42" not in caplog.text


def test_path_traversal_blocked(tmp_path):
    (tmp_path / "ok").mkdir()
    assert resolve_inside(tmp_path, "ok/file.txt").name == "file.txt"
    for bad in ("../etc/passwd", "/etc/passwd", "ok/../../x"):
        with pytest.raises(PermissionDeniedError):
            resolve_inside(tmp_path, bad)


def test_safe_name():
    assert safe_name("CON") == "_CON"
    assert safe_name("a/b\\c:d") == "a_b_c_d"
