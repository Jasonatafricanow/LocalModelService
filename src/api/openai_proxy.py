"""Forward the OpenAI chat wire protocol to the configured local Ollama server."""
import logging

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from src.core.config import get_llm_config
from src.api.inference_queue import inference_queue

logger = logging.getLogger(__name__)


async def forward_chat(payload: dict):
    config = get_llm_config()
    payload.setdefault("model", config.get("model", "qwen2.5"))
    url = config.get("base_url", "http://localhost:11434").rstrip("/") + "/v1/chat/completions"
    release = await inference_queue.acquire()
    client = None
    upstream = None

    async def close():
        try:
            if upstream is not None:
                await upstream.aclose()
        finally:
            try:
                if client is not None:
                    await client.aclose()
            finally:
                release()

    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5), trust_env=False)
        # Client credentials authenticate this service only; never forward them upstream.
        request = client.build_request("POST", url, json=payload, headers={"Accept-Encoding": "identity"})
        upstream = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        await close()
        logger.warning("Ollama connection failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Local model server unavailable") from exc
    except BaseException:
        await close()
        raise

    if not payload.get("stream") or upstream.is_error:
        try:
            content = await upstream.aread()
            return Response(content, status_code=upstream.status_code,
                            media_type=upstream.headers.get("content-type", "application/json"))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Local model response interrupted") from exc
        finally:
            await close()

    async def generate():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await close()

    return StreamingResponse(generate(), status_code=upstream.status_code,
                             media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
