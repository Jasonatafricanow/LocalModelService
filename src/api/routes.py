import asyncio
import json
import logging
import os
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.agent.agent import get_agent
from src.api.auth import (
    ApiPrincipal,
    require_api_principal,
    require_tools_principal,
)
from src.api.openai_proxy import forward_chat
from src.api.inference_queue import inference_queue
from src.api.schemas import ChatCompletionRequest, ChatRequest, ToolInvokeRequest
from src.core.config import get_llm_config
from src.memory.manager import ConversationMemory
from src.tools.registry import registry

logger = logging.getLogger(__name__)
router = APIRouter()
memory = ConversationMemory(
    os.getenv("OPENCLAW_MEMORY_DB", str(Path(__file__).resolve().parents[2] / "data" / "conversations.sqlite3")),
    ttl_seconds=int(os.getenv("OPENCLAW_MEMORY_TTL_SECONDS", "2592000")),
    max_messages=int(os.getenv("OPENCLAW_MEMORY_MAX_MESSAGES", "200")),
    max_sessions=int(os.getenv("OPENCLAW_MEMORY_MAX_SESSIONS", "100")),
)


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
    release = await inference_queue.acquire()
    try:
        history = memory.get_history(principal.owner_id, req.session_id)
        reply = await agent.achat(req.message, history)
        memory.add_exchange(principal.owner_id, req.session_id, req.message, reply)
    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release()

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
    release = await inference_queue.acquire()

    async def generate():
        try:
            history = memory.get_history(principal.owner_id, req.session_id)
            full = ""
            async for chunk in agent.astream(req.message, history):
                if chunk:
                    full += chunk
                    yield (
                        "data: "
                        + json.dumps({"content": chunk}, ensure_ascii=False)
                        + "\n\n"
                    )
            memory.add_exchange(principal.owner_id, req.session_id, req.message, full)
            yield "data: [DONE]\n\n"
        finally:
            release()

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/v1/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    _principal: ApiPrincipal = Depends(require_api_principal),
):
    return await forward_chat(req.model_dump(exclude_unset=True))


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
