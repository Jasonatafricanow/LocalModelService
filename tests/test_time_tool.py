"""Tests for src/tools/builtin/time_tool.py"""
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
import sys
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from datetime import datetime

from src.tools.builtin.time_tool import TimeTool, TimeInput


def test_time_tool_name_and_description():
    """TimeTool has a name and a non-empty description."""
    tool = TimeTool()
    assert tool.name == "get_current_time"
    assert tool.description and "时间" in tool.description


def test_time_tool_returns_iso_format():
    """TimeTool.run returns a timestamp parseable by datetime.fromisoformat."""
    tool = TimeTool()
    result = tool.run()
    parsed = datetime.fromisoformat(result)
    assert isinstance(parsed, datetime)


def test_time_tool_returns_naive_local_time():
    """TimeTool.run returns a naive local timestamp in the default format."""
    tool = TimeTool()
    result = tool.run()
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is None


def test_time_tool_custom_format():
    """TimeTool.run honours a custom strftime format."""
    tool = TimeTool()
    assert tool.run(format="%Y") == datetime.now().strftime("%Y")


def test_time_tool_args_schema():
    """TimeTool exposes its TimeInput args schema."""
    tool = TimeTool()
    assert tool.args_schema is TimeInput
