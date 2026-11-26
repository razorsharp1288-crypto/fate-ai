from fate_ai.database.db import MIGRATIONS, Database
from fate_ai.database.repository import ConversationRepository, PromptRepository, UsageRepository


def test_migrations_apply_and_are_idempotent(tmp_path):
    db = Database(tmp_path / "x.db")
    assert db.schema_version == len(MIGRATIONS)
    db.close()
    db2 = Database(tmp_path / "x.db")
    assert db2.schema_version == len(MIGRATIONS)


def test_conversation_roundtrip_and_persistence(tmp_path):
    path = tmp_path / "c.db"
    repo = ConversationRepository(Database(path))
    c = repo.create("Hello", "ollama", "llama3.2:3b", "sys", 0.5, 100)
    repo.add_message(c.id, "user", "hi")
    repo.add_message(c.id, "assistant", "hello there")
    repo.db.close()
    repo2 = ConversationRepository(Database(path))
    msgs = repo2.messages(c.id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert repo2.get(c.id).model == "llama3.2:3b"


def test_search_matches_title_and_content(tmp_path):
    repo = ConversationRepository(Database(tmp_path / "s.db"))
    a = repo.create("Rust question", "p", "m")
    b = repo.create("Other", "p", "m")
    repo.add_message(b.id, "user", "tell me about quaternions")
    assert [c.id for c in repo.list("rust")] == [a.id]
    assert [c.id for c in repo.list("quaternion")] == [b.id]


def test_sql_injection_is_inert(tmp_path):
    repo = ConversationRepository(Database(tmp_path / "i.db"))
    evil = "x'); DROP TABLE conversations; --"
    c = repo.create(evil, "p", "m")
    assert repo.list(evil)[0].id == c.id
    assert repo.get(c.id).title == evil


def test_update_ignores_unknown_columns(tmp_path):
    repo = ConversationRepository(Database(tmp_path / "u.db"))
    c = repo.create("t", "p", "m")
    repo.update(c.id, title="new", id=999, **{"title; DROP": 1})
    assert repo.get(c.id).title == "new"


def test_export_import_and_branch(tmp_path):
    repo = ConversationRepository(Database(tmp_path / "e.db"))
    c = repo.create("T", "openai", "gpt-4o-mini", "be nice")
    m1 = repo.add_message(c.id, "user", "q1")
    repo.add_message(c.id, "assistant", "a1")
    repo.add_message(c.id, "user", "q2")
    data = repo.export(c.id)
    imported = repo.import_(data)
    assert len(repo.messages(imported.id)) == 3
    br = repo.branch(c.id, m1)
    assert [m["content"] for m in repo.messages(br.id)] == ["q1"]
    assert br.parent_id == c.id


def test_delete_cascades(tmp_path):
    db = Database(tmp_path / "d.db")
    repo = ConversationRepository(db)
    c = repo.create("T", "p", "m")
    repo.add_message(c.id, "user", "x")
    repo.delete(c.id)
    assert db.one("SELECT COUNT(*) FROM messages")[0] == 0


def test_usage_and_prompts(tmp_path):
    db = Database(tmp_path / "p.db")
    u = UsageRepository(db)
    u.record("openai", "gpt-4o", 10, 20, estimated=False, latency_ms=100, success=True, is_local=False)
    u.record("ollama", "llama", 5, 5, estimated=True, latency_ms=50, success=False, is_local=True, error="x")
    s = u.summary()
    assert s["requests"] == 2 and s["failed"] == 1 and s["local_requests"] == 1
    assert len(u.by_model()) == 2
    p = PromptRepository(db)
    pid = p.create("A", "body {{x}}", "Coding", "t1", favorite=True)
    p.create("B", "zzz", "Writing")
    assert p.list(search="body")[0]["id"] == pid
    assert len(p.list(favorites_only=True)) == 1
    assert p.categories() == ["Coding", "Writing"]
