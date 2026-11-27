"""Any-provider support: catalog presets, key detection, custom endpoints and auth headers."""
import json

import httpx
import pytest

from fate_ai.ai.providers.base import ChatMessage, ChatRequest
from fate_ai.ai.providers.catalog import BY_ID, PRESETS, detect_from_key
from fate_ai.ai.providers.registry import KINDS, ProviderRegistry


def test_catalog_is_large_and_valid():
    assert len(PRESETS) >= 25
    assert len({p.id for p in PRESETS}) == len(PRESETS)
    for p in PRESETS:
        assert p.kind in KINDS
        assert p.base_url.startswith(("http://", "https://"))
    for must in ("openai", "anthropic", "gemini", "mistral", "xai", "deepseek", "groq", "openrouter", "together",
                 "perplexity", "cohere", "huggingface", "nvidia", "lmstudio"):
        assert must in BY_ID


@pytest.mark.parametrize("key,expected", [
    ("sk-ant-api03-xxxxxxxxxxxxxxxx", "anthropic"), ("sk-or-v1-abcdefabcdef", "openrouter"),
    ("gsk_abcdefghijklmnop", "groq"), ("xai-abcdefghijklmnop", "xai"), ("AIzaSyAbcdefghijklmnop", "gemini"),
    ("hf_abcdefghijklmnopqrstu", "huggingface"), ("nvapi-abcdefghijkl", "nvidia"), ("pplx-abcdefghij", "perplexity"),
    ("sk-proj-abcdefghijklmnop", "openai"),
])
def test_key_detection(key, expected):
    assert detect_from_key(key)[0].id == expected


def test_ambiguous_and_unknown_keys():
    ids = [p.id for p in detect_from_key("sk-1234567890abcdef")]
    assert "openai" in ids and "deepseek" in ids
    assert detect_from_key("totally-unknown") == []


def _mock(seen):
    def handler(req: httpx.Request):
        seen.append((str(req.url), dict(req.headers)))
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "model-x"}]})
        body = "data: " + json.dumps({"choices": [{"delta": {"content": "hi"}}]}) + "\n\ndata: [DONE]\n\n"
        return httpx.Response(200, content=body.encode())
    return httpx.MockTransport(handler)


def test_gemini_preset_urls_and_bearer(ctx):
    seen = []
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=_mock(seen))
    reg.add_preset("gemini")
    ctx.credentials.set_api_key("gemini", "AIzaSyTESTKEY1234567890")
    p = reg.get("gemini")
    assert p.test_connection().ok
    assert p.chat(ChatRequest("gemini-x", [ChatMessage("user", "q")]))[0] == "hi"
    assert seen[0][0] == "https://generativelanguage.googleapis.com/v1beta/openai/models"
    assert seen[1][0] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert seen[0][1]["authorization"] == "Bearer AIzaSyTESTKEY1234567890"
    cfg = ctx.provider_repo.get("gemini")
    assert reg.requires_key(cfg) and not reg.is_local(cfg)


def test_preset_without_key_reports_missing(ctx):
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=_mock([]))
    reg.add_preset("groq")
    assert reg.get("groq").test_connection().message == "No API key configured."


def test_perplexity_and_zhipu_raw_paths(ctx):
    seen = []
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=_mock(seen))
    for pid in ("perplexity", "zhipu", "deepinfra"):
        reg.add_preset(pid)
        ctx.credentials.set_api_key(pid, "k" * 20)
        reg.get(pid).list_models()
    assert [u for u, _ in seen] == ["https://api.perplexity.ai/models",
                                    "https://open.bigmodel.cn/api/paas/v4/models",
                                    "https://api.deepinfra.com/v1/openai/models"]


def test_azure_custom_header_and_url(ctx):
    seen = []
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=_mock(seen))
    reg.add_preset("azure", "https://myres.openai.azure.com/openai/v1")
    ctx.credentials.set_api_key("azure", "azurekey1234567890")
    reg.get("azure").list_models()
    url, headers = seen[0]
    assert url == "https://myres.openai.azure.com/openai/v1/models"
    assert headers["api-key"] == "azurekey1234567890" and "authorization" not in headers


def test_custom_endpoint_any_header(ctx):
    seen = []
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=_mock(seen))
    p = reg.add_custom("My Gateway", "https://gw.example.com/llm/v2", auth_header="X-Api-Key", auth_scheme="")
    ctx.credentials.set_api_key(p["id"], "gatewaykey123456")
    assert reg.get(p["id"]).test_connection().ok
    assert seen[0][0] == "https://gw.example.com/llm/v2/models"
    assert seen[0][1]["x-api-key"] == "gatewaykey123456"
    with pytest.raises(ValueError):
        reg.add_custom("Bad", "https://x.example.com", auth_header="Bad Header:")


def test_local_presets_need_no_key(ctx):
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=_mock([]))
    reg.add_preset("lmstudio")
    cfg = ctx.provider_repo.get("lmstudio")
    assert reg.is_local(cfg) and not reg.requires_key(cfg)
    assert reg.get("lmstudio").test_connection().ok
