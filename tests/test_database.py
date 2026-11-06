from app.database import db


def test_conversation_and_messages_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "APP_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.initialize_database()

    conversation_id = db.create_conversation("Test chat")
    db.add_message(conversation_id, "user", "Hello")
    db.add_message(conversation_id, "assistant", "Hi there")

    messages = db.get_messages(conversation_id)
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert [item["content"] for item in messages] == ["Hello", "Hi there"]


def test_message_role_is_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "APP_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.initialize_database()
    conversation_id = db.create_conversation()

    try:
        db.add_message(conversation_id, "tool", "not allowed")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid message role should be rejected")
