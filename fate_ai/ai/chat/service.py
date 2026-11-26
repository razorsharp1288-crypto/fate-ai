"""Chat orchestration: conversation persistence, streaming, usage tracking."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from ...core.exceptions import FateError
from ...database.repository import ConversationRepository, UsageRepository
from ..providers.base import Cancelled, ChatMessage, ChatRequest, estimate_tokens

log = logging.getLogger(__name__)


@dataclass
class ChatResult:
    message_id: int | None
    text: str
    input_tokens: int
    output_tokens: int
    estimated: bool
    latency_ms: int
    first_token_ms: int | None
    cancelled: bool = False


class ChatService:
    def __init__(self, conversations: ConversationRepository, usage: UsageRepository, registry, bus=None,
                 ollama_options: Callable[[], dict] | None = None):
        self.ollama_options = ollama_options
        self.conversations = conversations
        self.usage = usage
        self.registry = registry
        self.bus = bus

    def new_conversation(self, provider: str, model: str, system_prompt: str = "",
                         temperature: float = 0.7, max_tokens: int = 2048, title: str = "New chat"):
        return self.conversations.create(title, provider, model, system_prompt, temperature, max_tokens)

    @staticmethod
    def auto_title(text: str) -> str:
        t = " ".join(text.split())
        return (t[:48] + "…") if len(t) > 48 else (t or "New chat")

    def build_request(self, conv, history: list[dict]) -> ChatRequest:
        msgs = [ChatMessage(m["role"], m["content"]) for m in history if m["role"] in ("user", "assistant")]
        return ChatRequest(model=conv.model, messages=msgs, system=conv.system_prompt,
                           temperature=conv.temperature, max_tokens=conv.max_tokens)

    def send(self, conversation_id: int, user_text: str | None, on_token: Callable[[str], None],
             cancel=None) -> ChatResult:
        """Append ``user_text`` (if given) and stream the assistant reply.

        Passing ``user_text=None`` regenerates from the existing history.
        """
        conv = self.conversations.get(conversation_id)
        if conv is None:
            raise FateError("Conversation not found")
        if not conv.model:
            raise FateError("No model selected for this conversation.")
        if user_text is not None:
            if not self.conversations.messages(conversation_id):
                self.conversations.update(conversation_id, title=self.auto_title(user_text))
            self.conversations.add_message(conversation_id, "user", user_text)
        history = self.conversations.messages(conversation_id)
        req = self.build_request(conv, history)
        provider = self.registry.get(conv.provider)

        start = time.perf_counter()
        first_token = None
        parts: list[str] = []
        last = None
        cancelled = False
        try:
            if provider.kind == "ollama" and self.ollama_options:
                stream = provider.stream_chat(req, cancel=cancel, options=self.ollama_options())
            else:
                stream = provider.stream_chat(req, cancel=cancel)
            for chunk in stream:
                if chunk.text:
                    if first_token is None:
                        first_token = int((time.perf_counter() - start) * 1000)
                    parts.append(chunk.text)
                    on_token(chunk.text)
                if chunk.done:
                    last = chunk
        except Cancelled:
            cancelled = True
        except FateError as e:
            self._record(provider, conv, req, "", None, start, success=False, error=str(e))
            raise
        text = "".join(parts)
        result = self._record(provider, conv, req, text, last, start, success=True)
        result.first_token_ms = first_token
        result.cancelled = cancelled
        if text:
            result.message_id = self.conversations.add_message(
                conversation_id, "assistant", text, provider=conv.provider, model=conv.model,
                input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                latency_ms=result.latency_ms)
        return result

    def _record(self, provider, conv, req, text, last, start, success, error=None) -> ChatResult:
        latency = int((time.perf_counter() - start) * 1000)
        in_tok = last.input_tokens if last and last.input_tokens is not None else None
        out_tok = last.output_tokens if last and last.output_tokens is not None else None
        estimated = in_tok is None or out_tok is None
        if in_tok is None:
            in_tok = estimate_tokens(req.system + "".join(m.content for m in req.messages))
        if out_tok is None:
            out_tok = estimate_tokens(text)
        self.usage.record(conv.provider, conv.model, in_tok, out_tok, estimated=estimated,
                          latency_ms=latency, success=success, is_local=provider.is_local, error=error)
        if self.bus:
            self.bus.publish("usage.recorded", provider=conv.provider, model=conv.model)
        return ChatResult(None, text, in_tok, out_tok, estimated, latency, None)

    def edit_and_resend(self, conversation_id: int, message_id: int, new_text: str, on_token, cancel=None):
        """Replace a user message and everything after it, then regenerate."""
        self.conversations.delete_messages_from(conversation_id, message_id)
        return self.send(conversation_id, new_text, on_token, cancel)

    def regenerate(self, conversation_id: int, on_token, cancel=None):
        msgs = self.conversations.messages(conversation_id)
        if msgs and msgs[-1]["role"] == "assistant":
            self.conversations.delete_messages_from(conversation_id, msgs[-1]["id"])
        return self.send(conversation_id, None, on_token, cancel)
