"""Tests for src/agent/agent.py"""
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
import sys
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest
from unittest.mock import patch, MagicMock, PropertyMock


@pytest.fixture(autouse=True)
def mock_deps():
    """Mock all heavy external dependencies."""
    with patch("src.agent.agent.get_llm") as mock_llm,          patch("src.agent.agent.get_agent_config") as mock_cfg,          patch("src.agent.agent.registry") as mock_registry:
        mock_llm.return_value = MagicMock()
        mock_cfg.return_value = {
            "system_prompt": "You are a helpful assistant.",
            "max_history": 40,
            "enable_tools": True,
        }
        mock_registry.to_langchain_tools.return_value = []
        yield


def test_agent_init_defaults():
    """Agent initializes with defaults from config."""
    from src.agent.agent import Agent
    agent = Agent()
    assert agent.system_prompt == "You are a helpful assistant."
    assert agent.max_history == 40
    assert agent.enable_tools is True


def test_agent_init_custom_config():
    """Agent accepts a custom config dict."""
    from src.agent.agent import Agent
    with patch("src.agent.agent.get_agent_config") as mock_cfg:
        mock_cfg.return_value = {
            "system_prompt": "Custom prompt.",
            "max_history": 10,
            "enable_tools": False,
        }
        agent = Agent({"custom": True})
        assert agent.system_prompt == "Custom prompt."
        assert agent.max_history == 10
        assert agent.enable_tools is False


def test_agent_build_messages_empty_history():
    """_build_messages works without history."""
    from src.agent.agent import Agent
    agent = Agent()
    msgs = agent._build_messages("Hello", None)
    assert len(msgs) == 1
    assert msgs[0].content == "Hello"


def test_agent_build_messages_with_history():
    """_build_messages handles history correctly."""
    from src.agent.agent import Agent
    agent = Agent()
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]
    msgs = agent._build_messages("How are you?", history)
    assert len(msgs) == 3
    assert msgs[-1].content == "How are you?"
    assert msgs[0].content == "Hi"


def test_agent_build_messages_truncates_history():
    """_build_messages truncates history to max_history."""
    from src.agent.agent import Agent
    with patch("src.agent.agent.get_agent_config") as mock_cfg:
        mock_cfg.return_value = {
            "system_prompt": "X",
            "max_history": 2,
            "enable_tools": True,
        }
        agent = Agent()
        history = [
            {"role": "user", "content": f"msg_{i}"}
            for i in range(10)
        ]
        msgs = agent._build_messages("final", history)
        assert len(msgs) == 3  # 2 from history + 1 new
        assert msgs[1].content == "msg_9"  # last of truncated history
        assert msgs[-1].content == "final"


def test_agent_chat_extracts_output():
    """chat() extracts text from invoke result."""
    from src.agent.agent import Agent
    agent = Agent()
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [MagicMock(content="Response text")]
    }
    agent._agent = mock_graph
    result = agent.chat("Hello")
    assert result == "Response text"
