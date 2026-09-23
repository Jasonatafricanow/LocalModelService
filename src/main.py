"""OpenClaw CLI entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import uvicorn

from src.core.config import get_server_config, load_config


def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {
        "127.0.0.1",
        "localhost",
        "::1",
        "[::1]",
    }


def validate_bind_security(host: str) -> None:
    """Refuse non-loopback binding unless private API auth is configured."""
    if _is_loopback_host(host):
        return
    if not os.getenv("OPENCLAW_API_KEY", "").strip():
        raise RuntimeError(
            "OPENCLAW_API_KEY is required before binding OpenClaw "
            f"to non-loopback host {host!r}"
        )


def main():
    cfg = load_config()
    server_cfg = get_server_config(cfg)
    host = server_cfg.get("host", "127.0.0.1")
    port = int(server_cfg.get("port", 5000))
    validate_bind_security(host)

    import logging
    logging.info("OpenClaw starting on %s:%s", host, port)
    uvicorn.run("src.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
