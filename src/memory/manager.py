from collections import defaultdict


class ConversationMemory:
    """内存级对话记忆管理（单机轻量方案，重启后丢失）。"""

    def __init__(self):
        self._store: dict[str, list[dict]] = defaultdict(list)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self._store[session_id].append({"role": role, "content": content})

    def get_history(self, session_id: str, max_history: int = 40) -> list[dict]:
        return self._store[session_id][-max_history:]

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        return list(self._store.keys())

