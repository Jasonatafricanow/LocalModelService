"""Tests for src/tools/registry.py"""
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
import sys
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest
from pydantic import BaseModel
from src.tools.registry import ToolRegistry, BaseTool


def test_register_and_get():
    """Register a tool and retrieve it by name."""
    registry = ToolRegistry()

    class DummyTool(BaseTool):
        name = "dummy"
        description = "A dummy tool"

        def run(self, **kwargs) -> str:
            return "ran"

    registry.register(DummyTool())
    tool = registry.get("dummy")
    assert tool is not None
    assert tool.name == "dummy"
    assert tool.run() == "ran"


def test_register_empty_name_raises():
    """Registering a tool with empty name should raise ValueError."""
    registry = ToolRegistry()

    class BadTool(BaseTool):
        name = ""
        description = "bad"

        def run(self, **kwargs) -> str:
            return ""

    with pytest.raises(ValueError, match="non-empty name"):
        registry.register(BadTool())


def test_get_nonexistent_returns_none():
    """Getting a tool that was never registered returns None."""
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_list_returns_all_tools():
    """list() returns metadata for all registered tools."""
    registry = ToolRegistry()

    class ToolA(BaseTool):
        name = "tool_a"
        description = "Tool A"
        def run(self, **kwargs) -> str: return "a"

    class ToolB(BaseTool):
        name = "tool_b"
        description = "Tool B"
        args_schema = None
        def run(self, **kwargs) -> str: return "b"

    registry.register(ToolA())
    registry.register(ToolB())
    result = registry.list()
    assert len(result) == 2
    names = {t["name"] for t in result}
    assert names == {"tool_a", "tool_b"}


def test_list_returns_args_schema():
    """list() returns args_schema when available."""
    registry = ToolRegistry()

    class ThingInput(BaseModel):
        name: str
        count: int

    class ThingTool(BaseTool):
        name = "thing"
        description = "Does a thing"
        args_schema = ThingInput

        def run(self, **kwargs) -> str:
            return str(kwargs)

    registry.register(ThingTool())
    result = registry.list()
    assert len(result) == 1
    schema = result[0]["args_schema"]
    assert schema is not None
    assert "name" in schema["properties"]
    assert "count" in schema["properties"]


def test_list_args_schema_none():
    """list() returns args_schema as None when tool has no schema."""
    registry = ToolRegistry()

    class SimpleTool(BaseTool):
        name = "simple"
        description = "No schema"
        args_schema = None

        def run(self, **kwargs) -> str:
            return "ok"

    registry.register(SimpleTool())
    result = registry.list()
    assert result[0]["args_schema"] is None


def test_multiple_registrations():
    """Registering multiple tools works."""
    registry = ToolRegistry()

    class T1(BaseTool):
        name = "t1"
        def run(self, **kwargs) -> str: return "1"

    class T2(BaseTool):
        name = "t2"
        def run(self, **kwargs) -> str: return "2"

    registry.register(T1())
    registry.register(T2())
    assert len(registry.list()) == 2


def test_to_langchain_tools():
    """to_langchain_tools() converts all registered tools."""
    registry = ToolRegistry()

    class MyTool(BaseTool):
        name = "my_tool"
        description = "My custom tool"
        def run(self, **kwargs) -> str: return "done"

    registry.register(MyTool())
    lc_tools = registry.to_langchain_tools()
    assert len(lc_tools) == 1
    assert lc_tools[0].name == "my_tool"
    assert lc_tools[0].description == "My custom tool"


def test_run_with_args():
    """Tool run() receives keyword arguments correctly."""
    registry = ToolRegistry()

    class GreetInput(BaseModel):
        name: str

    class GreetTool(BaseTool):
        name = "greet"
        description = "Greets someone"
        args_schema = GreetInput

        def run(self, **kwargs) -> str:
            return f"Hello, {kwargs['name']}!"

    registry.register(GreetTool())
    tool = registry.get("greet")
    assert tool is not None
    assert tool.run(name="World") == "Hello, World!"
