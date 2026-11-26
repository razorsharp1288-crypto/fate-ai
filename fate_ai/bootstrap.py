"""Composition root: wires every service together (dependency injection)."""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from .ai.agents.service import AgentService
from .ai.chat.service import ChatService
from .ai.pricing import PricingTable
from .ai.providers.registry import ProviderRegistry
from .config import AppPaths, default_data_dir
from .core.event_bus import EventBus
from .core.settings import SettingsStore
from .core.task_manager import TaskManager
from .database.db import Database
from .database.repository import (BenchmarkRepository, ConversationRepository, PromptRepository,
                                  ProviderRepository, SandboxRunRepository, UsageRepository, agents_repo,
                                  projects_repo, sandboxes_repo)
from .projects.manager import ProjectManager
from .resources.manager import ollama_options, set_own_priority
from .sandbox.execution_manager import ExecutionManager
from .security.audit import AuditLog
from .security.credential_manager import CredentialManager

log = logging.getLogger(__name__)

STARTER_PROMPTS = [
    ("Explain this code", "Explain what the following code does, step by step, and point out bugs:\n\n{{code}}", "Coding", "explain,review"),
    ("Write unit tests", "Write thorough unit tests using {{framework}} for:\n\n{{code}}", "Coding", "tests"),
    ("Refactor for clarity", "Refactor this code for readability without changing behaviour:\n\n{{code}}", "Development", "refactor"),
    ("Summarise a document", "Summarise the attached document in {{length}} bullet points, then list open questions.", "Research", "summary"),
    ("Literature comparison", "Compare these sources on {{topic}}: agreements, disagreements, gaps.", "Research", "analysis"),
    ("Business email", "Write a concise, friendly business email to {{recipient}} about {{subject}}.", "Business", "email"),
    ("SWOT analysis", "Produce a SWOT analysis for {{company_or_idea}}.", "Business", "strategy"),
    ("Blog outline", "Create a blog post outline about {{topic}} for {{audience}}.", "Writing", "blog"),
    ("Proofread", "Proofread and improve the following text, keeping my voice:\n\n{{text}}", "Writing", "edit"),
    ("Automation script", "Write a {{language}} script that automates: {{task}}. Include error handling.", "Automation", "script"),
    ("Image prompt", "Write a detailed image-generation prompt for: {{idea}}. Include style, lighting, composition.", "Image generation", "image"),
]


@dataclass
class AppContext:
    paths: AppPaths
    settings: SettingsStore
    db: Database
    bus: EventBus
    tasks: TaskManager
    audit: AuditLog
    credentials: CredentialManager
    providers: ProviderRegistry
    provider_repo: ProviderRepository
    conversations: ConversationRepository
    usage: UsageRepository
    prompts: PromptRepository
    benchmarks: BenchmarkRepository
    chat: ChatService
    agents: AgentService
    projects: ProjectManager
    sandboxes: ExecutionManager
    pricing: PricingTable
    _vm_manager: object = None

    @property
    def vm_manager(self):
        """Created lazily: backend detection spawns PowerShell and can take seconds."""
        if self._vm_manager is None:
            from .virtualization.vm_manager import VMManager
            self._vm_manager = VMManager(self.settings.settings, self.audit)
            self.sandboxes.vm_manager = self._vm_manager
        return self._vm_manager

    def shutdown(self) -> None:
        if not self.settings.settings.privacy.store_chat_history:
            for c in self.conversations.list():
                self.conversations.delete(c.id)
        self.sandboxes.stop_all()
        self.tasks.shutdown()
        self.db.close()

    def delete_all_local_data(self) -> None:
        """Remove conversations, settings, projects copies, sandboxes and stored API keys."""
        for p in self.provider_repo.list():
            self.credentials.delete_api_key(p["id"])
        for sb in self.sandboxes.list():
            self.credentials.delete_api_key(f"sandbox-vm-{sb['id']}")
        self.sandboxes.stop_all()
        self.db.close()
        root = self.paths.root
        failed = False
        for child in root.iterdir():
            if child.name == "logs":
                continue
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
            except OSError:  # e.g. a file still locked by another thread on Windows
                failed = True
        if failed:
            (root / ".delete_pending").write_text("1")


def _finish_pending_delete(root: Path) -> None:
    marker = root / ".delete_pending"
    if marker.exists():
        for child in root.iterdir():
            if child.name == "logs":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass


def build_context(data_dir: Path | None = None, credential_backend=None, transport=None) -> AppContext:
    root = data_dir or default_data_dir()
    if root.exists():
        _finish_pending_delete(root)
    paths = AppPaths(root).ensure()
    settings = SettingsStore(paths.root / "settings.json")
    db = Database(paths.database)
    bus = EventBus()
    tasks = TaskManager(event_bus=bus)
    audit = AuditLog(db)
    credentials = CredentialManager(credential_backend, audit)
    provider_repo = ProviderRepository(db)
    registry = ProviderRegistry(provider_repo, credentials, transport=transport)
    registry.ensure_defaults(settings.settings)
    conversations = ConversationRepository(db)
    usage = UsageRepository(db)
    prompts = PromptRepository(db)
    if prompts.count() == 0:
        for title, body, cat, tags in STARTER_PROMPTS:
            prompts.create(title, body, cat, tags)
    chat = ChatService(conversations, usage, registry, bus,
                       ollama_options=lambda: ollama_options(settings.settings))
    agents = AgentService(agents_repo(db), audit)
    agents.ensure_builtins()
    projects = ProjectManager(projects_repo(db), paths.projects, audit)
    sandboxes = ExecutionManager(paths.sandboxes, sandboxes_repo(db), SandboxRunRepository(db),
                                 settings, audit, credentials)
    set_own_priority(settings.settings.resources.background_priority)
    return AppContext(paths, settings, db, bus, tasks, audit, credentials, registry, provider_repo,
                      conversations, usage, prompts, BenchmarkRepository(db), chat, agents, projects, sandboxes,
                      PricingTable(paths.root / "pricing.json"))
