"""Tests for modules/whatsapp_cs/intents.py"""
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
import sys
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest
from unittest.mock import patch, MagicMock

from modules.whatsapp_cs.intents import classify_intent, INTENTS


def test_intents_list_defined():
    """INTENTS list contains expected intent categories."""
    expected = {"greeting", "product_inquiry", "stock_check", "order_status",
                "return_request", "complaint", "goodbye", "unknown"}
    assert set(INTENTS) == expected
    assert len(INTENTS) == 8


def test_intents_all_lowercase():
    """All intents should be lowercase."""
    for intent in INTENTS:
        assert intent == intent.lower(), f"{intent} is not lowercase"


@patch("modules.whatsapp_cs.intents.requests.post")
def test_classify_greeting(mock_post):
    """Classify a greeting message returns 'greeting'."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "greeting"}
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_intent("Good morning!")
    assert result == "greeting"


@patch("modules.whatsapp_cs.intents.requests.post")
def test_classify_product_inquiry(mock_post):
    """Classify a product inquiry returns 'product_inquiry'."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "product_inquiry"}
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_intent("How much is the X200?")
    assert result == "product_inquiry"


@patch("modules.whatsapp_cs.intents.requests.post")
def test_classify_unknown_on_error(mock_post):
    """On request error, classify returns 'unknown'."""
    import requests
    mock_post.side_effect = requests.RequestException("Connection refused")

    result = classify_intent("Hello")
    assert result == "unknown"


@patch("modules.whatsapp_cs.intents.requests.post")
def test_classify_unknown_on_unexpected_intent(mock_post):
    """When LLM returns an unexpected intent, return 'unknown'."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "something_weird"}
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_intent("Some weird message")
    assert result == "unknown"
    assert result not in INTENTS or result == "unknown"


@patch("modules.whatsapp_cs.intents.requests.post")
def test_classify_case_insensitive(mock_post):
    """LLM response should be lowercased before matching."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "GREETING"}
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_intent("Hi!")
    assert result == "greeting"


@patch("modules.whatsapp_cs.intents.requests.post")
def test_classify_whitespace_trimmed(mock_post):
    """LLM response with whitespace should be trimmed."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "  goodbye  "}
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_intent("Bye!")
    assert result == "goodbye"


@patch("modules.whatsapp_cs.intents.requests.post")
def test_classify_ollama_url_passed_correctly(mock_post):
    """The ollama_base_url should be passed in the request."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "unknown"}
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    classify_intent("Test", ollama_base_url="http://custom:11434", model="test-model")
    # Verify the URL used
    call_kwargs = mock_post.call_args
    assert call_kwargs is not None
    url = call_kwargs[0][0]  # first positional arg = URL
    assert "custom" in url
    assert "test-model" in str(call_kwargs[1]["json"]["model"])


@patch("modules.whatsapp_cs.intents.requests.post")
def test_classify_empty_message(mock_post):
    """Empty message should still work and return result."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "unknown"}
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_intent("")
    assert result == "unknown"
