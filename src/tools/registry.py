from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.tools import BaseTool as LangChainTool
from langchain_core.tools import StructuredTool
from pydantic import BaseModel


class BaseTool(ABC):
    """所有工具的基类。继承此类并实现 name / description / args_schema / run 即可自动注册。"""

    name: str = ""
    description: str = ""
    args_schema: type[BaseModel] | None = None

    @abstractmethod
    def run(self, **kwargs) -> str: ...

    def _to_langchain(self) -> LangChainTool:
        """Convert to a LangChain StructuredTool, preserving args_schema."""
        return StructuredTool.from_function(
            func=self.run,
            name=self.name,
            description=self.description,
            args_schema=self.args_schema,
        )


class ToolRegistry:
    """全局工具注册表。工具注册后自动转为 LangChain 工具供 Agent 调用。"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError("Tool must have a non-empty name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "args_schema": (
                    t.args_schema.model_json_schema() if t.args_schema else None
                ),
            }
            for t in self._tools.values()
        ]

    def to_langchain_tools(self) -> list[LangChainTool]:
        return [t._to_langchain() for t in self._tools.values()]

    # Temporary compatibility for existing callers. Keep this last so it can
    # never shadow the builtin list in later annotations.
    def list(self) -> list[dict[str, Any]]:
        return self.list_tools()


registry = ToolRegistry()
