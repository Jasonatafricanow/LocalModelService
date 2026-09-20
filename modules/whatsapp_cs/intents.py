"""Intent classification via Ollama few-shot prompting.

Uses Qwen2.5 7B running on local Ollama to classify customer
messages into predefined intents with few-shot examples.
"""
import logging

import requests

logger = logging.getLogger(__name__)

INTENTS = [
    "greeting",
    "product_inquiry",
    "stock_check",
    "order_status",
    "return_request",
    "complaint",
    "goodbye",
    "unknown",
]

FEW_SHOT_EXAMPLES = [
    # --- greetings ---
    {"role": "user", "content": "Olá, bom dia!"},
    {"role": "assistant", "content": "greeting"},
    {"role": "user", "content": "Hi, good morning!"},
    {"role": "assistant", "content": "greeting"},
    # --- product inquiry ---
    {"role": "user", "content": "Qual a diferença entre o X200 e o X200 Pro?"},
    {"role": "assistant", "content": "product_inquiry"},
    {"role": "user", "content": "Does the X200 come in blue?"},
    {"role": "assistant", "content": "product_inquiry"},
    # --- stock check ---
    {"role": "user", "content": "Tem o X300 disponível?"},
    {"role": "assistant", "content": "stock_check"},
    {"role": "user", "content": "Do you have the X200 in stock right now?"},
    {"role": "assistant", "content": "stock_check"},
    {"role": "user", "content": "Quanto custa o TAB-A70?"},
    {"role": "assistant", "content": "stock_check"},
    # --- order status ---
    {"role": "user", "content": "Quero saber o status do meu pedido #12345"},
    {"role": "assistant", "content": "order_status"},
    {"role": "user", "content": "Where is my order #12345?"},
    {"role": "assistant", "content": "order_status"},
    {"role": "user", "content": "Meu pedido #67890 ainda não chegou"},
    {"role": "assistant", "content": "order_status"},
    # --- return request ---
    {"role": "user", "content": "Quero devolver o produto que comprei"},
    {"role": "assistant", "content": "return_request"},
    {"role": "user", "content": "I want to return my purchase"},
    {"role": "assistant", "content": "return_request"},
    {"role": "user", "content": "Como faço para trocar este item?"},
    {"role": "assistant", "content": "return_request"},
    # --- complaint ---
    {"role": "user", "content": "O produto chegou com defeito, quero reclamar"},
    {"role": "assistant", "content": "complaint"},
    {"role": "user", "content": "The product is damaged, I want to complain"},
    {"role": "assistant", "content": "complaint"},
    {"role": "user", "content": "Estou insatisfeito com a qualidade do produto"},
    {"role": "assistant", "content": "complaint"},
    # --- goodbye ---
    {"role": "user", "content": "Obrigado, tchau!"},
    {"role": "assistant", "content": "goodbye"},
    {"role": "user", "content": "Thanks, bye!"},
    {"role": "assistant", "content": "goodbye"},
]

SYSTEM_PROMPT = (
    "You are an intent classifier for a WhatsApp customer service system.\n"
    "Classify the customer's message into exactly one of these intents:\n"
    + ", ".join(INTENTS)
    + "\n\nRespond with ONLY the intent name, nothing else."
)


def classify_intent(
    message: str,
    ollama_base_url: str = "http://localhost:11434",
    model: str = "qwen2.5:7b",
) -> str:
    """Classify message intent using few-shot prompting via Ollama.

    Returns one of the INTENTS list.  Falls back to ``"unknown"``
    on any error or unrecognised response.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT_EXAMPLES,
        {"role": "user", "content": message},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 16},
    }

    try:
        resp = requests.post(
            f"{ollama_base_url}/api/chat",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        intent = result.get("message", {}).get("content", "").strip().lower()

        if intent in INTENTS:
            return intent
        logger.warning("Unknown intent from LLM: '%s'", intent)
        return "unknown"
    except requests.RequestException as e:
        logger.error("Ollama intent classification failed: %s", e)
        return "unknown"
