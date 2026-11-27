"""Paste-a-key auto detection: only matching services see a recognised key; unknown keys need consent."""
import httpx
import pytest

from fate_ai.ai.providers import autodetect
from fate_ai.ai.providers.catalog import BY_ID


def transport_accepting(host_ok: str, seen: list):
    def handler(req: httpx.Request):
        seen.append(req.url.host)
        if req.url.host == host_ok:
            return httpx.Response(200, json={"data": [{"id": "text-embedding-x"}, {"id": "mercury-coder"}]})
        return httpx.Response(401, json={"error": {"message": "invalid key"}})
    return httpx.MockTransport(handler)


def test_recognised_key_only_goes_to_its_service():
    seen = []
    winner, results = autodetect.find_service("gsk_" + "a" * 40, transport=transport_accepting("api.groq.com", seen))
    assert winner.preset.id == "groq"
    assert set(seen) == {"api.groq.com"}


def test_unknown_key_needs_consent_then_finds_service():
    seen = []
    t = transport_accepting("api.inceptionlabs.ai", seen)
    winner, results = autodetect.find_service("plainkey_123456789", transport=t)
    assert winner is None and results == [] and seen == []          # nothing sent without consent
    winner, results = autodetect.find_service("plainkey_123456789", allow_all=True, transport=t)
    assert winner.preset.id == "inception"
    assert len(results) == len(autodetect.cloud_candidates())
    assert "api.anthropic.com" in seen and all("127.0.0.1" not in h for h in seen)  # never local servers


def test_ambiguous_sk_key_picks_the_one_that_accepts():
    seen = []
    winner, _ = autodetect.find_service("sk-" + "b" * 40, transport=transport_accepting("api.deepseek.com", seen))
    assert winner.preset.id == "deepseek"
    assert "api.openai.com" in seen and "api.anthropic.com" not in seen


def test_connect_saves_key_and_sets_default_model(ctx):
    seen = []
    winner, _ = autodetect.connect(ctx, "custom-format-key-999999", allow_all=True,
                                   transport=transport_accepting("api.inceptionlabs.ai", seen))
    assert winner.preset.id == "inception"
    assert ctx.credentials.get_api_key("inception") == "custom-format-key-999999"
    cfg = ctx.provider_repo.get("inception")
    assert cfg["default_model"] == "mercury-coder"  # embeddings skipped
    assert ctx.settings.settings.ai.default_provider == "inception"
    assert ctx.settings.settings.ai.default_model == "mercury-coder"


def test_rejected_key_is_not_saved(ctx):
    winner, results = autodetect.connect(ctx, "xai-" + "c" * 30,
                                         transport=transport_accepting("nowhere.example", []))
    assert winner is None and results and not results[0].ok
    assert ctx.credentials.get_api_key("xai") is None


def test_new_presets_present():
    for pid in ("inception", "minimax", "hyperbolic", "lambda", "featherless", "nebius"):
        assert pid in BY_ID
