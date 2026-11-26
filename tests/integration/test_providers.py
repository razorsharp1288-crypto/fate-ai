"""Provider adapters tested against mock HTTP servers implementing each wire protocol."""
import json

import httpx
import pytest

from fate_ai.ai.providers.anthropic_provider import AnthropicProvider
from fate_ai.ai.providers.base import ChatMessage, ChatRequest
from fate_ai.ai.providers.ollama_provider import OllamaProvider
from fate_ai.ai.providers.openai_provider import OpenAICompatibleProvider, OpenAIProvider
from fate_ai.core.exceptions import AuthenticationError, ProviderUnavailableError, RateLimitError

REQ = ChatRequest("m", [ChatMessage("user", "hi")], system="sys", temperature=0.3, max_tokens=50)


def sse(*events):
    body = ""
    for ev in events:
        if isinstance(ev, tuple):
            body += f"event: {ev[0]}\ndata: {json.dumps(ev[1])}\n\n"
        else:
            body += f"data: {ev if isinstance(ev, str) else json.dumps(ev)}\n\n"
    return body.encode()


def test_openai_list_models_filters_and_auth_header():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"data": [{"id": "gpt-4o"}, {"id": "text-embedding-3-small"},
                                                  {"id": "whisper-1"}, {"id": "gpt-4o-mini"}]})
    p = OpenAIProvider("openai", OpenAIProvider.DEFAULT_URL, "sk-test-123456789012345678",
                       transport=httpx.MockTransport(handler))
    assert [m.id for m in p.list_models()] == ["gpt-4o", "gpt-4o-mini"]
    assert seen["auth"] == "Bearer sk-test-123456789012345678"
    assert p.test_connection().ok


def test_openai_streaming_and_usage():
    captured = {}

    def handler(req):
        captured.update(json.loads(req.content))
        return httpx.Response(200, content=sse(
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}},
            "[DONE]"), headers={"content-type": "text/event-stream"})
    p = OpenAIProvider("openai", OpenAIProvider.DEFAULT_URL, "k" * 20, transport=httpx.MockTransport(handler))
    text, last = p.chat(REQ)
    assert text == "Hello" and last.input_tokens == 7 and last.output_tokens == 2
    assert captured["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["max_completion_tokens"] == 50 and captured["stream"] is True


def test_openai_retries_without_temperature():
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature' does not support 0.3"}})
        return httpx.Response(200, content=sse({"choices": [{"delta": {"content": "ok"}}]}, "[DONE]"))
    p = OpenAIProvider("openai", OpenAIProvider.DEFAULT_URL, "k" * 20, transport=httpx.MockTransport(handler))
    assert p.chat(REQ)[0] == "ok"
    assert len(calls) == 2


@pytest.mark.parametrize("status,exc", [(401, AuthenticationError), (429, RateLimitError),
                                        (503, ProviderUnavailableError)])
def test_error_mapping(status, exc):
    p = OpenAIProvider("openai", OpenAIProvider.DEFAULT_URL, "k" * 20,
                       transport=httpx.MockTransport(lambda r: httpx.Response(status, json={"error": {"message": "nope"}})))
    with pytest.raises(exc):
        list(p.stream_chat(REQ))
    assert not p.test_connection().ok


def test_error_messages_redact_keys():
    key = "sk-proj-SECRETSECRETSECRET1234"
    p = OpenAIProvider("openai", OpenAIProvider.DEFAULT_URL, key, transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {key}"}})))
    res = p.test_connection()
    assert not res.ok and key not in res.message


def test_missing_key_reported_without_request():
    p = OpenAIProvider("openai", OpenAIProvider.DEFAULT_URL, None,
                       transport=httpx.MockTransport(lambda r: pytest.fail("should not call")))
    assert p.test_connection().message == "No API key configured."


def test_connection_refused_is_friendly():
    def handler(req):
        raise httpx.ConnectError("refused")
    p = OllamaProvider("ollama", "http://127.0.0.1:1", transport=httpx.MockTransport(handler))
    res = p.test_connection()
    assert not res.ok and "not running" in res.message


def test_compatible_endpoint_paths():
    urls = []

    def handler(req):
        urls.append(str(req.url))
        return httpx.Response(200, json={"data": [{"id": "local-model"}]})
    OpenAICompatibleProvider("c", "http://localhost:1234/v1", transport=httpx.MockTransport(handler)).list_models()
    OpenAICompatibleProvider("c", "http://localhost:8080", transport=httpx.MockTransport(handler)).list_models()
    assert urls == ["http://localhost:1234/v1/models", "http://localhost:8080/v1/models"]


def test_anthropic_streaming_and_headers():
    seen = {}

    def handler(req):
        seen["headers"] = dict(req.headers)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=sse(
            ("message_start", {"type": "message_start", "message": {"usage": {"input_tokens": 12}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0}),
            ("content_block_delta", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi "}}),
            ("content_block_delta", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "there"}}),
            ("message_delta", {"type": "message_delta", "usage": {"output_tokens": 3}}),
            ("message_stop", {"type": "message_stop"})))
    p = AnthropicProvider("anthropic", AnthropicProvider.DEFAULT_URL, "sk-ant-xxxxxxxxxxxx",
                          transport=httpx.MockTransport(handler))
    req = ChatRequest("claude-x", [ChatMessage("user", "a"), ChatMessage("user", "b")], system="S")
    text, last = p.chat(req)
    assert text == "Hi there" and last.input_tokens == 12 and last.output_tokens == 3
    assert seen["headers"]["x-api-key"] == "sk-ant-xxxxxxxxxxxx"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["system"] == "S"
    assert seen["body"]["messages"] == [{"role": "user", "content": "a\n\nb"}]


def test_anthropic_model_pagination():
    def handler(req):
        if "after_id" in str(req.url):
            return httpx.Response(200, json={"data": [{"id": "m3"}], "has_more": False})
        return httpx.Response(200, json={"data": [{"id": "m1", "display_name": "M1"}, {"id": "m2"}],
                                         "has_more": True, "last_id": "m2"})
    p = AnthropicProvider("anthropic", AnthropicProvider.DEFAULT_URL, "k" * 12, transport=httpx.MockTransport(handler))
    assert [m.id for m in p.list_models()] == ["m1", "m2", "m3"]


def test_anthropic_stream_error_event():
    def handler(req):
        return httpx.Response(200, content=sse(("error", {"type": "error", "error": {"type": "overloaded_error",
                                                                                      "message": "Overloaded"}})))
    p = AnthropicProvider("anthropic", AnthropicProvider.DEFAULT_URL, "k" * 12, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderUnavailableError):
        p.chat(REQ)


def test_ollama_chat_pull_delete():
    log = []

    def handler(req):
        log.append((req.method, req.url.path))
        if req.url.path == "/api/chat":
            body = json.loads(req.content)
            assert body["options"]["num_thread"] == 3
            lines = [{"message": {"content": "Yo"}, "done": False},
                     {"message": {"content": "!"}, "done": True, "prompt_eval_count": 4, "eval_count": 2}]
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())
        if req.url.path == "/api/pull":
            lines = [{"status": "pulling manifest"}, {"status": "downloading", "completed": 50, "total": 100},
                     {"status": "success"}]
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())
        if req.url.path == "/api/delete":
            return httpx.Response(200)
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3.2:1b", "size": 1300000000,
                                                         "details": {"parameter_size": "1.2B"}}]})
        return httpx.Response(404)
    p = OllamaProvider("ollama", OllamaProvider.DEFAULT_URL, transport=httpx.MockTransport(handler))
    chunks = list(p.stream_chat(REQ, options={"num_thread": 3}))
    assert "".join(c.text for c in chunks) == "Yo!" and chunks[-1].output_tokens == 2
    prog = []
    p.pull("llama3.2:1b", progress=lambda s, c, t: prog.append((s, c, t)))
    assert ("downloading", 50, 100) in prog
    p.delete("llama3.2:1b")
    assert p.list_models()[0].size_bytes == 1300000000
    assert ("DELETE", "/api/delete") in log
