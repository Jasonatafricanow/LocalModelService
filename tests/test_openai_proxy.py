import json
import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import openai_proxy, routes
from src.api.inference_queue import InferenceQueue


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENCLAW_API_KEY", "local-test-key")
    monkeypatch.setattr(openai_proxy, "get_llm_config", lambda: {
        "base_url": "http://model.example.invalid", "model": "configured-model"})
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app, headers={"Authorization": "Bearer local-test-key"})


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(openai_proxy.httpx, "AsyncClient", lambda **kw: original(
        transport=httpx.MockTransport(handler), **kw))


def test_preserves_system_tools_parameters_model_and_real_upstream_usage(client, monkeypatch):
    payload = {"model": "chosen-model", "messages": [
        {"role": "system", "content": "Answer briefly"},
        {"role": "user", "content": "weather"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "weather", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "sunny"}],
        "temperature": 0.2, "max_tokens": 55,
        "tools": [{"type": "function", "function": {"name": "weather", "parameters": {"type": "object"}}}],
        "tool_choice": "auto"}
    result = {"id": "chatcmpl-real", "model": "chosen-model", "created": 123,
              "choices": [{"message": {"role": "assistant", "content": "sunny"}, "finish_reason": "stop"}],
              "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}}

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert "authorization" not in request.headers
        assert json.loads(request.content) == payload
        return httpx.Response(200, json=result)

    transport(monkeypatch, handler)
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert response.json() == result


def test_stream_preserves_metadata_usage_finish_reason_and_done(client, monkeypatch):
    frames = [
        {"id": "same", "object": "chat.completion.chunk", "created": 123, "model": "configured-model",
         "choices": [{"index": 0, "delta": {"role": "assistant", "content": "hello"}, "finish_reason": None}]},
        {"id": "same", "object": "chat.completion.chunk", "created": 123, "model": "configured-model",
         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {"id": "same", "choices": [], "usage": {"total_tokens": 8}}]
    wire = "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames) + "data: [DONE]\n\n"

    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "configured-model"
        assert payload["stream_options"] == {"include_usage": True}
        return httpx.Response(200, text=wire, headers={"content-type": "text/event-stream"})

    transport(monkeypatch, handler)
    response = client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "hi"}], "stream": True,
        "stream_options": {"include_usage": True}})
    assert response.status_code == 200
    assert response.text == wire


def test_upstream_error_is_returned_before_starting_success_stream(client, monkeypatch):
    transport(monkeypatch, lambda req: httpx.Response(404, json={"error": {"message": "model missing"}}))
    response = client.post("/v1/chat/completions", json={
        "model": "missing", "messages": [{"role": "user", "content": "hi"}], "stream": True})
    assert response.status_code == 404
    assert response.json() == {"error": {"message": "model missing"}}


def test_unavailable_upstream_returns_502(client, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("unavailable", request=request)
    transport(monkeypatch, handler)
    response = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 502


def test_closing_partial_stream_releases_upstream_and_inference_slot(monkeypatch):
    closed = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"content":"first"}\n\n'
            yield b'data: [DONE]\n\n'

        async def aclose(self):
            closed.append(True)

    async def scenario():
        queue = InferenceQueue(max_waiting=0)
        monkeypatch.setattr(openai_proxy, "inference_queue", queue)
        transport(monkeypatch, lambda req: httpx.Response(200, stream=Stream()))
        response = await openai_proxy.forward_chat({
            "messages": [{"role": "user", "content": "hi"}], "stream": True})
        assert await anext(response.body_iterator) == b'data: {"content":"first"}\n\n'
        with pytest.raises(Exception, match="full"):
            await queue.acquire()
        await response.body_iterator.aclose()
        assert closed
        (await queue.acquire())()
    asyncio.run(scenario())
