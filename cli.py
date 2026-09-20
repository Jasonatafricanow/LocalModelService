#!/usr/bin/env python3
"""
CLI entry point - usage: python cli.py [--host HOST] [--port PORT]
"""
import argparse
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import uvicorn
from src.core.config import load_config, get_server_config


def main():
    parser = argparse.ArgumentParser(description="OpenClaw - AI Agent Server")
    parser.add_argument("--host", type=str, default=None, help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    cfg = load_config()
    server_cfg = get_server_config(cfg)
    host = args.host or server_cfg.get("host", "0.0.0.0")
    port = args.port or int(server_cfg.get("port", 5000))

    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logging.info("OpenClaw starting on %s:%s (reload=%s)", host, port, args.reload)
    uvicorn.run("src.server:app", host=host, port=port, reload=args.reload)


if __name__ == "__main__":
    main()
