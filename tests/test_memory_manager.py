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
