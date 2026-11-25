"""Owner-scoped SQLite conversation history with bounded retention."""
import sqlite3
import threading
import time
from pathlib import Path


class ConversationMemory:
    def __init__(self, path: str = ":memory:", *, ttl_seconds: int = 2592000,
                 max_messages: int = 200, max_sessions: int = 100, clock=time.time):
        if min(ttl_seconds, max_messages, max_sessions) <= 0:
            raise ValueError("retention limits must be positive")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self._clock = clock
        self._ttl = ttl_seconds
        self._max_messages = max_messages
        self._max_sessions = max_sessions
        with self._db:
            self._db.execute("""CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, owner TEXT NOT NULL, session TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL, created REAL NOT NULL)""")
            self._db.execute("CREATE INDEX IF NOT EXISTS message_scope ON messages(owner, session, id)")

    @staticmethod
    def _key(owner_id: str, session_id: str) -> tuple[str, str]:
        if not owner_id:
            raise ValueError("owner_id is required")
        if not session_id:
            raise ValueError("session_id is required")
        return owner_id, session_id

    def _prune(self):
        self._db.execute("DELETE FROM messages WHERE created <= ?", (self._clock() - self._ttl,))

    def add_message(self, owner_id: str, session_id: str, role: str, content: str) -> None:
        self._append(owner_id, session_id, [(role, content)])

    def add_exchange(self, owner_id: str, session_id: str, user: str, assistant: str) -> None:
        """Commit a completed turn atomically; interrupted generations are not saved."""
        self._append(owner_id, session_id, [("user", user), ("assistant", assistant)])

    def _append(self, owner_id, session_id, messages):
        key = self._key(owner_id, session_id)
        with self._lock, self._db:
            self._prune()
            now = self._clock()
            self._db.executemany(
                "INSERT INTO messages(owner,session,role,content,created) VALUES(?,?,?,?,?)",
                [(*key, role, content, now) for role, content in messages])
            self._db.execute("""DELETE FROM messages WHERE owner=? AND session=? AND id NOT IN
                (SELECT id FROM messages WHERE owner=? AND session=? ORDER BY id DESC LIMIT ?)""",
                (*key, *key, self._max_messages))
            self._db.execute("""DELETE FROM messages WHERE owner=? AND session NOT IN
                (SELECT session FROM messages WHERE owner=? GROUP BY session
                 ORDER BY MAX(id) DESC LIMIT ?)""", (owner_id, owner_id, self._max_sessions))

    def get_history(
        self,
        owner_id: str,
        session_id: str,
        max_history: int = 40,
    ) -> list[dict]:
        key = self._key(owner_id, session_id)
        if max_history < 0:
            raise ValueError("max_history cannot be negative")
        with self._lock, self._db:
            self._prune()
            rows = self._db.execute("""SELECT role,content FROM messages WHERE owner=? AND session=?
                ORDER BY id DESC LIMIT ?""", (*key, min(max_history, self._max_messages))).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def clear(self, owner_id: str, session_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM messages WHERE owner=? AND session=?", self._key(owner_id, session_id))

    def list_sessions(self, owner_id: str) -> list[str]:
        if not owner_id:
            raise ValueError("owner_id is required")
        with self._lock, self._db:
            self._prune()
            return [row[0] for row in self._db.execute(
                "SELECT DISTINCT session FROM messages WHERE owner=? ORDER BY session", (owner_id,))]

    def close(self) -> None:
        with self._lock:
            self._db.close()
