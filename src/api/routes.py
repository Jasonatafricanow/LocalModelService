import asyncio
import json
import logging
import time
import uuid

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.agent.agent import get_agent
from src.api.auth import (
    ApiPrincipal,
    require_api_principal,
    require_tools_principal,
)
from src.api.schemas import ChatCompletionRequest, ChatRequest, ToolInvokeRequest
from src.core.config import get_llm_config
from src.memory.manager import ConversationMemory
from src.tools.registry import registry

logger = logging.getLogger(__name__)
router = APIRouter()
memory = ConversationMemory()


@router.get("/health")
async def health():
    """Cheap public health check."""
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
        return {
            "status": "degraded",
            "ollama": "disconnected",
            "error": str(e),
        }


@router.get("/models")
async def list_models(
    _principal: ApiPrincipal = Depends(require_api_principal),
):
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
async def chat(
    req: ChatRequest,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    agent = get_agent()
    history = memory.get_history(principal.owner_id, req.session_id)
    try:
        reply = await agent.achat(req.message, history)
    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail=str(e))

    memory.add_message(principal.owner_id, req.session_id, "user", req.message)
    memory.add_message(principal.owner_id, req.session_id, "assistant", reply)

    return {
        "status": "ok",
        "session_id": req.session_id,
        "response": reply,
        "model": get_llm_config().get("model"),
    }


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    agent = get_agent()
    history = memory.get_history(principal.owner_id, req.session_id)

    async def generate():
        full = ""
        async for chunk in agent.astream(req.message, history):
            if chunk:
                full += chunk
                yield (
                    "data: "
                    + json.dumps({"content": chunk}, ensure_ascii=False)
                    + "\n\n"
                )
        yield "data: [DONE]\n\n"

        memory.add_message(
            principal.owner_id, req.session_id, "user", req.message
        )
        memory.add_message(
            principal.owner_id, req.session_id, "assistant", full
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/v1/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    _principal: ApiPrincipal = Depends(require_api_principal),
):
    agent = get_agent()

    user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user":
            user_msg = m.content
            break

    history = []
    for m in req.messages[:-1]:
        if m.role in ("user", "assistant"):
            history.append({"role": m.role, "content": m.content})

    if req.stream:
        async def generate():
            async for chunk in agent.astream(user_msg, history):
                if chunk:
                    payload = {
                        "choices": [
                            {"delta": {"content": chunk}, "index": 0}
                        ]
                    }
                    yield (
                        "data: "
                        + json.dumps(payload, ensure_ascii=False)
                        + "\n\n"
                    )
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
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "created": int(time.time()),
    }


@router.get("/tools")
async def list_tools(
    _principal: ApiPrincipal = Depends(require_tools_principal),
):
    tools = registry.list_tools()
    return {"tools": tools, "count": len(tools)}


@router.post("/tools/{name}/invoke")
async def invoke_tool(
    name: str,
    req: ToolInvokeRequest,
    _principal: ApiPrincipal = Depends(require_tools_principal),
):
    tool = registry.get(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    try:
        result = tool.run(**req.arguments)
        return {"status": "ok", "tool": name, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    principal: ApiPrincipal = Depends(require_api_principal),
):
    sessions = memory.list_sessions(principal.owner_id)
    return {"sessions": sessions, "count": len(sessions)}


@router.delete("/sessions/{session_id}")
async def clear_session(
    session_id: str,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    memory.clear(principal.owner_id, session_id)
    return {"status": "ok", "session_id": session_id}


@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    include_in_schema=False,
)
async def friendly_404(full_path: str, request: Request):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "path": request.url.path,
            "hint": "Unknown endpoint. See GET / for service info.",
        },
    )
