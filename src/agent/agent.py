from typing import Any

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import BaseTool as LangChainTool
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk

from src.core.config import get_agent_config
from src.core.llm import get_llm
from src.tools.registry import registry


class Agent:
    def __init__(self, cfg: dict | None = None):
        agent_cfg = get_agent_config(cfg)
        self.system_prompt = agent_cfg.get(
            "system_prompt", "你是一个智能助手。"
        )
        self.max_history = agent_cfg.get("max_history", 40)
        self.enable_tools = agent_cfg.get("enable_tools", True)

        self.llm = get_llm(cfg)
        self._agent = None

    def _build_agent(self):
        tools: list[LangChainTool] = []
        if self.enable_tools:
            tools = registry.to_langchain_tools()

        return create_react_agent(
            model=self.llm,
            tools=tools or None,
            prompt=self.system_prompt,
        )

    @property
    def graph(self):
        if self._agent is None:
            self._agent = self._build_agent()
        return self._agent

    def _build_messages(self, message: str, history: list[dict] | None):
        msgs = []
        if history:
            for msg in history[-self.max_history :]:
                if msg["role"] == "user":
                    msgs.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    msgs.append(AIMessage(content=msg["content"]))
        msgs.append(HumanMessage(content=message))
        return msgs

    def chat(self, message: str, history: list[dict] | None = None) -> str:
        msgs = self._build_messages(message, history)
        result = self.graph.invoke({"messages": msgs})
        return self._extract_output(result)

    async def achat(self, message: str, history: list[dict] | None = None) -> str:
        msgs = self._build_messages(message, history)
        result = await self.graph.ainvoke({"messages": msgs})
        return self._extract_output(result)

    async def astream(self, message: str, history: list[dict] | None = None):
        msgs = self._build_messages(message, history)
        async for chunk, _ in self.graph.astream({"messages": msgs}, stream_mode="messages"):
            if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str) and chunk.content:
                yield chunk.content

    @staticmethod
    def _extract_output(result: dict[str, Any]) -> str:
        messages = result.get("messages", [])
        # Walk backwards to find the last AI message — in multi-turn tool
        # loops the final message may be a ToolMessage, not the answer.
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
                return msg.content
        return str(result)


# 全局单例
_agent: Agent | None = None


def get_agent(cfg: dict | None = None) -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(cfg)
    return _agent
