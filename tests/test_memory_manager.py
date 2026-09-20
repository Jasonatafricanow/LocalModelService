"""Tests for src/memory/manager.py - ConversationMemory"""
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
import sys
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest
from src.memory.manager import ConversationMemory


def test_conversation_memory_init():
    """ConversationMemory initializes clean."""
    cm = ConversationMemory()
    assert cm.list_sessions() == []


def test_add_and_get_message():
    """Adding a message and retrieving it works."""
    cm = ConversationMemory()
    cm.add_message("sess_1", "user", "Hello")
    history = cm.get_history("sess_1")
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"


def test_get_nonexistent_session():
    """Getting history for a nonexistent session returns empty list."""
    cm = ConversationMemory()
    history = cm.get_history("nobody")
    assert history == []


def test_history_truncation():
    """get_history truncates to max_history."""
    cm = ConversationMemory()
    for i in range(10):
        cm.add_message("sess_a", "user", f"msg_{i}")
    history = cm.get_history("sess_a", max_history=3)
    assert len(history) == 3
    assert history[-1]["content"] == "msg_9"
    assert history[0]["content"] == "msg_7"


def test_multiple_sessions():
    """Different sessions maintain separate history."""
    cm = ConversationMemory()
    cm.add_message("a", "user", "a1")
    cm.add_message("b", "user", "b1")
    cm.add_message("a", "assistant", "a2")
    assert len(cm.get_history("a")) == 2
    assert len(cm.get_history("b")) == 1


def test_clear_session():
    """Clearing a session removes its history."""
    cm = ConversationMemory()
    cm.add_message("x", "user", "keep")
    cm.clear("x")
    assert cm.get_history("x") == []


def test_clear_nonexistent():
    """Clearing a nonexistent session does not raise."""
    cm = ConversationMemory()
    cm.clear("nobody")
    assert True


def test_list_sessions():
    """list_sessions returns all session IDs with messages."""
    cm = ConversationMemory()
    cm.add_message("s1", "user", "hi")
    cm.add_message("s2", "user", "hey")
    sessions = cm.list_sessions()
    assert set(sessions) == {"s1", "s2"}


def test_list_sessions_after_clear():
    """After clearing, the session no longer appears in list_sessions."""
    cm = ConversationMemory()
    cm.add_message("s1", "user", "hi")
    cm.clear("s1")
    assert "s1" not in cm.list_sessions()
