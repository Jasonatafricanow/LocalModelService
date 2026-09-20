import asyncio
import json
import logging
import time
import uuid

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.core.config import get_llm_config
from src.agent.agent import get_agent
from src.tools.registry import registry
from src.memory.manager import ConversationMemory
from src.api.schemas import (
    ChatRequest,
    ChatCompletionRequest,
    ToolInvokeRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()
memory = ConversationMemory()


@router.get("/health")
async def health():
    """Lightweight health check — verifies Ollama is reachable via /api/tags.

    (Does not run a full inference so the endpoint stays cheap.)
    """
    llm_cfg = get_llm_config()
    base_url = llm_cfg.get("base_url", "http://localhost:11434")
    try:
        resp = await asyncio.to_thread(
            requests.get, f"{base_url}/api/tags", timeout=5
        )
        connected = resp.status_code == 200
        return {
            "status": "ok" if connected else "degraded",
            "model": llm_cfg.get("model"),
            "ollama": "connected" if connected else "disconnected",
        }
    except Exception as e:
        return {"status": "degraded", "ollama": "disconnected", "error": str(e)}


@router.get("/models")
async def list_models():
    llm_cfg = get_llm_config()
    base_url = llm_cfg.get("base_url", "http://localhost:11434")
    try:
        resp = await asyncio.to_thread(
            requests.get, f"{base_url}/api/tags", timeout=5
        )
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"Ollama returned status {resp.status_code}"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/chat")
async def chat(req: ChatRequest):
    agent = get_agent()
    history = memory.get_history(req.session_id)
    try:
        reply = await agent.achat(req.message, history)
    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail=str(e))

    memory.add_message(req.session_id, "user", req.message)
    memory.add_message(req.session_id, "assistant", reply)

    return {
        "status": "ok",
        "session_id": req.session_id,
        "response": reply,
        "model": get_llm_config().get("model"),
    }


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    agent = get_agent()
    history = memory.get_history(req.session_id)
    llm_cfg = get_llm_config()

    async def generate():
        full = ""
        async for chunk in agent.astream(req.message, history):
            if chunk:
                full += chunk
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        memory.add_message(req.session_id, "user", req.message)
        memory.add_message(req.session_id, "assistant", full)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    agent = get_agent()

    # 提取最后一条 user 消息
    user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user":
            user_msg = m.content
            break

    # 将历史消息转为记忆格式
    history = []
    for m in req.messages[:-1]:
        if m.role in ("user", "assistant"):
            history.append({"role": m.role, "content": m.content})

    if req.stream:
        async def generate():
            async for chunk in agent.astream(user_msg, history):
                if chunk:
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk}, 'index': 0}]}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(generate(), media_type="text/event-stream")

    reply = await agent.achat(user_msg, history)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "created": int(time.time()),
    }


@router.get("/tools")
async def list_tools():
    return {"tools": registry.list(), "count": len(registry.list())}


@router.post("/tools/{name}/invoke")
async def invoke_tool(name: str, req: ToolInvokeRequest):
    tool = registry.get(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    try:
        result = tool.run(**req.arguments)
        return {"status": "ok", "tool": name, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    return {"sessions": memory.list_sessions(), "count": len(memory.list_sessions())}


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    memory.clear(session_id)
    return {"status": "ok", "session_id": session_id}


@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    include_in_schema=False,
)
async def friendly_404(full_path: str, request: Request):
    """Catch-all returning a friendly JSON 404 for any unmatched path.

    Registered at the end of the router so it never shadows the real API
    routes declared above it.
    """
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "path": request.url.path,
            "hint": "Unknown endpoint. See GET / for service info.",
        },
    )
