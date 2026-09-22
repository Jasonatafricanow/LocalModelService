"""
OpenClaw server - FastAPI application setup.
Extracted from main.py for cleaner module separation.
"""
import importlib
import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI

# Path setup: ensure the project root is importable so ``src.*`` resolves.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.core.config import load_config
from src.tools.registry import registry
from src.tools.builtin.time_tool import TimeTool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("openclaw")

# Auto-load modules
MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"

def _auto_load_modules():
    if not MODULES_DIR.exists():
        return
    sys.path.insert(0, str(MODULES_DIR.parent))
    for f in sorted(MODULES_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"modules.{f.stem}")
            logger.info("Loaded module: modules.%s", f.stem)
        except Exception as e:
            logger.warning("Failed to load module modules.%s: %s", f.stem, e)
    for d in sorted(MODULES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        if not (d / "__init__.py").exists():
            continue
        try:
            importlib.import_module(f"modules.{d.name}")
            logger.info("Loaded module package: modules.%s", d.name)
        except Exception as e:
            logger.warning("Failed to load module package modules.%s: %s", d.name, e)

_auto_load_modules()

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    logger.info("OpenClaw starting - model: %s, ollama: %s", llm_cfg.get("model"), llm_cfg.get("base_url"))
    yield

# Register built-in tools
registry.register(TimeTool())

app = FastAPI(
    title="OpenClaw",
    version="1.0.0",
    description="Agent server powered by Ollama models",
    lifespan=lifespan,
)

@app.get("/")
async def root():
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    return {
        "name": "OpenClaw",
        "version": "1.0.0",
        "model": llm_cfg.get("model"),
        "tools_count": len(registry.list_tools()),
        "status": "running",
    }

# Include API routes last so the router's catch-all 404 never shadows "/".
from src.api.routes import router
app.include_router(router)