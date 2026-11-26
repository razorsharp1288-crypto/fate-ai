import json

import httpx
import pytest

from fate_ai.bootstrap import build_context
from fate_ai.core.exceptions import AuthenticationError
from fate_ai.security.credential_manager import MemoryBackend


def ollama_handler(req):
    if req.url.path == "/api/chat":
        body = json.loads(req.content)
        last = body["messages"][-1]["content"]
        lines = [{"message": {"content": f"echo: {last}"}, "done": False},
                 {"done": True, "prompt_eval_count": 3, "eval_count": 2}]
        return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())
    if req.url.host == "api.openai.com":
        return httpx.Response(401, json={"error": {"message": "bad key"}})
    return httpx.Response(404)


@pytest.fixture
def mctx(tmp_path):
    c = build_context(tmp_path / "d", credential_backend=MemoryBackend(), transport=httpx.MockTransport(ollama_handler))
    yield c
    c.shutdown()


def test_send_streams_persists_and_tracks_usage(mctx):
    conv = mctx.chat.new_conversation("ollama", "tiny", "be brief")
    tokens = []
    res = mctx.chat.send(conv.id, "hello world", tokens.append)
    assert "".join(tokens) == "echo: hello world" == res.text
    assert not res.estimated and res.output_tokens == 2
    msgs = mctx.conversations.messages(conv.id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert mctx.conversations.get(conv.id).title == "hello world"
    assert mctx.usage.summary()["requests"] == 1


def test_regenerate_and_edit(mctx):
    conv = mctx.chat.new_conversation("ollama", "tiny")
    mctx.chat.send(conv.id, "one", lambda t: None)
    mctx.chat.regenerate(conv.id, lambda t: None)
    msgs = mctx.conversations.messages(conv.id)
    assert len(msgs) == 2
    mctx.chat.edit_and_resend(conv.id, msgs[0]["id"], "two", lambda t: None)
    msgs = mctx.conversations.messages(conv.id)
    assert [m["content"] for m in msgs] == ["two", "echo: two"]


def test_failure_is_recorded(mctx):
    mctx.credentials.set_api_key("openai", "sk-test-aaaaaaaaaaaaaaaaaaaa")
    conv = mctx.chat.new_conversation("openai", "gpt-4o-mini")
    with pytest.raises(AuthenticationError):
        mctx.chat.send(conv.id, "hi", lambda t: None)
    assert mctx.usage.summary()["failed"] == 1


def test_conversation_preserves_provider_and_model(mctx):
    a = mctx.chat.new_conversation("ollama", "model-a")
    b = mctx.chat.new_conversation("openai", "model-b")
    assert mctx.conversations.get(a.id).model == "model-a"
    assert mctx.conversations.get(b.id).provider == "openai"


def test_pricing_estimates(mctx):
    assert mctx.pricing.estimate("openai", "gpt-4o-mini-2024-07-18", 1_000_000, 0) == pytest.approx(0.15)
    assert mctx.pricing.estimate("ollama", "x", 10, 10) is None


def test_delete_all_local_data(tmp_path):
    from fate_ai.security.credential_manager import MemoryBackend
    backend = MemoryBackend()
    c = build_context(tmp_path / "x", credential_backend=backend)
    c.credentials.set_api_key("openai", "sk-test-bbbbbbbbbbbbbbbbbbbb")
    c.chat.new_conversation("ollama", "m")
    root = c.paths.root
    c.delete_all_local_data()
    c.tasks.shutdown()
    assert backend.get("provider:openai:api_key") is None
    c2 = build_context(root, credential_backend=MemoryBackend())
    try:
        assert c2.conversations.list() == []
    finally:
        c2.shutdown()


def test_history_not_stored_when_disabled(tmp_path):
    c = build_context(tmp_path / "y", credential_backend=MemoryBackend())
    c.settings.update(privacy={"store_chat_history": False})
    c.chat.new_conversation("ollama", "m")
    root = c.paths.root
    c.shutdown()
    c2 = build_context(root, credential_backend=MemoryBackend())
    try:
        assert c2.conversations.list() == []
    finally:
        c2.shutdown()
