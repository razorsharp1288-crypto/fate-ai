"""Model detection: any list format, suggested fallbacks, user-added models, and key checks without a model list."""
import json

import httpx
import pytest

from fate_ai.ai.providers import autodetect
from fate_ai.ai.providers.catalog import BY_ID
from fate_ai.ai.providers.openai_provider import parse_model_list
from fate_ai.ai.providers.registry import ProviderRegistry


@pytest.mark.parametrize("body,expected", [
    ({"data": [{"id": "a"}, {"id": "b"}]}, ["a", "b"]),
    ({"models": [{"name": "models/gemini-x"}, {"name": "y"}]}, ["gemini-x", "y"]),
    ({"data": ["m1", "m2", "m1"]}, ["m1", "m2"]),
    ([{"model": "x1"}, {"slug": "x2"}, 5, None], ["x1", "x2"]),
    ({"result": {"data": [{"id": "deep"}]}}, ["deep"]),
    ({"object": "list"}, []),
])
def test_parse_any_model_list(body, expected):
    assert [m.id for m in parse_model_list(body)] == expected


def make_transport(models_status=200, models_body=None, chat_status=200, chat_body=None, seen=None):
    def handler(req):
        if seen is not None:
            seen.append((req.method, req.url.path, req.content and json.loads(req.content).get("model")))
        if req.url.path.endswith("/models"):
            return httpx.Response(models_status, json=models_body if models_body is not None else {"data": []})
        if chat_status != 200:
            return httpx.Response(chat_status, json=chat_body or {"error": {"message": "nope"}})
        body = "data: " + json.dumps({"choices": [{"delta": {"content": "o"}}]}) + "\n\ndata: [DONE]\n\n"
        return httpx.Response(200, content=body.encode())
    return httpx.MockTransport(handler)


def test_models_live(ctx):
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials,
                           transport=make_transport(models_body={"data": [{"id": "mercury-coder"}]}))
    reg.add_preset("inception")
    ctx.credentials.set_api_key("inception", "k" * 20)
    ids, source, _ = reg.models("inception")
    assert ids == ["mercury-coder"] and source == "live"


def test_models_fall_back_to_suggested_when_not_listed(ctx):
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=make_transport(models_status=404))
    reg.add_preset("inception")
    ctx.credentials.set_api_key("inception", "k" * 20)
    ids, source, msg = reg.models("inception")
    assert source == "suggested" and "mercury" in ids and "suggested" in msg.lower()
    reg.add_custom_model("inception", "mercury-2-preview")
    ids, _, _ = reg.models("inception")
    assert ids[0] == "mercury-2-preview"
    assert ctx.provider_repo.get("inception")["default_model"] == "mercury-2-preview"
    with pytest.raises(ValueError):
        reg.add_custom_model("inception", "bad name")


def test_models_auth_error_is_reported_not_hidden(ctx):
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=make_transport(models_status=401))
    reg.add_preset("groq")
    ctx.credentials.set_api_key("groq", "gsk_" + "x" * 20)
    ids, source, msg = reg.models("groq")
    assert source == "error" and "Authentication" in msg


def test_probe_accepts_key_via_chat_when_models_endpoint_missing():
    seen = []
    t = make_transport(models_status=404, seen=seen)
    winner, _ = autodetect.find_service("anykey123456789", candidates=[BY_ID["inception"]], transport=t)
    assert winner and winner.preset.id == "inception" and winner.models[0] == "mercury"
    assert ("POST", "/v1/chat/completions", "mercury") in seen


def test_probe_rejects_bad_key_even_without_model_list():
    t = make_transport(models_status=404, chat_status=401)
    winner, results = autodetect.find_service("badkey123456789", candidates=[BY_ID["inception"]], transport=t)
    assert winner is None and "Authentication" in results[0].message


def test_lenient_only_for_matched_services():
    t = make_transport(models_status=404, chat_status=400,
                       chat_body={"error": {"message": "model 'mercury' does not exist"}})
    winner, _ = autodetect.find_service("k123456789012", candidates=[BY_ID["inception"]], transport=t)
    assert winner is not None  # user chose the service: key works, model list is a suggestion
    winner, _ = autodetect.find_service("unknownformat-key-9999", allow_all=True, transport=t)
    assert winner is None      # broad search never accepts on a 4xx guess
