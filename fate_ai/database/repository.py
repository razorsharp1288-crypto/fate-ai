"""Repositories: the only code that talks SQL. Return plain dicts/dataclasses."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .db import Database


def _row(r) -> dict[str, Any] | None:
    return dict(r) if r is not None else None


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


class ConversationRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, title: str, provider: str, model: str, system_prompt: str = "",
               temperature: float = 0.7, max_tokens: int = 2048,
               parent_id: int | None = None) -> Conversation:
        cur = self.db.execute(
            "INSERT INTO conversations(title, provider, model, system_prompt, temperature, max_tokens, parent_id)"
            " VALUES (?,?,?,?,?,?,?)",
            (title, provider, model, system_prompt, temperature, max_tokens, parent_id))
        return self.get(cur.lastrowid)

    def get(self, cid: int) -> Conversation | None:
        r = self.db.one("SELECT * FROM conversations WHERE id=?", (cid,))
        return Conversation(**dict(r)) if r else None

    def list(self, search: str = "") -> list[Conversation]:
        if search:
            like = f"%{search}%"
            rows = self.db.query(
                "SELECT DISTINCT c.* FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id "
                "WHERE c.title LIKE ? OR m.content LIKE ? ORDER BY c.updated_at DESC, c.id DESC",
                (like, like))
        else:
            rows = self.db.query("SELECT * FROM conversations ORDER BY updated_at DESC, id DESC")
        return [Conversation(**dict(r)) for r in rows]

    _UPDATABLE = {"title", "provider", "model", "system_prompt", "temperature", "max_tokens"}

    def update(self, cid: int, **fields) -> Conversation:
        fields = {k: v for k, v in fields.items() if k in self._UPDATABLE}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            self.db.execute(f"UPDATE conversations SET {sets}, updated_at=datetime('now') WHERE id=?",
                            (*fields.values(), cid))
        return self.get(cid)

    def touch(self, cid: int) -> None:
        self.db.execute("UPDATE conversations SET updated_at=datetime('now') WHERE id=?", (cid,))

    def delete(self, cid: int) -> None:
        self.db.execute("DELETE FROM conversations WHERE id=?", (cid,))

    # messages -------------------------------------------------------------
    def add_message(self, cid: int, role: str, content: str, **meta) -> int:
        cur = self.db.execute(
            "INSERT INTO messages(conversation_id, role, content, provider, model, input_tokens, output_tokens, latency_ms)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (cid, role, content, meta.get("provider"), meta.get("model"), meta.get("input_tokens"),
             meta.get("output_tokens"), meta.get("latency_ms")))
        self.touch(cid)
        return cur.lastrowid

    def messages(self, cid: int) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,))]

    def update_message(self, mid: int, content: str) -> None:
        self.db.execute("UPDATE messages SET content=? WHERE id=?", (content, mid))

    def delete_messages_from(self, cid: int, mid: int) -> None:
        """Delete message ``mid`` and everything after it (used by edit/regenerate)."""
        self.db.execute("DELETE FROM messages WHERE conversation_id=? AND id>=?", (cid, mid))

    def branch(self, cid: int, upto_mid: int) -> Conversation:
        src = self.get(cid)
        new = self.create(f"{src.title} (branch)", src.provider, src.model, src.system_prompt,
                          src.temperature, src.max_tokens, parent_id=cid)
        for m in self.messages(cid):
            if m["id"] > upto_mid:
                break
            self.add_message(new.id, m["role"], m["content"], provider=m["provider"], model=m["model"])
        return new

    def export(self, cid: int) -> dict:
        c = self.get(cid)
        return {
            "format": "fate-ai-conversation", "version": 1,
            "conversation": {k: getattr(c, k) for k in
                             ("title", "provider", "model", "system_prompt", "temperature", "max_tokens",
                              "created_at")},
            "messages": [{k: m[k] for k in ("role", "content", "provider", "model", "created_at")}
                         for m in self.messages(cid)],
        }

    def import_(self, data: dict) -> Conversation:
        if data.get("format") != "fate-ai-conversation":
            raise ValueError("Not a FATE AI conversation export")
        c = data["conversation"]
        conv = self.create(str(c.get("title", "Imported chat"))[:200], str(c.get("provider", "")),
                           str(c.get("model", "")), str(c.get("system_prompt", "")),
                           float(c.get("temperature", 0.7)), int(c.get("max_tokens", 2048)))
        for m in data.get("messages", []):
            if m.get("role") in ("system", "user", "assistant"):
                self.add_message(conv.id, m["role"], str(m.get("content", "")),
                                 provider=m.get("provider"), model=m.get("model"))
        return conv


class ProviderRepository:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, pid: str, kind: str, name: str, base_url: str = "", default_model: str = "",
               enabled: bool = True, options: dict | None = None) -> dict:
        self.db.execute(
            "INSERT INTO providers(id, kind, name, base_url, default_model, enabled, options_json) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, name=excluded.name, base_url=excluded.base_url,"
            " default_model=excluded.default_model, enabled=excluded.enabled, options_json=excluded.options_json",
            (pid, kind, name, base_url, default_model, int(enabled), json.dumps(options or {})))
        return self.get(pid)

    def get(self, pid: str) -> dict | None:
        r = _row(self.db.one("SELECT * FROM providers WHERE id=?", (pid,)))
        if r:
            r["options"] = json.loads(r.pop("options_json"))
            r["enabled"] = bool(r["enabled"])
        return r

    def list(self) -> list[dict]:
        return [self.get(r["id"]) for r in self.db.query("SELECT id FROM providers ORDER BY name")]

    def delete(self, pid: str) -> None:
        self.db.execute("DELETE FROM providers WHERE id=?", (pid,))


class UsageRepository:
    def __init__(self, db: Database):
        self.db = db

    def record(self, provider: str, model: str, input_tokens: int, output_tokens: int, *,
               estimated: bool, latency_ms: int | None, success: bool, is_local: bool,
               error: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO usage_events(provider, model, input_tokens, output_tokens, estimated, latency_ms,"
            " success, error, is_local) VALUES (?,?,?,?,?,?,?,?,?)",
            (provider, model, input_tokens, output_tokens, int(estimated), latency_ms, int(success),
             error, int(is_local)))

    def summary(self) -> dict:
        r = self.db.one(
            "SELECT COUNT(*) AS requests, SUM(success=0) AS failed, COALESCE(SUM(input_tokens),0) AS input_tokens,"
            " COALESCE(SUM(output_tokens),0) AS output_tokens, AVG(latency_ms) AS avg_latency,"
            " SUM(is_local) AS local_requests FROM usage_events")
        out = dict(r)
        out["conversations"] = self.db.one("SELECT COUNT(*) FROM conversations")[0]
        return out

    def by_model(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT provider, model, COUNT(*) AS requests, SUM(input_tokens) AS input_tokens,"
            " SUM(output_tokens) AS output_tokens, AVG(latency_ms) AS avg_latency, SUM(success=0) AS failed,"
            " MAX(is_local) AS is_local, MIN(estimated) AS exact FROM usage_events GROUP BY provider, model"
            " ORDER BY requests DESC")]

    def daily(self, days: int = 30) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT date(created_at) AS day, COUNT(*) AS requests, SUM(input_tokens+output_tokens) AS tokens"
            " FROM usage_events WHERE created_at >= datetime('now', ?) GROUP BY day ORDER BY day",
            (f"-{int(days)} days",))]


class PromptRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, title: str, body: str, category: str = "General", tags: str = "",
               favorite: bool = False) -> int:
        return self.db.execute(
            "INSERT INTO prompts(title, body, category, tags, favorite) VALUES (?,?,?,?,?)",
            (title, body, category, tags, int(favorite))).lastrowid

    def update(self, pid: int, **f) -> None:
        allowed = {k: v for k, v in f.items() if k in {"title", "body", "category", "tags", "favorite"}}
        if allowed:
            sets = ", ".join(f"{k}=?" for k in allowed)
            self.db.execute(f"UPDATE prompts SET {sets}, updated_at=datetime('now') WHERE id=?",
                            (*allowed.values(), pid))

    def mark_used(self, pid: int) -> None:
        self.db.execute("UPDATE prompts SET use_count=use_count+1 WHERE id=?", (pid,))

    def delete(self, pid: int) -> None:
        self.db.execute("DELETE FROM prompts WHERE id=?", (pid,))

    def get(self, pid: int) -> dict | None:
        return _row(self.db.one("SELECT * FROM prompts WHERE id=?", (pid,)))

    def list(self, search: str = "", category: str = "", favorites_only: bool = False) -> list[dict]:
        sql, params = "SELECT * FROM prompts WHERE 1=1", []
        if search:
            sql += " AND (title LIKE ? OR body LIKE ? OR tags LIKE ?)"
            params += [f"%{search}%"] * 3
        if category:
            sql += " AND category=?"
            params.append(category)
        if favorites_only:
            sql += " AND favorite=1"
        sql += " ORDER BY favorite DESC, use_count DESC, title"
        return [dict(r) for r in self.db.query(sql, tuple(params))]

    def categories(self) -> list[str]:
        return [r[0] for r in self.db.query("SELECT DISTINCT category FROM prompts ORDER BY category")]

    def count(self) -> int:
        return self.db.one("SELECT COUNT(*) FROM prompts")[0]


class SimpleRepository:
    """Generic CRUD for small tables with a JSON column convention (*_json)."""

    def __init__(self, db: Database, table: str, columns: set[str]):
        self.db, self.table, self.columns = db, table, columns

    def _encode(self, f: dict) -> dict:
        out = {}
        for k, v in f.items():
            if k + "_json" in self.columns:
                out[k + "_json"] = json.dumps(v)
            elif k in self.columns:
                out[k] = v
        return out

    def _decode(self, r) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        for k in list(d):
            if k.endswith("_json"):
                d[k[:-5]] = json.loads(d.pop(k))
        return d

    def create(self, **f) -> int:
        enc = self._encode(f)
        cols = ", ".join(enc)
        qs = ", ".join("?" * len(enc))
        return self.db.execute(f"INSERT INTO {self.table}({cols}) VALUES ({qs})", tuple(enc.values())).lastrowid

    def update(self, rid: int, **f) -> None:
        enc = self._encode(f)
        if enc:
            sets = ", ".join(f"{k}=?" for k in enc)
            self.db.execute(f"UPDATE {self.table} SET {sets} WHERE id=?", (*enc.values(), rid))

    def get(self, rid: int) -> dict | None:
        return self._decode(self.db.one(f"SELECT * FROM {self.table} WHERE id=?", (rid,)))

    def list(self) -> list[dict]:
        return [self._decode(r) for r in self.db.query(f"SELECT * FROM {self.table} ORDER BY id")]

    def delete(self, rid: int) -> None:
        self.db.execute(f"DELETE FROM {self.table} WHERE id=?", (rid,))


def agents_repo(db: Database) -> SimpleRepository:
    return SimpleRepository(db, "agents", {"name", "role", "instructions", "provider", "model",
                                           "permissions_json", "allowed_paths_json"})


def projects_repo(db: Database) -> SimpleRepository:
    return SimpleRepository(db, "projects", {"name", "path", "instructions", "agent_id"})


def sandboxes_repo(db: Database) -> SimpleRepository:
    return SimpleRepository(db, "sandboxes", {"name", "level", "workdir", "config_json"})


class SandboxRunRepository:
    def __init__(self, db: Database):
        self.db = db

    def record(self, sandbox_id: int, command: str, exit_code: int | None, duration_ms: int,
               stdout: str, stderr: str, timed_out: bool) -> int:
        return self.db.execute(
            "INSERT INTO sandbox_runs(sandbox_id, command, exit_code, duration_ms, stdout, stderr, timed_out)"
            " VALUES (?,?,?,?,?,?,?)",
            (sandbox_id, command, exit_code, duration_ms, stdout, stderr, int(timed_out))).lastrowid

    def list(self, sandbox_id: int) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM sandbox_runs WHERE sandbox_id=? ORDER BY id DESC", (sandbox_id,))]


class BenchmarkRepository:
    def __init__(self, db: Database):
        self.db = db

    def record(self, **f) -> None:
        self.db.execute(
            "INSERT INTO benchmarks(prompt, provider, model, latency_ms, first_token_ms, output_chars,"
            " tokens_per_sec, success, error) VALUES (?,?,?,?,?,?,?,?,?)",
            (f["prompt"], f["provider"], f["model"], f.get("latency_ms"), f.get("first_token_ms"),
             f.get("output_chars"), f.get("tokens_per_sec"), int(f["success"]), f.get("error")))

    def list(self, limit: int = 200) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM benchmarks ORDER BY id DESC LIMIT ?", (limit,))]
