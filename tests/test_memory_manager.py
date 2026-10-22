"""Tests for owner-scoped ConversationMemory."""

from src.memory.manager import ConversationMemory


OWNER_A = "owner-a"
OWNER_B = "owner-b"


def test_conversation_memory_init():
    cm = ConversationMemory()
    assert cm.list_sessions(OWNER_A) == []


def test_add_and_get_message():
    cm = ConversationMemory()
    cm.add_message(OWNER_A, "sess_1", "user", "Hello")
    history = cm.get_history(OWNER_A, "sess_1")
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"


def test_get_nonexistent_session():
    cm = ConversationMemory()
    assert cm.get_history(OWNER_A, "nobody") == []
    assert cm.list_sessions(OWNER_A) == []


def test_history_truncation():
    cm = ConversationMemory()
    for i in range(10):
        cm.add_message(OWNER_A, "sess_a", "user", f"msg_{i}")
    history = cm.get_history(OWNER_A, "sess_a", max_history=3)
    assert len(history) == 3
    assert history[-1]["content"] == "msg_9"
    assert history[0]["content"] == "msg_7"


def test_multiple_sessions():
    cm = ConversationMemory()
    cm.add_message(OWNER_A, "a", "user", "a1")
    cm.add_message(OWNER_A, "b", "user", "b1")
    cm.add_message(OWNER_A, "a", "assistant", "a2")
    assert len(cm.get_history(OWNER_A, "a")) == 2
    assert len(cm.get_history(OWNER_A, "b")) == 1


def test_owner_isolation_for_same_session_id():
    cm = ConversationMemory()
    cm.add_message(OWNER_A, "shared", "user", "secret-a")
    cm.add_message(OWNER_B, "shared", "user", "secret-b")

    assert cm.get_history(OWNER_A, "shared") == [
        {"role": "user", "content": "secret-a"}
    ]
    assert cm.get_history(OWNER_B, "shared") == [
        {"role": "user", "content": "secret-b"}
    ]


def test_clear_session_is_owner_scoped():
    cm = ConversationMemory()
    cm.add_message(OWNER_A, "shared", "user", "a")
    cm.add_message(OWNER_B, "shared", "user", "b")

    cm.clear(OWNER_A, "shared")

    assert cm.get_history(OWNER_A, "shared") == []
    assert cm.get_history(OWNER_B, "shared") == [
        {"role": "user", "content": "b"}
    ]


def test_list_sessions_is_owner_scoped():
    cm = ConversationMemory()
    cm.add_message(OWNER_A, "s1", "user", "hi")
    cm.add_message(OWNER_A, "s2", "user", "hey")
    cm.add_message(OWNER_B, "other", "user", "hidden")

    assert set(cm.list_sessions(OWNER_A)) == {"s1", "s2"}
    assert cm.list_sessions(OWNER_B) == ["other"]


def test_restart_retains_owner_scoped_turns_and_deletions(tmp_path):
    path = str(tmp_path / "history.sqlite3")
    first = ConversationMemory(path)
    first.add_exchange(OWNER_A, "same", "question", "answer")
    first.add_message(OWNER_B, "same", "user", "private")
    first.close()
    second = ConversationMemory(path)
    assert second.get_history(OWNER_A, "same") == [
        {"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"}]
    second.clear(OWNER_A, "same")
    second.close()
    third = ConversationMemory(path)
    assert third.get_history(OWNER_A, "same") == []
    assert third.get_history(OWNER_B, "same")[0]["content"] == "private"
    third.close()


def test_retention_bounds_messages_sessions_and_expires_at_ttl():
    now = [100.0]
    cm = ConversationMemory(ttl_seconds=10, max_messages=2, max_sessions=1, clock=lambda: now[0])
    cm.add_message(OWNER_A, "old", "user", "old")
    for content in ["1", "2", "3"]:
        cm.add_message(OWNER_A, "new", "user", content)
    assert cm.list_sessions(OWNER_A) == ["new"]
    assert [m["content"] for m in cm.get_history(OWNER_A, "new")] == ["2", "3"]
    assert cm.get_history(OWNER_A, "new", max_history=0) == []
    now[0] = 110.0
    assert cm.list_sessions(OWNER_A) == []
    assert cm.get_history(OWNER_A, "new") == []
