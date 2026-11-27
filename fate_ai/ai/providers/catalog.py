"""Catalog of AI services FATE AI can connect to with your own API key.

Almost every modern AI API speaks the OpenAI Chat Completions protocol, so
most entries are handled by ``OpenAICompatibleProvider`` with a preset base
URL. Anthropic and Ollama use native adapters. Anything not listed can be
added as a custom endpoint (any URL, any auth header).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    name: str
    kind: str                 # registry kind: openai | anthropic | ollama | llamacpp | openai_compatible
    base_url: str
    category: str             # Cloud | Aggregator | Local
    description: str
    key_url: str = ""         # where users create a key
    key_prefixes: tuple[str, ...] = ()
    requires_key: bool = True
    raw_base: bool = True     # base_url already contains the version path (…/v1)
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    needs_url: bool = False   # user must supply their own endpoint (e.g. Azure resource)


PRESETS: list[ProviderPreset] = [
    ProviderPreset("openai", "OpenAI", "openai", "https://api.openai.com/v1", "Cloud",
                   "GPT and o-series models.", "https://platform.openai.com/api-keys", ("sk-proj-", "sk-svcacct-")),
    ProviderPreset("anthropic", "Anthropic Claude", "anthropic", "https://api.anthropic.com", "Cloud",
                   "Claude models.", "https://console.anthropic.com/settings/keys", ("sk-ant-",)),
    ProviderPreset("gemini", "Google Gemini", "openai_compatible",
                   "https://generativelanguage.googleapis.com/v1beta/openai", "Cloud",
                   "Gemini models via Google AI Studio.", "https://aistudio.google.com/apikey", ("AIza",)),
    ProviderPreset("mistral", "Mistral AI", "openai_compatible", "https://api.mistral.ai/v1", "Cloud",
                   "Mistral Large, Codestral, Ministral…", "https://console.mistral.ai/api-keys"),
    ProviderPreset("xai", "xAI Grok", "openai_compatible", "https://api.x.ai/v1", "Cloud",
                   "Grok models.", "https://console.x.ai", ("xai-",)),
    ProviderPreset("deepseek", "DeepSeek", "openai_compatible", "https://api.deepseek.com/v1", "Cloud",
                   "DeepSeek chat and reasoning models.", "https://platform.deepseek.com/api_keys"),
    ProviderPreset("groq", "Groq", "openai_compatible", "https://api.groq.com/openai/v1", "Cloud",
                   "Very fast inference of open models.", "https://console.groq.com/keys", ("gsk_",)),
    ProviderPreset("cerebras", "Cerebras", "openai_compatible", "https://api.cerebras.ai/v1", "Cloud",
                   "Wafer-scale fast inference.", "https://cloud.cerebras.ai", ("csk-",)),
    ProviderPreset("perplexity", "Perplexity", "openai_compatible", "https://api.perplexity.ai", "Cloud",
                   "Sonar models with web search.", "https://www.perplexity.ai/settings/api", ("pplx-",)),
    ProviderPreset("cohere", "Cohere", "openai_compatible", "https://api.cohere.ai/compatibility/v1", "Cloud",
                   "Command models.", "https://dashboard.cohere.com/api-keys"),
    ProviderPreset("moonshot", "Moonshot Kimi", "openai_compatible", "https://api.moonshot.ai/v1", "Cloud",
                   "Kimi long-context models.", "https://platform.moonshot.ai"),
    ProviderPreset("qwen", "Alibaba Qwen (DashScope)", "openai_compatible",
                   "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "Cloud",
                   "Qwen models from Alibaba Cloud.", "https://dashscope.console.aliyun.com"),
    ProviderPreset("zhipu", "Zhipu GLM", "openai_compatible", "https://open.bigmodel.cn/api/paas/v4", "Cloud",
                   "GLM models.", "https://open.bigmodel.cn"),
    ProviderPreset("ai21", "AI21 Jamba", "openai_compatible", "https://api.ai21.com/studio/v1", "Cloud",
                   "Jamba long-context models.", "https://studio.ai21.com"),
    ProviderPreset("azure", "Azure OpenAI", "openai_compatible", "https://YOUR-RESOURCE.openai.azure.com/openai/v1",
                   "Cloud", "OpenAI models hosted in your Azure subscription.",
                   "https://portal.azure.com", auth_header="api-key", auth_scheme="", needs_url=True),
    ProviderPreset("openrouter", "OpenRouter", "openai_compatible", "https://openrouter.ai/api/v1", "Aggregator",
                   "One key for hundreds of models from every major lab.", "https://openrouter.ai/keys", ("sk-or-",)),
    ProviderPreset("together", "Together AI", "openai_compatible", "https://api.together.xyz/v1", "Aggregator",
                   "Open models (Llama, Qwen, DeepSeek…) in the cloud.", "https://api.together.ai/settings/api-keys"),
    ProviderPreset("fireworks", "Fireworks AI", "openai_compatible", "https://api.fireworks.ai/inference/v1",
                   "Aggregator", "Fast hosted open models.", "https://fireworks.ai/account/api-keys", ("fw_",)),
    ProviderPreset("deepinfra", "DeepInfra", "openai_compatible", "https://api.deepinfra.com/v1/openai",
                   "Aggregator", "Low-cost hosted open models.", "https://deepinfra.com/dash/api_keys"),
    ProviderPreset("huggingface", "Hugging Face", "openai_compatible", "https://router.huggingface.co/v1",
                   "Aggregator", "Inference Providers router.", "https://huggingface.co/settings/tokens", ("hf_",)),
    ProviderPreset("nvidia", "NVIDIA NIM", "openai_compatible", "https://integrate.api.nvidia.com/v1",
                   "Aggregator", "NVIDIA-hosted model endpoints.", "https://build.nvidia.com", ("nvapi-",)),
    ProviderPreset("sambanova", "SambaNova", "openai_compatible", "https://api.sambanova.ai/v1", "Aggregator",
                   "Fast hosted Llama and DeepSeek.", "https://cloud.sambanova.ai"),
    ProviderPreset("novita", "Novita AI", "openai_compatible", "https://api.novita.ai/v3/openai", "Aggregator",
                   "Hosted open models.", "https://novita.ai/settings/key-management"),
    ProviderPreset("ollama", "Ollama", "ollama", "http://127.0.0.1:11434", "Local",
                   "Free local models on this PC.", requires_key=False),
    ProviderPreset("llamacpp", "llama.cpp server", "llamacpp", "http://127.0.0.1:8080", "Local",
                   "GGUF models via llama-server.", requires_key=False, raw_base=False),
    ProviderPreset("lmstudio", "LM Studio", "openai_compatible", "http://127.0.0.1:1234/v1", "Local",
                   "LM Studio's local server.", requires_key=False),
    ProviderPreset("vllm", "vLLM", "openai_compatible", "http://127.0.0.1:8000/v1", "Local",
                   "Self-hosted vLLM server.", requires_key=False),
    ProviderPreset("localai", "LocalAI", "openai_compatible", "http://127.0.0.1:8080/v1", "Local",
                   "Self-hosted LocalAI.", requires_key=False),
    ProviderPreset("jan", "Jan", "openai_compatible", "http://127.0.0.1:1337/v1", "Local",
                   "Jan desktop app's local API.", requires_key=False),
]

BY_ID = {p.id: p for p in PRESETS}


def detect_from_key(key: str) -> list[ProviderPreset]:
    """Best-guess providers for a pasted key (most specific prefix first).

    Many services use plain ``sk-…`` keys, so an ambiguous key returns several
    candidates and the user picks one.
    """
    key = (key or "").strip()
    hits = [(len(pre), p) for p in PRESETS for pre in p.key_prefixes if key.startswith(pre)]
    if hits:
        best = max(h[0] for h in hits)
        return [p for n, p in hits if n == best]
    if key.startswith("sk-"):
        return [BY_ID[i] for i in ("openai", "deepseek", "moonshot", "qwen", "novita")]
    return []
