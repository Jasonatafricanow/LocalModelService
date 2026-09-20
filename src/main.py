"""
OpenClaw entry point - CLI interface for starting the server.
"""
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import uvicorn
from src.core.config import load_config, get_server_config


def main():
    cfg = load_config()
    server_cfg = get_server_config(cfg)
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 5000))

    import logging
    logging.info("OpenClaw starting on %s:%s", host, port)
    uvicorn.run("src.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
