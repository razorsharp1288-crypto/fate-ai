from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ...ai.agents.service import extract_tool_call
from ...ai.providers.base import ChatMessage, ChatRequest
from ...projects.manager import GitVersioning
from ..components.markdown_view import render
from ..components.widgets import Page, confirm, error, hbox, info
from ..components.worker import run_async
from ..theme import C, MONO_STACK, chat_css


class DiffHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        fmt = QTextCharFormat()
        if text.startswith("+") and not text.startswith("+++"):
            fmt.setForeground(QColor(C["ok"]))
        elif text.startswith("-") and not text.startswith("---"):
            fmt.setForeground(QColor(C["err"]))
        elif text.startswith("@@"):
            fmt.setForeground(QColor(C["accent_hi"]))
        else:
            return
        self.setFormat(0, len(text), fmt)


class DiffDialog(QDialog):
    def __init__(self, diff: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Review the changes before they are written to disk:"))
        view = QPlainTextEdit(diff or "(no changes)")
        view.setReadOnly(True)
        view.setStyleSheet(f"font-family:{MONO_STACK};")
        DiffHighlighter(view.document())
        lay.addWidget(view)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Write file")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class ProjectsPage(Page):
    def __init__(self, ctx):
        super().__init__("Projects", "Local workspaces. Agents can only touch files inside a project you open, and "
                                     "every write is shown as a diff for your approval.", scroll=False)
        self.ctx = ctx
        self.pid = None
        self.current_file = None
        self.agent_history: list[ChatMessage] = []
        for label, fn in (("New", self.new), ("Open folder", self.open_folder), ("Import zip", self.import_zip)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            self.header_actions.addWidget(b)

        split = QSplitter()
        self.body.addWidget(split, 1)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.projects = QListWidget()
        self.projects.currentItemChanged.connect(self._select)
        ll.addWidget(QLabel("Projects"))
        ll.addWidget(self.projects, 1)
        ll.addWidget(QLabel("Files"))
        self.tree = QListWidget()
        self.tree.itemDoubleClicked.connect(lambda it: self.open_file(it.text()))
        ll.addWidget(self.tree, 2)
        rm = QPushButton("Forget project")
        rm.clicked.connect(self.forget)
        exp = QPushButton("Export zip")
        exp.clicked.connect(self.export)
        ll.addLayout(hbox(exp, rm))
        split.addWidget(left)

        tabs = QTabWidget()
        split.addWidget(tabs)
        split.setSizes([260, 900])

        ed = QWidget()
        el = QVBoxLayout(ed)
        self.file_label = QLabel("Open a file from the list")
        self.file_label.setObjectName("Muted")
        self.editor = QPlainTextEdit()
        f = QFont()
        f.setFamilies(["Cascadia Code", "Consolas", "DejaVu Sans Mono"])
        f.setPointSize(10)
        self.editor.setFont(f)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        save = QPushButton("Save (review diff)")
        save.setObjectName("Primary")
        save.clicked.connect(self.save_file)
        newf = QPushButton("New file")
        newf.clicked.connect(self.new_file)
        sbx = QPushButton("Run tests in sandbox")
        sbx.clicked.connect(self.run_in_sandbox)
        el.addLayout(hbox(self.file_label, None, newf, sbx, save))
        el.addWidget(self.editor, 1)
        tabs.addTab(ed, "Editor")

        ag = QWidget()
        al = QVBoxLayout(ag)
        self.agent_combo = QComboBox()
        self.instructions = QPlainTextEdit()
        self.instructions.setPlaceholderText("Project-specific instructions for agents (coding style, goals…)")
        self.instructions.setFixedHeight(70)
        save_instr = QPushButton("Save instructions")
        save_instr.clicked.connect(self.save_instructions)
        al.addLayout(hbox(QLabel("Agent"), self.agent_combo, None, save_instr))
        al.addWidget(self.instructions)
        self.agent_view = QTextBrowser()
        self.agent_view.document().setDefaultStyleSheet(chat_css())
        al.addWidget(self.agent_view, 1)
        self.agent_input = QPlainTextEdit()
        self.agent_input.setFixedHeight(64)
        self.agent_input.setPlaceholderText("Ask the agent about this project, e.g. 'Find the bug in main.py'")
        ask = QPushButton("Ask agent")
        ask.setObjectName("Primary")
        ask.clicked.connect(self.ask_agent)
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: (self.agent_history.clear(), self.agent_view.clear()))
        al.addLayout(hbox(self.agent_input, ask, clear))
        self.agent_status = QLabel("")
        self.agent_status.setObjectName("Dim")
        al.addWidget(self.agent_status)
        tabs.addTab(ag, "Agent")

        gw = QWidget()
        gl = QVBoxLayout(gw)
        self.git_info = QPlainTextEdit()
        self.git_info.setReadOnly(True)
        self.git_info.setStyleSheet(f"font-family:{MONO_STACK};")
        DiffHighlighter(self.git_info.document())
        gi = QPushButton("Initialise Git")
        gi.clicked.connect(self.git_init)
        gc = QPushButton("Commit all changes")
        gc.clicked.connect(self.git_commit)
        gr = QPushButton("Refresh")
        gr.clicked.connect(self.git_refresh)
        gl.addLayout(hbox(gi, gc, None, gr))
        gl.addWidget(self.git_info, 1)
        tabs.addTab(gw, "Version history")
        self.reload()

    def on_show(self):
        self.agent_combo.clear()
        for a in self.ctx.agents.list():
            self.agent_combo.addItem(a["name"], a)
        self.reload()

    def reload(self, select=None):
        cur = select or self.pid
        self.projects.blockSignals(True)
        self.projects.clear()
        for p in self.ctx.projects.list():
            it = QListWidgetItem(p["name"])
            it.setToolTip(p["path"])
            it.setData(Qt.UserRole, p["id"])
            self.projects.addItem(it)
            if p["id"] == cur:
                self.projects.setCurrentItem(it)
        self.projects.blockSignals(False)
        if self.projects.currentItem():
            self._select()

    def _select(self, *_):
        it = self.projects.currentItem()
        if not it:
            return
        self.pid = it.data(Qt.UserRole)
        p = self.ctx.projects.get(self.pid)
        if not Path(p["path"]).exists():
            self.tree.clear()
            self.file_label.setText("Project folder no longer exists.")
            return
        self.instructions.setPlainText(p["instructions"])
        self.tree.clear()
        self.tree.addItems(self.ctx.projects.tree(self.pid))
        self.git_refresh()

    def new(self):
        name, ok = QInputDialog.getText(self, "New project", "Project name:")
        if ok and name.strip():
            try:
                p = self.ctx.projects.create(name.strip())
            except Exception as e:
                error(self, str(e))
                return
            self.reload(p["id"])

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open project folder")
        if d:
            p = self.ctx.projects.import_folder(Path(d))
            self.reload(p["id"])

    def import_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import project zip", "", "Zip (*.zip)")
        if f:
            try:
                p = self.ctx.projects.import_zip(Path(f), Path(f).stem)
            except Exception as e:
                error(self, str(e))
                return
            self.reload(p["id"])

    def export(self):
        if not self.pid:
            return
        p = self.ctx.projects.get(self.pid)
        f, _ = QFileDialog.getSaveFileName(self, "Export project", str(self.ctx.paths.exports / f"{p['name']}.zip"),
                                           "Zip (*.zip)")
        if f:
            self.ctx.projects.export_zip(self.pid, Path(f))
            info(self, f"Exported to {f}")

    def forget(self):
        if self.pid and confirm(self, "Forget project", "Remove this project from FATE AI? Files on disk are not "
                                                        "deleted."):
            self.ctx.projects.remove(self.pid)
            self.pid = None
            self.tree.clear()
            self.reload()

    def open_file(self, rel):
        try:
            self.editor.setPlainText(self.ctx.projects.read(self.pid, rel))
        except Exception as e:
            error(self, str(e))
            return
        self.current_file = rel
        self.file_label.setText(rel)

    def new_file(self):
        if not self.pid:
            return
        rel, ok = QInputDialog.getText(self, "New file", "Relative path:")
        if ok and rel.strip():
            self.current_file = rel.strip()
            self.file_label.setText(self.current_file + " (new)")
            self.editor.clear()

    def save_file(self):
        if not self.pid or not self.current_file:
            return
        content = self.editor.toPlainText()
        try:
            diff = self.ctx.projects.diff(self.pid, self.current_file, content)
        except Exception as e:
            error(self, str(e))
            return
        if DiffDialog(diff, f"Save {self.current_file}", self).exec():
            try:
                self.ctx.projects.write(self.pid, self.current_file, content, confirmed=True)
            except Exception as e:
                error(self, str(e))
                return
            self._select()

    def save_instructions(self):
        if self.pid:
            self.ctx.projects.repo.update(self.pid, instructions=self.instructions.toPlainText())

    def _sandbox_for_project(self):
        p = self.ctx.projects.get(self.pid)
        name = f"project-{p['name']}"
        sb = next((s for s in self.ctx.sandboxes.list() if s["name"] == name), None)
        level = "container" if any(b.name in ("docker", "podman") for b in self.ctx.vm_manager.available()) else "process"
        if sb is None:
            sb = self.ctx.sandboxes.create(name, level)
        self.ctx.sandboxes.reset(sb["id"])
        self.ctx.sandboxes.import_project(sb["id"], Path(p["path"]))
        return sb, Path(p["path"]).name

    def run_in_sandbox(self):
        if not self.pid:
            return
        cmd, ok = QInputDialog.getText(self, "Run in sandbox", "Command (run from the project folder):",
                                       text="python -m pytest -q")
        if not ok or not cmd.strip():
            return
        try:
            sb, folder = self._sandbox_for_project()
        except Exception as e:
            error(self, str(e))
            return
        consent = sb["level"] != "process" or confirm(
            self, "No container engine", "Docker/Podman is not available, so this runs as a restricted process on "
                                         "your PC (Level 1, not a security boundary). Continue?", danger=True)
        if not consent:
            return
        self.agent_status.setText(f"Running in sandbox '{sb['name']}'…")
        argv = self.ctx.sandboxes.parse_command(cmd)
        sid = sb["id"]

        def work():
            return self.ctx.sandboxes.run(sid, self._cd_command(sb["level"], folder, argv), host_consent=True)

        def done(res):
            QMessageBox.information(self, "Sandbox result",
                                    f"Exit code {res.exit_code} in {res.duration_ms / 1000:.1f}s\n\n"
                                    f"{(res.stdout + res.stderr)[-3000:]}")
            self.agent_status.setText("")
        run_async(work, on_done=done, on_error=lambda e: error(self, str(e)))

    @staticmethod
    def _cd_command(level, folder, argv):
        import shlex
        import sys
        if level == "container":
            return "sh -c " + shlex.quote(f"cd {shlex.quote(folder)} && " + " ".join(shlex.quote(a) for a in argv))
        if sys.platform == "win32":
            return "cmd /c " + f'cd /d "{folder}" && ' + " ".join(f'"{a}"' if " " in a else a for a in argv)
        return "sh -c " + shlex.quote(f"cd {shlex.quote(folder)} && " + " ".join(shlex.quote(a) for a in argv))

    # -- agent loop -------------------------------------------------------
    def _render_agent(self, extra=""):
        parts = [f"<style>{chat_css()}</style>"]
        for m in self.agent_history:
            who = "YOU" if m.role == "user" else "AGENT"
            body = render(m.content) if m.role == "assistant" else m.content.replace("\n", "<br>")
            parts.append(f'<div class="row"><div class="who">{who}</div>{body}</div>')
        parts.append(extra)
        self.agent_view.setHtml("".join(parts))
        self.agent_view.verticalScrollBar().setValue(self.agent_view.verticalScrollBar().maximum())

    def ask_agent(self):
        if not self.pid:
            error(self, "Open a project first.")
            return
        text = self.agent_input.toPlainText().strip()
        if not text:
            return
        agent = self.agent_combo.currentData()
        provider = agent.get("provider") or self.ctx.settings.settings.ai.default_provider
        model = agent.get("model") or self.ctx.settings.settings.ai.default_model
        if not model:
            error(self, "Set a default model (Settings → AI) or assign one to the agent.")
            return
        self.agent_input.clear()
        self.agent_history.append(ChatMessage("user", text))
        self._render_agent()
        self._agent_turn(agent, provider, model, steps=0)

    def _agent_turn(self, agent, provider, model, steps):
        project = self.ctx.projects.get(self.pid)
        system = self.ctx.agents.system_prompt(agent, project)
        req = ChatRequest(model, list(self.agent_history), system=system, max_tokens=2048,
                          temperature=self.ctx.settings.settings.ai.temperature)
        self.agent_status.setText(f"{agent['name']} is thinking ({provider} · {model})…")

        def work():
            return self.ctx.providers.get(provider).chat(req)[0]

        def done(reply):
            self.agent_history.append(ChatMessage("assistant", reply))
            self._render_agent()
            call = extract_tool_call(reply)
            if call and steps < 6:
                guard = self.ctx.agents.guard(agent, confirm=lambda msg: confirm(self, "Agent permission", msg),
                                              extra_paths=[project["path"]])
                result = self.ctx.agents.execute_tool(
                    call, guard, project["path"], sandbox_runner=self._agent_sandbox,
                    system_info=self._system_info)
                self.agent_history.append(ChatMessage("user", f"Tool result for {call.tool}:\n{result[:20000]}"))
                self._render_agent()
                self._select()
                self._agent_turn(agent, provider, model, steps + 1)
            else:
                self.agent_status.setText("")
        run_async(work, on_done=done, on_error=lambda e: (self.agent_status.setText(""), error(self, str(e))))

    def _agent_sandbox(self, command):
        sb, folder = self._sandbox_for_project()
        argv = self.ctx.sandboxes.parse_command(command)
        return self.ctx.sandboxes.run(sb["id"], self._cd_command(sb["level"], folder, argv), host_consent=True)

    @staticmethod
    def _system_info():
        from ...hardware.detection import detect_cpu, detect_gpus, detect_memory
        cpu, mem = detect_cpu(sample=False), detect_memory()
        gpus = ", ".join(f"{g.name} ({g.vram_total_gb or '?'} GB)" for g in detect_gpus()) or "none detected"
        return f"CPU: {cpu.model} ({cpu.physical_cores}C/{cpu.logical_threads}T). RAM: {mem.total_gb} GB " \
               f"({mem.available_gb} GB free). GPUs: {gpus}."

    # -- git --------------------------------------------------------------
    def _git(self):
        return GitVersioning(Path(self.ctx.projects.get(self.pid)["path"])) if self.pid else None

    def git_refresh(self):
        g = self._git()
        if not g:
            return
        if not g.available:
            self.git_info.setPlainText("Git is not installed. Install it from git-scm.com to enable version history.")
        elif not g.is_repo():
            self.git_info.setPlainText("This project is not a Git repository. Click 'Initialise Git' to start "
                                       "tracking changes.")
        else:
            self.git_info.setPlainText("Recent commits:\n" + "\n".join(g.log()) + "\n\nUncommitted changes:\n"
                                       + (g.status() or "(none)") + "\n\n" + g.diff()[:50000])

    def git_init(self):
        g = self._git()
        if g and g.available:
            g.init()
            self.git_refresh()

    def git_commit(self):
        g = self._git()
        if not g:
            return
        msg, ok = QInputDialog.getText(self, "Commit", "Commit message:", text="Update via FATE AI")
        if ok and msg.strip():
            ok2, out = g.commit_all(msg.strip())
            info(self, out or ("Committed." if ok2 else "Nothing to commit."))
            self.git_refresh()
