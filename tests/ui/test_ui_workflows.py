"""UI workflow tests driving real widgets against a local HTTP server speaking the Ollama protocol."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("pytestqt")
from PySide6.QtCore import Qt  # noqa: E402

from fate_ai.bootstrap import build_context  # noqa: E402
from fate_ai.security.credential_manager import MemoryBackend  # noqa: E402


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            return self._json({"version": "0.0-test"})
        if self.path == "/api/tags":
            return self._json({"models": [{"name": "tiny:latest", "size": 123456789,
                                           "details": {"parameter_size": "0.5B", "quantization_level": "Q4_K_M",
                                                       "family": "qwen2"}}]})
        if self.path == "/api/ps":
            return self._json({"models": []})
        self._json({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            q = body["messages"][-1]["content"]
            for word in ["You ", "said: ", q]:
                self.wfile.write((json.dumps({"message": {"content": word}, "done": False}) + "\n").encode())
                self.wfile.flush()
            self.wfile.write((json.dumps({"done": True, "prompt_eval_count": 5, "eval_count": 3}) + "\n").encode())
            return
        self._json({}, 404)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def uictx(tmp_path, server):
    c = build_context(tmp_path / "ui", credential_backend=MemoryBackend())
    c.settings.update(onboarding_complete=True, local={"ollama_url": server},
                      ai={"default_provider": "ollama", "default_model": "tiny:latest"})
    p = c.provider_repo.get("ollama")
    c.provider_repo.upsert("ollama", p["kind"], p["name"], server)
    yield c
    c.shutdown()


def test_chat_stream_persist_and_reopen(qtbot, uictx, tmp_path):
    from fate_ai.ui.main_window import MainWindow
    win = MainWindow(uictx)
    qtbot.addWidget(win)
    win.navigate("chat")
    chat = win.page("chat")
    qtbot.waitUntil(lambda: chat.model.count() > 0, timeout=5000)
    assert chat.model.currentText() == "tiny:latest"
    chat.input.setPlainText("hello fate")
    chat.send()
    qtbot.waitUntil(lambda: not chat.streaming, timeout=10000)
    msgs = uictx.conversations.messages(chat.conv_id)
    assert [m["content"] for m in msgs] == ["hello fate", "You said: hello fate"]
    assert "You said: hello fate" in chat.view.toPlainText()
    assert "3 out tokens" in chat.status.text()
    cid = chat.conv_id
    win.close()
    uictx.db.close()
    # "restart": new context on same data folder
    c2 = build_context(uictx.paths.root, credential_backend=MemoryBackend())
    try:
        conv = c2.conversations.get(cid)
        assert conv.provider == "ollama" and conv.model == "tiny:latest"
        assert len(c2.conversations.messages(cid)) == 2
    finally:
        c2.shutdown()


def test_models_page_lists_installed(qtbot, uictx):
    from fate_ai.ui.pages.models import ModelsPage
    page = ModelsPage(uictx)
    qtbot.addWidget(page)
    page.refresh()
    qtbot.waitUntil(lambda: page.installed.rowCount() == 1, timeout=5000)
    assert page.installed.item(0, 0).text() == "tiny:latest"
    assert "Running" in page.ollama_badge.text()
    qtbot.waitUntil(lambda: page.catalog.rowCount() > 10, timeout=15000)


def test_provider_test_connection(qtbot, uictx):
    from fate_ai.ui.pages.providers import ProvidersPage
    page = ProvidersPage(uictx)
    qtbot.addWidget(page)
    for i in range(page.list.count()):
        if page.list.item(i).data(Qt.UserRole) == "ollama":
            page.list.setCurrentRow(i)
    page.test()
    qtbot.waitUntil(lambda: page.result.label.text().startswith(("✓", "✗")), timeout=5000)
    assert page.result.label.text().startswith("✓")


def test_sandbox_page_runs_code(qtbot, uictx, monkeypatch):
    from fate_ai.ui.pages import sandbox as sbmod
    monkeypatch.setattr(sbmod, "confirm", lambda *a, **k: True)
    sb = uictx.sandboxes.create("ui-test", "process")
    uictx.sandboxes.write_file(sb["id"], "hello.py", "print('sandbox says hi')")
    page = sbmod.SandboxPage(uictx)
    qtbot.addWidget(page)
    page.reload(sb["id"])
    page.cmd.setText("python hello.py")
    page.run()
    qtbot.waitUntil(lambda: not page.running, timeout=15000)
    assert "sandbox says hi" in page.console.toPlainText()
    assert page.t_status.value.text() == "0"


def test_onboarding_completes_without_cloud_or_models(qtbot, uictx):
    from fate_ai.ui.dialogs.onboarding import OnboardingDialog
    uictx.settings.update(onboarding_complete=False)
    d = OnboardingDialog(uictx)
    qtbot.addWidget(d)
    d.choice.button(0).setChecked(True)  # local only
    for _ in range(12):
        if d.stack.currentIndex() == d.stack.count() - 1:
            break
        d._next()
    d._next()
    assert uictx.settings.settings.onboarding_complete


def test_every_page_builds(qtbot, uictx):
    from fate_ai.ui.main_window import NAV, MainWindow
    win = MainWindow(uictx)
    qtbot.addWidget(win)
    for key, _, _ in NAV:
        win.navigate(key)
        assert type(win.page(key)).__name__ != "QLabel", f"page {key} failed to build"


def test_blueprints_auto3d_and_export(qtbot, uictx, tmp_path, monkeypatch):
    from fate_ai.ui.pages import blueprints as bpmod
    page = bpmod.BlueprintsPage(uictx)
    qtbot.addWidget(page)
    page.idea.setPlainText("A quadcopter drone for aerial photos")
    page.auto_3d()
    assert len(page.parts) >= 10 and page.bid
    assert "drone" in page.status.text().lower()
    page.table.selectRow(0)
    page.mirror_part()
    n = len(page.parts)
    page.delete_part()
    assert len(page.parts) == n - 1
    monkeypatch.setattr(bpmod.QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "m.stl"), ""))
    monkeypatch.setattr(bpmod, "info", lambda *a, **k: None)
    page.export("stl")
    assert (tmp_path / "m.stl").read_text().startswith("solid")
    page.viewer.set_view("front")
    page.viewer.grab()  # renders without error


def test_blueprint_ai_generation_via_local_server(qtbot, uictx):
    """The fake Ollama echoes the prompt, which contains no JSON -> a clear error, no crash."""
    from fate_ai.ui.pages import blueprints as bpmod
    errors = []
    page = bpmod.BlueprintsPage(uictx)
    qtbot.addWidget(page)
    bpmod.error = lambda *a, **k: errors.append(a)
    page.on_show()
    qtbot.waitUntil(lambda: page.model.count() > 0, timeout=5000)
    page.idea.setPlainText("an exosuit")
    page.generate_ai()
    qtbot.waitUntil(lambda: page.gen_btn.isEnabled(), timeout=10000)
    assert "failed" in page.status.text().lower() and errors


def test_api_keys_paste_autoconnects(qtbot, uictx, monkeypatch):
    from fate_ai.ai.providers import autodetect
    from fate_ai.ui.pages.api_keys import APIKeysPage
    calls = []

    def fake_probe(preset, key, transport=None, lenient=False):
        calls.append(preset.id)
        return autodetect.ProbeResult(preset, preset.id == "groq", "ok", ["llama-3.3-70b"])
    monkeypatch.setattr(autodetect, "_probe", fake_probe)
    page = APIKeysPage(uictx)
    qtbot.addWidget(page)
    page.any_key.setText("gsk_abcdefghijklmnopqrstuvwxyz")   # just paste — no button press
    qtbot.waitUntil(lambda: "Connected" in page.key_status.text(), timeout=5000)
    assert calls == ["groq"]
    assert uictx.credentials.get_api_key("groq") == "gsk_abcdefghijklmnopqrstuvwxyz"
    assert uictx.provider_repo.get("groq")["default_model"] == "llama-3.3-70b"
    assert page.any_key.text() == "" and page.open_chat.isVisibleTo(page)
    # unknown format asks before trying other services
    page.any_key.setText("weirdformat123456789")
    page.connect_key()
    assert page.try_all_btn.isVisibleTo(page) and len(calls) == 1
    page.catalog.search.setText("gemini")
    assert page.catalog.grid.count() == 1


def test_command_palette_filters():
    from fate_ai.ui.dialogs.command_palette import _score
    assert _score("bp", "Go to Blueprints") > 0
    assert _score("blue", "Go to Blueprints") > _score("blue", "xyz")


def test_pc_control_page_turn_on_and_run(qtbot, uictx, monkeypatch):
    from fate_ai.ui.pages import computer as cmod
    monkeypatch.setattr(cmod, "confirm", lambda *a, **k: True)
    page = cmod.ComputerPage(uictx)
    qtbot.addWidget(page)
    page.on_show()
    assert not page.run_btn.isEnabled()
    page.turn_on()
    assert uictx.settings.settings.computer.enabled and page.run_btn.isEnabled()
    qtbot.waitUntil(lambda: page.model.count() > 0, timeout=5000)
    page.hide_me.setChecked(False)
    page.task.setPlainText("say hi")          # fake Ollama echoes text without an action -> finishes
    page.run()
    qtbot.waitUntil(lambda: page.cancel is None, timeout=10000)
    assert "say hi" in page.log.toPlainText()
    assert page.overlay is None


def test_settings_voice_and_power_tabs(qtbot, uictx, monkeypatch):
    from fate_ai.ui.pages import settings as smod
    monkeypatch.setattr(smod, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(smod, "info", lambda *a, **k: None)
    page = smod.SettingsPage(uictx)
    qtbot.addWidget(page)
    page.show_tab("PC Control & Power")
    page._full_power()
    c = uictx.settings.settings.computer
    assert c.enabled and c.approval == "auto_all" and all(getattr(c, k) for k in page.pc_caps)
    assert uictx.settings.settings.resources.preset == "max"
