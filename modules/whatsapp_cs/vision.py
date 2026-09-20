"""Image analysis via Ollama vision models.

Sends images to an Ollama multimodal model (e.g., qwen2.5vl:7b)
and extracts structured product information from the response.
"""
import base64
import json
import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = (
    "You are a product recognition assistant for an electronics store "
    "customer service system.\n\n"
    "Analyze the image and extract the following information:\n"
    "1. Product model or number (e.g., X200, TAB-A70, FONE-BT100)\n"
    "2. Quantity of items visible\n"
    "3. Any visible serial numbers, part numbers, or barcodes\n\n"
    "Return your response as valid JSON only, using this exact schema:\n"
    '{"product_model": <string or null>, "quantity": <number or null>,'
    ' "serial_numbers": <list of strings>, "description": <string or null>}\n\n'
    "If a field cannot be determined, use null for strings/numbers "
    "and an empty list for serial_numbers."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_image(
    image_data: bytes,
    ollama_base_url: str = "http://localhost:11434",
    model: str = "qwen2.5vl:7b",
) -> dict:
    """Analyze an image using an Ollama vision model.

    Args:
        image_data: Raw image bytes (JPEG, PNG, etc.).
        ollama_base_url: Base URL of the Ollama server.
        model: Vision model name (e.g., ``qwen2.5vl:7b``, ``llava``).

    Returns:
        A dict with keys ``product_model``, ``quantity``,
        ``serial_numbers``, ``description``, and optionally ``error``.
    """
    image_b64 = base64.b64encode(image_data).decode("utf-8")

    # Ollama's native /api/chat takes the prompt as a plain string and the
    # image(s) as raw base64 in a separate "images" list (no data: URI,
    # no OpenAI-style content parts — those only work on /v1/chat/completions).
    messages = [
        {
            "role": "user",
            "content": VISION_SYSTEM_PROMPT,
            "images": [image_b64],
        }
    ]

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1},
    }

    try:
        resp = requests.post(
            f"{ollama_base_url}/api/chat",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        content: str = result.get("message", {}).get("content", "")
        return _parse_vision_response(content)

    except requests.RequestException as e:
        logger.error("Ollama vision analysis failed: %s", e)
        return {
            "product_model": None,
            "quantity": None,
            "serial_numbers": [],
            "description": None,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_vision_response(content: str) -> dict:
    """Attempt to extract a JSON object from the vision model's response.

    Tries, in order:
    1. Direct ``json.loads`` of the entire response.
    2. Extract JSON from a markdown code block (e.g. ```json ... ```).
    3. Return the raw content as ``description`` when no JSON is found.
    """
    # Attempt 1 — direct JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Attempt 2 — JSON inside a markdown code fence
    match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL
    )
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Attempt 3 — best-effort: return raw text as description
    logger.warning("Could not parse JSON from vision response, using raw text")
    return {
        "product_model": None,
        "quantity": None,
        "serial_numbers": [],
        "description": content.strip(),
    }
