import sys

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


def test_cli_entrypoint_also_refuses_unauthenticated_non_loopback_bind(monkeypatch):
    import cli

    monkeypatch.delenv("OPENCLAW_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["cli.py", "--host", "0.0.0.0"])
    started = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: started.append(a))
    with pytest.raises(RuntimeError, match="OPENCLAW_API_KEY"):
        cli.main()
    assert started == []


def test_cli_entrypoint_defaults_to_loopback(monkeypatch):
    import cli

    monkeypatch.delenv("OPENCLAW_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["cli.py"])
    monkeypatch.setattr(cli, "get_server_config", lambda cfg: {})
    started = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: started.append(k["host"]))
    cli.main()
    assert started == ["127.0.0.1"]
