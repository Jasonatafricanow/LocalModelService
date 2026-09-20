"""Main message handler for the WhatsApp Customer Service module.

Orchestrates the full message processing pipeline:

  1. Vision analysis (if image is present)
  2. Intent classification via :mod:`intents`
  3. Business-logic lookup via :mod:`business_ops`
  4. Response generation (template fill or LLM fallback)
  5. Message dispatch via :class:`whatsapp_bridge.WhatsAppBridge`
"""
import json
import logging
import os
import re
from typing import Optional

import requests

from src.i18n import LangManager, LangSession
from src.install import gpu_detector
from . import business_ops
from . import intents
from . import knowledge_base
from . import vision
from .whatsapp_bridge import WhatsAppBridge

logger = logging.getLogger(__name__)

# Explicitly load knowledge base (not on import)
# Primary: Obsidian vault (shared knowledge base); fallback: local knowledge/
_k_base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge")
_obsidian_vault = os.getenv(
    "OBSIDIAN_VAULT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "whatsapp-cs-kb"),
)
if os.path.isdir(os.path.join(_obsidian_vault, "话术库")):
    k_base_dir = _obsidian_vault
    logger.info("Using Obsidian vault as knowledge base: %s", _obsidian_vault)
else:
    k_base_dir = _k_base_dir
    logger.info("Using local knowledge directory: %s", k_base_dir)
knowledge_base.load_knowledge(k_base_dir)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_DIR = os.path.join(_HERE, "templates")

# Multi-language template manager (shared i18n module)
_lang = LangManager(template_dir=_TEMPLATE_DIR, default_lang="pt")

# Per-sender language detection with 3-message window + locking
_session = LangSession(_lang, default_lang="pt", window_size=3)

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def _resolve_models() -> tuple[str, str]:
    """Resolve the chat + vision model tags.

    The server config (``config/agent_llm_config.json``, written by the
    installer) is the source of truth. GPU auto-detection is used only as a
    fallback to fill in any value the config does not provide, so the module
    stays consistent with the main agent instead of diverging from it.
    """
    chat = vision = None
    try:
        from src.core.config import get_llm_config
        llm_cfg = get_llm_config()
        chat = llm_cfg.get("model") or None
        vision = llm_cfg.get("vision_model") or None
    except Exception as e:  # config missing / unreadable — fall back to GPU
        logger.warning("Could not load LLM config, using GPU detection: %s", e)

    if not chat or not vision:
        gpu = gpu_detector.detect_gpu()
        logger.info(
            "GPU detected: %s (%s, %s GB VRAM)",
            gpu["name"], gpu["type"], gpu["vram_gb"],
        )
        if not chat:
            chat = gpu["recommended_model"]
        if not vision:
            # Prefer a dedicated vision model; otherwise reuse the chat model
            # (only useful when the chat model is itself multimodal).
            vision = gpu.get("recommended_vision_model") or chat

    logger.info("WhatsApp module — chat model: %s | vision model: %s", chat, vision)
    return chat, vision


LLM_MODEL, VISION_MODEL = _resolve_models()

# These intents are handled with template responses + optional business ops.
# All other intents fall back to the LLM for response generation.
HIGH_FREQUENCY_INTENTS = {"greeting", "goodbye", "stock_check", "order_status"}

# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

_FALLBACK_SYSTEM_PROMPT = (
    "You are a helpful customer service assistant for LojaTech, "
    "an electronics store.\n"
    "Customer intent: {intent}\n"
    "{lang_instruction}\n\n"
    "Keep responses concise (under 200 characters) and helpful.\n"
    "Do not use markdown formatting.\n"
    "Respond directly to the customer — no introductory phrases."
)




def _llm_fallback(
    message: str,
    intent: str,
    lang: str,
    vision_info: Optional[dict] = None,
    locked: bool = False,
) -> str:
    """Generate a natural-language response via Ollama for non-templated intents."""
    lang_instruction = (
        _lang.get_lock_instruction(lang) if locked
        else _lang.get_llm_instruction(lang)
    )

    vision_context = ""
    if vision_info and vision_info.get("product_model"):
        vision_context = (
            f"\nThe customer sent an image showing:\n"
            f"  Product: {vision_info['product_model']}\n"
            f"  Quantity: {vision_info.get('quantity', 'unknown')}\n"
            f"  Serial numbers: {vision_info.get('serial_numbers', [])}\n"
        )

    user_message = (
        f"{vision_context}\nCustomer message: {message}"
        if vision_context
        else message
    )

    # Build system prompt with optional knowledge base context
    system_prompt = _FALLBACK_SYSTEM_PROMPT.format(
        intent=intent, lang_instruction=lang_instruction,
    )
    knowledge_context = knowledge_base.retrieve(message)
    if knowledge_context:
        system_prompt += (
            "\n\nRelevant knowledge base context:\n"
            f"{knowledge_context}"
        )

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 256},
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("message", {}).get("content", "").strip()
    except requests.RequestException as e:
        logger.error("LLM fallback failed: %s", e)
        return _lang.t("error", lang, default="Sorry, an error occurred.")


# ---------------------------------------------------------------------------
# Product / order extraction helpers
# ---------------------------------------------------------------------------

def _find_product_in_text(text: str) -> Optional[str]:
    """Scan *text* for a known product model identifier."""
    known = business_ops.get_known_products()
    upper_set = {p.upper(): p for p in known}

    for word in text.upper().split():
        cleaned = word.strip(".,!?[]():;\"'")
        if cleaned in upper_set:
            return upper_set[cleaned]
    return None


def _find_order_id(text: str) -> Optional[str]:
    """Extract a numeric order ID from text (``#12345`` or ``12345``)."""
    match = re.search(r"#?(\d{4,})", text)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def handle_message(
    bridge: WhatsAppBridge,
    sender: str,
    message_text: Optional[str] = None,
    image_data: Optional[bytes] = None,
) -> str:
    """Process an incoming message and send a reply.

    This is the main entry point for the WhatsApp customer service module.
    Language is auto-detected over a 3-message window, then locked.
    Explicit language-switch commands ("Fale português") override immediately.

    Args:
        bridge: Initialised :class:`WhatsAppBridge` used to dispatch the reply.
        sender: The customer's phone number (recipient of the reply).
        message_text: Text content of the incoming message (may be ``None``
            when the message contains only an image).
        image_data: Raw image bytes (``None`` for text-only messages).

    Returns:
        The reply text that was dispatched.
    """
    # Resolve language from session state (detection + locking)
    lang, locked = _session.advance(sender, message_text or "")

    reply: Optional[str] = None

    # ---- Step 1: Vision analysis (image messages) -------------------------
    vision_info: Optional[dict] = None
    if image_data:
        logger.info("Analyzing image from %s (%d bytes)", sender, len(image_data))
        vision_info = vision.analyze_image(image_data, OLLAMA_BASE_URL, VISION_MODEL)

        if vision_info and vision_info.get("product_model"):
            enriched = (
                f"[Image shows product: {vision_info['product_model']}"
                f" qty: {vision_info.get('quantity', '?')}]"
            )
            message_text = f"{message_text or ''} {enriched}".strip()
        else:
            logger.warning("Vision analysis returned no product info")

    # ---- Step 2: Intent classification -----------------------------------
    text_for_classification = message_text or ""
    intent = intents.classify_intent(text_for_classification, OLLAMA_BASE_URL, LLM_MODEL)
    logger.info("Intent for %s: '%s'", sender, intent)

    # ---- Step 3: Generate response ----------------------------------------

    if intent == "greeting":
        reply = _lang.t("greeting", lang, default="Hello!")

    elif intent == "goodbye":
        reply = _lang.t("goodbye", lang, default="Goodbye!")

    elif intent == "stock_check":
        product = (
            vision_info.get("product_model")
            if vision_info and vision_info.get("product_model")
            else _find_product_in_text(message_text or "")
        )
        if product:
            info = business_ops.check_stock(product)
            reply = _lang.t(
                "stock_check_result", lang,
                default="Product {{product}}: {{message}}",
                product=info["product"],
                status="in stock" if info["in_stock"] else "out of stock",
                details=info["message"],
            )
        else:
            reply = _lang.t(
                "need_more_info", lang,
                default="Please tell me which product you would like to check.",
            )

    elif intent == "order_status":
        order_id = _find_order_id(message_text or "")
        if order_id:
            info = business_ops.get_order_status(order_id)
            reply = _lang.t(
                "order_status", lang,
                default="Order #{{order_id}}: {{status}}",
                order_id=info["order_id"],
                status=info["status"],
                details=f"Estimated delivery: {info.get('estimated_delivery', 'N/A')}",
            )
        else:
            reply = _lang.t(
                "need_more_info", lang,
                default="Please provide your order number so I can check the status.",
            )

    else:
        # product_inquiry, return_request, complaint, unknown → LLM fallback
        reply = _llm_fallback(
            message_text or "",
            intent,
            lang,
            vision_info,
            locked=locked,
        )

    # ---- Step 4: Send reply -----------------------------------------------
    if not reply:
        reply = _lang.t("error", lang, default="Sorry, an error occurred.")

    bridge.send_message(sender, reply)
    logger.info("Reply to %s: %.120s", sender, reply)
    return reply
