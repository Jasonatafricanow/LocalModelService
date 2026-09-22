import pytest

from src.main import validate_bind_security


def test_loopback_bind_does_not_require_api_key(monkeypatch):
    monkeypatch.delenv("OPENCLAW_API_KEY", raising=False)
    validate_bind_security("127.0.0.1")
    validate_bind_security("localhost")
    validate_bind_security("::1")


def test_non_loopback_bind_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENCLAW_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENCLAW_API_KEY"):
        validate_bind_security("0.0.0.0")


def test_non_loopback_bind_allowed_after_explicit_auth_config(monkeypatch):
    monkeypatch.setenv("OPENCLAW_API_KEY", "configured-secret")
    validate_bind_security("0.0.0.0")
