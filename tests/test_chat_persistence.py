from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes
from src.memory.manager import ConversationMemory


def test_native_chat_and_stream_commit_complete_turns_before_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAW_API_KEY", "test-persistence")
    path = str(tmp_path / "api.sqlite3")
    memory = ConversationMemory(path)
    monkeypatch.setattr(routes, "memory", memory)
    histories = []

    class Agent:
        async def achat(self, message, history):
            histories.append(history)
            return "first answer"

        async def astream(self, message, history):
            histories.append(history)
            yield "second "
            yield "answer"

    monkeypatch.setattr(routes, "get_agent", lambda: Agent())
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app, headers={"Authorization": "Bearer test-persistence"})
    assert client.post("/chat", json={"message": "first", "session_id": "s"}).status_code == 200
    response = client.post("/chat/stream", json={"message": "second", "session_id": "s"})
    assert "[DONE]" in response.text
    assert histories == [[], [{"role": "user", "content": "first"},
                             {"role": "assistant", "content": "first answer"}]]
    memory.close()
    reopened = ConversationMemory(path)
    monkeypatch.setattr(routes, "memory", reopened)
    assert client.get("/sessions").json()["sessions"] == ["s"]
    owner = routes.require_api_principal("Bearer test-persistence").owner_id
    assert reopened.get_history(owner, "s")[-1] == {"role": "assistant", "content": "second answer"}
    assert client.delete("/sessions/s").status_code == 200
    assert client.get("/sessions").json()["sessions"] == []
    reopened.close()
