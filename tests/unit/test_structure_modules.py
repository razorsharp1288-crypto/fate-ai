"""Tests for the modules that complete the documented project layout."""
import json
import time

import httpx
import pytest

from fate_ai.core.exceptions import ValidationError


def test_layout_matches_spec():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "fate_ai"
    for rel in ["ui/main_window.py", "ui/components", "ui/pages", "ui/dialogs", "ui/themes",
                "core/event_bus.py", "core/task_manager.py", "core/settings.py", "core/exceptions.py",
                "ai/providers", "ai/local_engine", "ai/model_manager", "ai/agents", "ai/chat",
                "virtualization/backends", "virtualization/vm_manager.py", "virtualization/snapshots.py",
                "virtualization/resource_limits.py", "sandbox/process_sandbox.py", "sandbox/container_sandbox.py",
                "sandbox/vm_sandbox.py", "sandbox/execution_manager.py", "hardware/detection.py", "hardware/cpu.py",
                "hardware/memory.py", "hardware/gpu.py", "hardware/storage.py", "security/credential_manager.py",
                "security/permissions.py", "security/audit.py", "security/redaction.py", "database/models.py",
                "database/repository.py", "database/migrations", "documents/parsers", "documents/indexing.py",
                "monitoring/metrics.py", "monitoring/collector.py", "projects/manager.py", "projects/versioning.py",
                "utilities/logging.py", "utilities/paths.py", "utilities/validation.py"]:
        assert (root / rel).exists(), rel


def test_validation():
    from fate_ai.utilities.validation import (is_insecure_remote, validate_env_name, validate_model_tag,
                                              validate_url)
    assert validate_url("https://api.openai.com/v1/") == "https://api.openai.com/v1"
    for bad in ("ftp://x", "localhost:1234", "https://user:pw@host"):
        with pytest.raises(ValidationError):
            validate_url(bad)
    assert is_insecure_remote("http://example.com") and not is_insecure_remote("http://127.0.0.1:11434")
    assert validate_model_tag("qwen2.5-coder:7b") == "qwen2.5-coder:7b"
    assert validate_model_tag("hf.co/org/model:Q4_K_M")
    for bad in ("", "a b", "x;rm -rf", "../x"):
        with pytest.raises(ValidationError):
            validate_model_tag(bad)
    with pytest.raises(ValidationError):
        validate_env_name("bad/name")


def test_paths(monkeypatch, tmp_path):
    from fate_ai.utilities.paths import default_data_dir, dir_size
    monkeypatch.setenv("FATE_AI_HOME", str(tmp_path))
    assert default_data_dir() == tmp_path.resolve()
    (tmp_path / "a.txt").write_bytes(b"x" * 10)
    assert dir_size(tmp_path) == 10


def test_hardware_component_modules():
    from fate_ai.hardware.cpu import detect_cpu
    from fate_ai.hardware.memory import detect_memory
    from fate_ai.hardware.storage import detect_storage
    from fate_ai.hardware.gpu import detect_gpus
    assert detect_cpu(sample=False).logical_threads >= 1
    assert detect_memory().total_gb > 0
    assert all(s.total_gb >= 1 for s in detect_storage())
    assert isinstance(detect_gpus(), list)


def test_migrations_package():
    from fate_ai.database.migrations import load
    from fate_ai.database.db import MIGRATIONS
    assert load() == MIGRATIONS and "CREATE TABLE conversations" in MIGRATIONS[0]


def test_models_module_used_by_repo(tmp_path):
    from fate_ai.database.db import Database
    from fate_ai.database.models import Conversation
    from fate_ai.database.repository import ConversationRepository
    assert isinstance(ConversationRepository(Database(tmp_path / "m.db")).create("t", "p", "m"), Conversation)


def test_document_index(tmp_path):
    from fate_ai.documents.indexing import DocumentIndex
    (tmp_path / "auth.py").write_text("def login(user, password):\n    return check_password(user, password)\n")
    (tmp_path / "notes.md").write_text("# Notes\nThe deployment uses kubernetes and helm charts.\n")
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.txt").write_text("password password password")
    idx = DocumentIndex()
    assert idx.add_folder(tmp_path) == 2
    hits = idx.search("how does login check the password")
    assert hits and hits[0].chunk.path == "auth.py"
    assert idx.search("kubernetes")[0].chunk.path == "notes.md"
    assert idx.search("zzzz") == []
    ctx = idx.context_for("password")
    assert "untrusted" in ctx and "[auth.py:1]" in ctx
    idx.save(tmp_path / "i.json")
    from fate_ai.documents.indexing import DocumentIndex as D
    assert D.load(tmp_path / "i.json").search("helm")[0].chunk.path == "notes.md"


def test_parsers_package_exports():
    from fate_ai.documents import parsers
    assert callable(parsers.parse) and callable(parsers.docx_text) and ".pdf" in parsers.SUPPORTED


def test_metrics_summary_and_csv():
    from fate_ai.monitoring.collector import MetricsCollector
    from fate_ai.monitoring.metrics import summarize, to_csv_rows
    c = MetricsCollector(gpu=False)
    for _ in range(3):
        c.sample()
    sm = summarize(c.history)
    assert sm.count == 3 and 0 <= sm.cpu_avg <= 100
    assert summarize(c.history, since=time.time() + 100) is None
    rows = to_csv_rows(c.history)
    assert rows[0][0] == "timestamp" and len(rows) == 4


def test_snapshot_manager(ctx):
    from fate_ai.virtualization.snapshots import CLEAN, SnapshotManager
    from fate_ai.virtualization.backends.base import BackendStatus, Cap, Snapshot, VirtualizationBackend, VMInfo

    class B(VirtualizationBackend):
        name, label, caps = "b", "B", {Cap.SNAPSHOT, Cap.STOP}

        def __init__(self):
            self.snaps, self.restored, self.state = [], None, "running"

        def status(self): return BackendStatus(True, "")
        def list(self): return [VMInfo("vm", "vm", "b", self.state)]
        def create(self, s): pass
        def start(self, i): self.state = "running"
        def stop(self, i, force=False): self.state = "stopped"
        def delete(self, i): pass
        def snapshots(self, i): return [Snapshot(n, n) for n in self.snaps]
        def create_snapshot(self, i, n): self.snaps.append(n)
        def restore_snapshot(self, i, n): self.restored = n
        def delete_snapshot(self, i, n): self.snaps.remove(n)

    b = B()
    m = SnapshotManager(b, ctx.audit)
    m.ensure_clean("vm")
    m.ensure_clean("vm")
    assert b.snaps == [CLEAN]
    name = m.create("vm")
    assert name.startswith("snapshot-")
    with pytest.raises(ValidationError):
        m.create("vm", "bad/name")
    m.revert_to_clean("vm")
    assert b.restored == CLEAN and b.state == "stopped"
    m.delete("vm", name)
    assert any(r["action"] == "snapshot_restored" for r in ctx.audit.recent())


def test_resource_limits_module():
    from fate_ai.virtualization import resource_limits, vm_manager
    assert vm_manager.validate_spec is resource_limits.validate_spec
    cpus, ram, disk = resource_limits.recommend()
    assert cpus >= 1 and ram >= 1024


def test_local_engine_manager(ctx):
    from fate_ai.ai.local_engine.engine import LocalEngineManager
    from fate_ai.ai.providers.registry import ProviderRegistry

    def handler(req):
        p = req.url.path
        if p == "/api/version":
            return httpx.Response(200, json={"version": "9.9"})
        if p == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "a:1b", "size": 1}]})
        if p == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "a:1b"}]})
        if p == "/api/pull":
            return httpx.Response(200, content=json.dumps({"status": "success"}).encode())
        raise httpx.ConnectError("no llama")
    reg = ProviderRegistry(ctx.provider_repo, ctx.credentials, transport=httpx.MockTransport(handler))
    eng = LocalEngineManager(reg, ctx.settings)
    st = eng.status()
    assert st.ollama_running and st.installed[0].id == "a:1b" and st.loaded and not st.llamacpp_running
    eng.pull("a:1b")
    with pytest.raises(ValidationError):
        eng.pull("bad tag;")


def test_themes_package():
    from fate_ai.ui.themes import C, chat_css, stylesheet
    assert C["accent"].startswith("#") and "QPushButton" in stylesheet() and "pre" in chat_css()
