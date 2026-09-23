from collections import defaultdict


class ConversationMemory:
    """In-memory conversation history partitioned by authenticated owner."""

    def __init__(self):
        self._store: dict[tuple[str, str], list[dict]] = defaultdict(list)

    @staticmethod
    def _key(owner_id: str, session_id: str) -> tuple[str, str]:
        if not owner_id:
            raise ValueError("owner_id is required")
        if not session_id:
            raise ValueError("session_id is required")
        return owner_id, session_id

    def add_message(
        self,
        owner_id: str,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        self._store[self._key(owner_id, session_id)].append(
            {"role": role, "content": content}
        )

    def get_history(
        self,
        owner_id: str,
        session_id: str,
        max_history: int = 40,
    ) -> list[dict]:
        return self._store[self._key(owner_id, session_id)][-max_history:]

    def clear(self, owner_id: str, session_id: str) -> None:
        self._store.pop(self._key(owner_id, session_id), None)

    def list_sessions(self, owner_id: str) -> list[str]:
        return sorted(
            session_id
            for stored_owner, session_id in self._store
            if stored_owner == owner_id
        )
