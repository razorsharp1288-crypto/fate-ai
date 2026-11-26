"""Typed records returned by repositories."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Conversation:
    id: int
    title: str
    provider: str
    model: str
    system_prompt: str
    temperature: float
    max_tokens: int
    parent_id: int | None
    created_at: str
    updated_at: str


@dataclass
class Message:
    id: int
    conversation_id: int
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    created_at: str = ""


@dataclass
class AgentRecord:
    id: int
    name: str
    role: str
    instructions: str
    provider: str
    model: str
    permissions: dict = field(default_factory=dict)
    allowed_paths: list = field(default_factory=list)
    created_at: str = ""


@dataclass
class SandboxRecord:
    id: int
    name: str
    level: str
    workdir: str
    config: dict = field(default_factory=dict)
    created_at: str = ""
