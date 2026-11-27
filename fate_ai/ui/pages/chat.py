from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from ...core.task_manager import CancelToken
from ...documents.parsers import SUPPORTED, parse, wrap_untrusted
from ..components.icons import icon
from ..components.markdown_view import render
from ..components.widgets import Badge, confirm, error, h, info
from ..components.worker import run_async
from ..themes import C, chat_css


class ChatInput(QPlainTextEdit):
    submit = Signal()

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.submit.emit()
            return
        super().keyPressEvent(e)


class ChatSettingsDialog(QDialog):
    def __init__(self, conv, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chat settings")
        self.setMinimumWidth(520)
        f = QFormLayout(self)
        self.system = QPlainTextEdit(conv.system_prompt)
        self.system.setPlaceholderText("System prompt / custom instructions for this chat")
        self.system.setMinimumHeight(140)
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0, 2)
        self.temp.setSingleStep(0.1)
        self.temp.setValue(conv.temperature)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(16, 200_000)
        self.max_tokens.setValue(conv.max_tokens)
        f.addRow("System prompt", self.system)
        f.addRow("Temperature", self.temp)
        f.addRow("Max output tokens", self.max_tokens)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class ChatPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self.conv_id: int | None = None
        self.streaming = False
        self.cancel: CancelToken | None = None
        self.stream_buf = ""
        self.pending_user: str | None = None
        self.attachment = None
        self._render_timer = QTimer(self, interval=60, singleShot=True, timeout=self._render)
        self._build()
        self.reload_conversations()
        self._load_providers()

    # ------------------------------------------------------------------ UI
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        root.addWidget(split)

        left = QWidget()
        left.setStyleSheet(f"background:{C['bg2']};")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 18, 10, 14)
        top = QHBoxLayout()
        t = QLabel("Chats")
        t.setObjectName("H2")
        top.addWidget(t)
        top.addStretch(1)
        imp = QPushButton("Import")
        imp.setObjectName("Ghost")
        imp.clicked.connect(self.import_chat)
        top.addWidget(imp)
        ll.addLayout(top)
        new = QPushButton(" New chat")
        new.setIcon(icon("plus", "#FFFFFF"))
        new.setObjectName("Primary")
        new.clicked.connect(self.new_chat)
        ll.addWidget(new)
        self.search = QLineEdit(placeholderText="Search conversations…")
        self.search.textChanged.connect(lambda: self.reload_conversations())
        ll.addWidget(self.search)
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget{background:transparent;border:none;} QListWidget::item{border-radius:8px;"
                                "padding:8px;margin:1px 0;}")
        self.list.currentItemChanged.connect(self._on_select)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        ll.addWidget(self.list, 1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 14, 20, 14)
        bar = QHBoxLayout()
        self.title = QLabel("New chat")
        self.title.setObjectName("H2")
        bar.addWidget(self.title, 1)
        self.provider = QComboBox()
        self.provider.setMinimumWidth(150)
        self.provider.currentIndexChanged.connect(self._on_provider_changed)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumWidth(240)
        self.model.lineEdit().setPlaceholderText("Select or type a model")
        self.model.currentTextChanged.connect(self._on_model_changed)
        refresh = QPushButton("Refresh")
        refresh.setToolTip("Reload the model list from the provider")
        refresh.clicked.connect(lambda: self._load_models(self.provider.currentData()))
        self.agent = QComboBox()
        self.agent.setToolTip("Apply an agent persona (sets the system prompt)")
        self.agent.addItem("No agent", None)
        for a in self.ctx.agents.list():
            self.agent.addItem(a["name"], a)
        self.agent.activated.connect(self._apply_agent)
        settings = QPushButton("Settings")
        settings.clicked.connect(self.edit_settings)
        self.local_badge = Badge("")
        for w in (self.local_badge, self.provider, self.model, refresh, self.agent, settings):
            bar.addWidget(w)
        rl.addLayout(bar)

        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._on_anchor)
        self.view.document().setDefaultStyleSheet(chat_css())
        rl.addWidget(self.view, 1)

        self.attach_bar = QHBoxLayout()
        self.attach_label = QLabel("")
        self.attach_label.setObjectName("Muted")
        self.attach_clear = QPushButton("Remove")
        self.attach_clear.setObjectName("Ghost")
        self.attach_clear.clicked.connect(self._clear_attachment)
        self.attach_bar.addWidget(self.attach_label, 1)
        self.attach_bar.addWidget(self.attach_clear)
        self.attach_clear.hide()
        rl.addLayout(self.attach_bar)

        box = QWidget()
        box.setStyleSheet(f"QWidget#InputBox{{background:{C['card']};border:1px solid {C['border']};"
                          f"border-radius:14px;}}")
        box.setObjectName("InputBox")
        bl = QHBoxLayout(box)
        bl.setContentsMargins(10, 8, 10, 8)
        att = QPushButton()
        att.setIcon(icon("attach"))
        att.setObjectName("Ghost")
        att.setToolTip("Attach a document (parsed locally)")
        att.clicked.connect(self.attach)
        self.input = ChatInput()
        self.input.setPlaceholderText("Message FATE AI…  (Enter to send, Shift+Enter for a new line)")
        self.input.setFixedHeight(76)
        self.input.setStyleSheet("QPlainTextEdit{border:none;background:transparent;}")
        self.input.submit.connect(self.send)
        self.send_btn = QPushButton()
        self.send_btn.setIcon(icon("send", "#FFFFFF"))
        self.send_btn.setObjectName("Primary")
        self.send_btn.setFixedSize(44, 44)
        self.send_btn.clicked.connect(self._send_or_stop)
        bl.addWidget(att, 0, Qt.AlignBottom)
        bl.addWidget(self.input, 1)
        bl.addWidget(self.send_btn, 0, Qt.AlignBottom)
        rl.addWidget(box)
        self.status = QLabel("")
        self.status.setObjectName("Dim")
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([260, 900])
        split.setStretchFactor(1, 1)
        self._render()

    # ------------------------------------------------------------------ providers/models
    def _load_providers(self):
        self.provider.blockSignals(True)
        self.provider.clear()
        for p in self.ctx.providers.configs():
            if p["enabled"]:
                self.provider.addItem(p["name"], p["id"])
        default = self.ctx.settings.settings.ai.default_provider
        idx = self.provider.findData(default)
        self.provider.setCurrentIndex(max(0, idx))
        self.provider.blockSignals(False)
        self._on_provider_changed()

    def _on_provider_changed(self):
        pid = self.provider.currentData()
        if not pid:
            return
        cfg = self.ctx.provider_repo.get(pid)
        local = self.ctx.providers.is_local(cfg)
        self.local_badge.set("LOCAL" if local else "CLOUD", "ok" if local else "info")
        self._load_models(pid)
        if self.conv_id and not self.streaming:
            conv = self.ctx.conversations.get(self.conv_id)
            if conv and conv.provider != pid:
                self.ctx.conversations.update(self.conv_id, provider=pid, model="")

    def _load_models(self, pid, keep: str | None = None):
        if keep is None:
            conv = self.ctx.conversations.get(self.conv_id) if self.conv_id else None
            keep = conv.model if conv and conv.provider == pid else (
                self.ctx.provider_repo.get(pid) or {}).get("default_model", "")
            if not keep and pid == self.ctx.settings.settings.ai.default_provider:
                keep = self.ctx.settings.settings.ai.default_model
        self.model.blockSignals(True)
        self.model.clear()
        if keep:
            self.model.addItem(keep)
        self.model.setCurrentText(keep or "")
        self.model.blockSignals(False)
        self.status.setText("Loading models…")

        def done(models):
            if self.provider.currentData() != pid:
                return
            cur = self.model.currentText()
            self.model.blockSignals(True)
            self.model.clear()
            ids = [m.id for m in models]
            self.model.addItems(ids)
            if cur:
                self.model.setCurrentText(cur)
            elif ids:
                self.model.setCurrentIndex(0)
                self._on_model_changed(ids[0])
            self.model.blockSignals(False)
            self.status.setText(f"{len(ids)} models available from {self.provider.currentText()}."
                                if ids else "No models found. Install a local model or check the provider.")

        def fail(e):
            if self.provider.currentData() == pid:
                self.status.setText(f"Could not list models: {e}")
        run_async(lambda: self.ctx.providers.get(pid).list_models(), on_done=done, on_error=fail)

    def _on_model_changed(self, text):
        if self.conv_id and text and not self.streaming:
            self.ctx.conversations.update(self.conv_id, provider=self.provider.currentData(), model=text)

    def _apply_agent(self):
        a = self.agent.currentData()
        if not a:
            return
        if not self.conv_id:
            self.new_chat()
        self.ctx.conversations.update(self.conv_id, system_prompt=self.ctx.agents.system_prompt(a))
        if a.get("provider") and a.get("model"):
            self.ctx.conversations.update(self.conv_id, provider=a["provider"], model=a["model"])
            self.open_conversation(self.conv_id)
        self.status.setText(f"Agent '{a['name']}' applied to this chat.")

    # ------------------------------------------------------------------ conversations
    def reload_conversations(self, select: int | None = None):
        self.list.blockSignals(True)
        self.list.clear()
        for c in self.ctx.conversations.list(self.search.text().strip()):
            it = QListWidgetItem(c.title)
            it.setData(Qt.UserRole, c.id)
            it.setToolTip(f"{c.provider} · {c.model}\nUpdated {c.updated_at}")
            self.list.addItem(it)
            if c.id == (select or self.conv_id):
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _on_select(self, cur, _prev):
        if cur and not self.streaming:
            self.open_conversation(cur.data(Qt.UserRole))

    def open_conversation(self, cid: int):
        conv = self.ctx.conversations.get(cid)
        if not conv:
            return
        self.conv_id = cid
        self.title.setText(conv.title)
        idx = self.provider.findData(conv.provider)
        if idx >= 0:
            self.provider.blockSignals(True)
            self.provider.setCurrentIndex(idx)
            self.provider.blockSignals(False)
            self._on_provider_changed_silent(conv)
        self._render()

    def _on_provider_changed_silent(self, conv):
        cfg = self.ctx.provider_repo.get(conv.provider)
        if cfg:
            local = self.ctx.providers.is_local(cfg)
            self.local_badge.set("LOCAL" if local else "CLOUD", "ok" if local else "info")
        self._load_models(conv.provider, keep=conv.model)

    def new_chat(self):
        if self.streaming:
            return
        s = self.ctx.settings.settings.ai
        conv = self.ctx.chat.new_conversation(self.provider.currentData() or s.default_provider,
                                              self.model.currentText().strip(), s.default_system_prompt,
                                              s.temperature, s.max_tokens)
        self.conv_id = conv.id
        self.reload_conversations(conv.id)
        self.title.setText(conv.title)
        self._render()
        self.input.setFocus()

    def _list_menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        cid = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Rename", lambda: self.rename(cid))
        m.addAction("Export…", lambda: self.export_chat(cid))
        m.addAction("Duplicate (branch)", lambda: self._branch_all(cid))
        m.addSeparator()
        m.addAction("Delete", lambda: self.delete(cid))
        m.exec(self.list.mapToGlobal(pos))

    def rename(self, cid):
        conv = self.ctx.conversations.get(cid)
        name, ok = QInputDialog.getText(self, "Rename chat", "Title", text=conv.title)
        if ok and name.strip():
            self.ctx.conversations.update(cid, title=name.strip()[:200])
            self.reload_conversations()
            if cid == self.conv_id:
                self.title.setText(name.strip())

    def delete(self, cid):
        if confirm(self, "Delete chat", "Delete this conversation permanently?", danger=True):
            self.ctx.conversations.delete(cid)
            if cid == self.conv_id:
                self.conv_id = None
                self.title.setText("New chat")
            self.reload_conversations()
            self._render()

    def export_chat(self, cid):
        conv = self.ctx.conversations.get(cid)
        path, flt = QFileDialog.getSaveFileName(self, "Export chat", str(self.ctx.paths.exports / f"{conv.title[:40]}.json"),
                                                "FATE chat (*.json);;Markdown (*.md)")
        if not path:
            return
        data = self.ctx.conversations.export(cid)
        if path.endswith(".md"):
            lines = [f"# {conv.title}", f"*{conv.provider} · {conv.model}*", ""]
            for m in data["messages"]:
                lines += [f"## {m['role'].title()}", m["content"], ""]
            Path(path).write_text("\n".join(lines), "utf-8")
        else:
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        self.status.setText(f"Exported to {path}")

    def import_chat(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import chat", str(self.ctx.paths.exports), "FATE chat (*.json)")
        if not path:
            return
        try:
            conv = self.ctx.conversations.import_(json.loads(Path(path).read_text("utf-8")))
        except Exception as e:
            error(self, f"Could not import: {e}")
            return
        self.reload_conversations(conv.id)
        self.open_conversation(conv.id)

    def _branch_all(self, cid):
        msgs = self.ctx.conversations.messages(cid)
        new = self.ctx.conversations.branch(cid, msgs[-1]["id"] if msgs else 0)
        self.reload_conversations(new.id)
        self.open_conversation(new.id)

    def edit_settings(self):
        if not self.conv_id:
            self.new_chat()
        conv = self.ctx.conversations.get(self.conv_id)
        d = ChatSettingsDialog(conv, self)
        if d.exec():
            self.ctx.conversations.update(self.conv_id, system_prompt=d.system.toPlainText(),
                                          temperature=d.temp.value(), max_tokens=d.max_tokens.value())

    # ------------------------------------------------------------------ attachments
    def attach(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED))
        path, _ = QFileDialog.getOpenFileName(self, "Attach document", "", f"Documents ({exts})")
        if not path:
            return
        try:
            doc = parse(path)
        except Exception as e:
            error(self, str(e), "Cannot read file")
            return
        self.attachment = doc
        warn = (" — " + " ".join(doc.warnings)) if doc.warnings else ""
        self.attach_label.setText(f"📎 {doc.name} · {len(doc.text):,} characters parsed locally{warn}")
        self.attach_clear.show()

    def _clear_attachment(self):
        self.attachment = None
        self.attach_label.setText("")
        self.attach_clear.hide()

    # ------------------------------------------------------------------ sending
    def _send_or_stop(self):
        if self.streaming:
            self.stop()
        else:
            self.send()

    def stop(self):
        if self.cancel:
            self.cancel.cancel()
            self.status.setText("Stopping…")

    def _is_cloud(self, pid) -> bool:
        cfg = self.ctx.provider_repo.get(pid)
        return bool(cfg) and not self.ctx.providers.is_local(cfg)

    def send(self):
        if self.streaming:
            return
        text = self.input.toPlainText().strip()
        if not text and not self.attachment:
            return
        if not self.model.currentText().strip():
            error(self, "Choose a model first. For local AI install one on the AI Models page; for cloud AI add "
                        "an API key on the API Keys page.", "No model selected")
            return
        if not self.conv_id:
            self.new_chat()
        self.ctx.conversations.update(self.conv_id, provider=self.provider.currentData(),
                                      model=self.model.currentText().strip())
        if self.attachment:
            pid = self.provider.currentData()
            if self._is_cloud(pid) and self.ctx.settings.settings.ai.confirm_cloud_document_upload:
                if not confirm(self, "Send document to cloud provider?",
                               f"The content of '{self.attachment.name}' will be sent to {self.provider.currentText()}"
                               f" (a third-party cloud service).\n\nUse a local model to keep it on this PC.\n\nContinue?"):
                    return
            text = wrap_untrusted(self.attachment) + ("\n\n" + text if text else "")
            self._clear_attachment()
        self.input.clear()
        self._start_stream(lambda tok, cancel: self.ctx.chat.send(self.conv_id, text, on_token=tok, cancel=cancel),
                           pending=text)

    def _start_stream(self, fn, pending: str | None = None):
        self.streaming = True
        self.pending_user = pending
        self.stream_buf = ""
        self.cancel = CancelToken()
        cancel = self.cancel
        self.send_btn.setIcon(icon("stop", "#FFFFFF"))
        self.send_btn.setToolTip("Stop generating")
        self.status.setText("Generating…")
        self._t0 = time.perf_counter()
        self._render()
        run_async(lambda progress: fn(progress, cancel), on_progress=self._on_token, on_done=self._on_done,
                  on_error=self._on_error)

    def _on_token(self, tok):
        self.stream_buf += tok
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _finish(self):
        self.streaming = False
        self.pending_user = None
        self.stream_buf = ""
        self.send_btn.setIcon(icon("send", "#FFFFFF"))
        self.send_btn.setToolTip("Send")
        self.reload_conversations()
        conv = self.ctx.conversations.get(self.conv_id) if self.conv_id else None
        if conv:
            self.title.setText(conv.title)
        self._render()

    def _on_done(self, res):
        tok = "≈" if res.estimated else ""
        ftt = f" · first token {res.first_token_ms} ms" if res.first_token_ms is not None else ""
        cost = self.ctx.pricing.estimate(self.ctx.provider_repo.get(self.provider.currentData())["kind"],
                                         self.model.currentText(), res.input_tokens, res.output_tokens)
        cost_s = f" · est. ${cost:.4f}" if cost else ""
        self.status.setText(("Stopped. " if res.cancelled else "") +
                            f"{res.latency_ms / 1000:.1f}s{ftt} · {tok}{res.input_tokens} in / {tok}"
                            f"{res.output_tokens} out tokens{cost_s}")
        self._finish()

    def _on_error(self, e):
        self._finish()
        self.status.setText(f"Error: {e}")
        error(self, str(e), "Request failed")

    # ------------------------------------------------------------------ rendering
    def _render(self):
        parts = [f"<style>{chat_css()}</style>"]
        msgs = self.ctx.conversations.messages(self.conv_id) if self.conv_id else []
        if not msgs and not self.streaming:
            parts.append(
                f'<div style="margin-top:120px;text-align:center;">'
                f'<div style="font-size:30px;font-weight:700;letter-spacing:6px;">FATE&nbsp;AI</div>'
                f'<div style="color:{C["muted"]};margin-top:8px;">Ask anything. Local models stay on your PC; '
                f'cloud models use your own API account.</div></div>')
        last_user = max((m["id"] for m in msgs if m["role"] == "user"), default=None)
        last_ai = max((m["id"] for m in msgs if m["role"] == "assistant"), default=None)
        for m in msgs:
            parts.append(self._bubble(m["role"], m["content"], m["id"], m.get("model"),
                                      is_last_user=m["id"] == last_user, is_last_ai=m["id"] == last_ai))
        if self.streaming:
            if self.pending_user and (not msgs or msgs[-1]["content"] != self.pending_user):
                parts.append(self._bubble("user", self.pending_user, None, None))
            parts.append(self._bubble("assistant", self.stream_buf + " ▍", None, self.model.currentText()))
        sb = self.view.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 40
        self.view.setHtml("".join(parts))
        if at_bottom or self.streaming:
            sb.setValue(sb.maximum())

    def _bubble(self, role, content, mid, model, is_last_user=False, is_last_ai=False) -> str:
        if role == "user":
            if "BEGIN UNTRUSTED FILE" in content:
                head, _, rest = content.partition("BEGIN UNTRUSTED FILE")
                name = head.split("'")[1] if "'" in head else "file"
                tail = rest.split("END UNTRUSTED FILE", 1)[-1].strip(" =\n")
                body = f'<span style="color:{C["accent_hi"]}">📎 {h(name)}</span><br>' + h(tail).replace("\n", "<br>")
            else:
                body = h(content).replace("\n", "<br>")
            actions = ""
            if mid and not self.streaming:
                actions = f'<a href="fate:copy:{mid}">Copy</a>'
                if is_last_user:
                    actions += f' &nbsp; <a href="fate:edit:{mid}">Edit</a>'
            return (f'<table width="100%" border="0" cellspacing="0" cellpadding="12" class="row"><tr>'
                    f'<td width="18%" style="border:none;"></td>'
                    f'<td style="background:{C["user_bubble"]};border:none;">'
                    f'<p class="who">YOU</p><p>{body}</p><p class="actions">{actions}</p>'
                    f'</td></tr></table>')
        actions = ""
        if mid and not self.streaming:
            actions = f'<a href="fate:copy:{mid}">Copy</a> &nbsp; <a href="fate:branch:{mid}">Branch from here</a>'
            if is_last_ai:
                actions += ' &nbsp; <a href="fate:regen:0">Regenerate</a>'
        label = h(model or "FATE AI")
        return (f'<table width="100%" border="0" cellspacing="0" cellpadding="12" class="row"><tr>'
                f'<td style="background:{C["ai_bubble"]};border:none;">'
                f'<p class="who who-ai">✦ {label}</p>{render(content)}'
                f'<p class="actions">{actions}</p></td><td width="6%" style="border:none;"></td></tr></table>')

    def _on_anchor(self, url: QUrl):
        s = url.toString()
        if not s.startswith("fate:"):
            if url.scheme() in ("http", "https"):
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(url)
            return
        _, action, arg = s.split(":", 2)
        msgs = {m["id"]: m for m in self.ctx.conversations.messages(self.conv_id)} if self.conv_id else {}
        if action == "copy" and int(arg) in msgs:
            QGuiApplication.clipboard().setText(msgs[int(arg)]["content"])
            self.status.setText("Copied to clipboard.")
        elif action == "regen" and not self.streaming:
            self._start_stream(lambda tok, cancel: self.ctx.chat.regenerate(self.conv_id, tok, cancel))
        elif action == "edit" and int(arg) in msgs and not self.streaming:
            old = msgs[int(arg)]["content"]
            text, ok = QInputDialog.getMultiLineText(self, "Edit message", "Edit and resend:", old)
            if ok and text.strip():
                mid = int(arg)
                self._start_stream(lambda tok, cancel: self.ctx.chat.edit_and_resend(self.conv_id, mid, text.strip(),
                                                                                       tok, cancel), pending=text.strip())
        elif action == "branch" and int(arg) in msgs:
            new = self.ctx.conversations.branch(self.conv_id, int(arg))
            self.reload_conversations(new.id)
            self.open_conversation(new.id)

    def use_prompt(self, text: str):
        self.input.setPlainText(text)
        self.input.setFocus()

    def on_show(self):
        cur = self.provider.currentData()
        ids = [self.provider.itemData(i) for i in range(self.provider.count())]
        if ids != [p["id"] for p in self.ctx.providers.configs() if p["enabled"]]:
            self._load_providers()
            if cur:
                i = self.provider.findData(cur)
                if i >= 0:
                    self.provider.setCurrentIndex(i)
