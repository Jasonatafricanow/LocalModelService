"""Tests for src/api — FastAPI endpoint integration tests.

Run with::

    python -m pytest tests/test_api.py -v

Note: Tests that require Ollama (e.g. /chat) are skipped automatically.
"""
from pathlib import Path
import os

os.environ.setdefault("OPENCLAW_API_KEY", "test-api-key")
os.environ.setdefault("OPENCLAW_TOOLS_API_KEY", "test-tools-key")

API_HEADERS = {"Authorization": "Bearer test-api-key"}
TOOLS_HEADERS = {"Authorization": "Bearer test-tools-key"}

_root = Path(__file__).resolve().parent.parent
import sys
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest
import requests
from fastapi.testclient import TestClient

# Automatically detect whether Ollama is available.
# Tests that need Ollama will run on deployed servers and skip on dev machines.
_ollama_available = False
try:
    r = requests.get("http://localhost:11434/api/tags", timeout=2)
    _ollama_available = r.status_code == 200
except Exception:
    pass

ollama_required = pytest.mark.skipif(
    not _ollama_available,
    reason="Ollama not running on localhost:11434",
)

# Import the app — this triggers module loading including WhatsApp
from src.server import app

client = TestClient(app)


# ===================================================================
# Basic endpoints (no Ollama required)
# ===================================================================


class TestRoot:
    def test_root_returns_status(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "version" in data
        assert data["name"] == "OpenClaw"
        assert data["status"] == "running"


class TestTools:
    def test_list_tools_returns_list(self):
        resp = client.get("/tools", headers=TOOLS_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert "count" in data
        assert isinstance(data["tools"], list)
        # At least the built-in TimeTool should be registered
        assert data["count"] >= 1
        tool_names = [t["name"] for t in data["tools"]]
        assert "get_current_time" in tool_names

    def test_tool_has_args_schema(self):
        resp = client.get("/tools", headers=TOOLS_HEADERS)
        data = resp.json()
        for tool in data["tools"]:
            assert "name" in tool
            assert "description" in tool
            # args_schema may be None or a string
            assert "args_schema" in tool


class TestSessions:
    def test_list_sessions_empty_initially(self):
        resp = client.get("/sessions", headers=API_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert "count" in data
        assert isinstance(data["sessions"], list)

    def test_delete_nonexistent_session(self):
        resp = client.delete("/sessions/nonexistent_123", headers=API_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestHealth:
    def test_health_returns_degraded_without_ollama(self):
        """Without Ollama running, /health should return degraded, not 500."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        if data["status"] == "degraded":
            assert "ollama" in data
            assert data["ollama"] == "disconnected"


# ===================================================================
# Schema validation
# ===================================================================


class TestChatSchema:
    def test_chat_missing_message_returns_422(self):
        resp = client.post("/chat", headers=API_HEADERS, json={"session_id": "test"})
        assert resp.status_code == 422  # Unprocessable Entity

    @ollama_required
    def test_chat_empty_message(self):
        resp = client.post("/chat", headers=API_HEADERS, json={"message": "", "session_id": "test"})
        assert resp.status_code in (200, 422)

    @ollama_required
    def test_chat_stream_schema(self):
        resp = client.post("/chat/stream", headers=API_HEADERS, json={"message": "hi"})
        assert resp.status_code in (200, 422, 502, 503)


class TestChatCompletionsSchema:
    def test_completions_missing_messages_returns_422(self):
        resp = client.post("/v1/chat/completions", headers=API_HEADERS, json={"model": "test"})
        assert resp.status_code == 422

    @ollama_required
    def test_completions_valid_request(self):
        resp = client.post("/v1/chat/completions", headers=API_HEADERS, json={
            "model": "test",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert resp.status_code in (200, 500, 502)
        if resp.status_code == 500:
            data = resp.json()
            assert "detail" in data


class TestToolInvokeSchema:
    def test_invoke_nonexistent_tool_404(self):
        resp = client.post("/tools/nonexistent/invoke", headers=TOOLS_HEADERS, json={"arguments": {}})
        assert resp.status_code == 404

    def test_invoke_invalid_args(self):
        resp = client.post("/tools/get_current_time/invoke", headers=TOOLS_HEADERS, json={"arguments": {"format": "%Y"}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "result" in data

class TestAuthentication:
    def test_private_api_rejects_missing_bearer(self):
        assert client.get("/models").status_code == 401
        assert client.get("/sessions", headers=API_HEADERS).status_code == 401
        assert client.post("/chat", json={"message": "hello"}).status_code == 401

    def test_private_api_rejects_wrong_bearer(self):
        response = client.get(
            "/sessions",
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert response.status_code == 401

    def test_standard_api_key_cannot_invoke_tools(self):
        response = client.get("/tools", headers=API_HEADERS)
        assert response.status_code == 401

    def test_tools_key_cannot_read_sessions(self):
        response = client.get("/sessions", headers=TOOLS_HEADERS)
        assert response.status_code == 401