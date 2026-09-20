import json
import os
from pathlib import Path

DEFAULT_CONFIG_PATH = str(
    Path(__file__).resolve().parent.parent.parent / "config" / "agent_llm_config.json",
)
EXAMPLE_CONFIG_PATH = str(
    Path(__file__).resolve().parent.parent.parent / "config" / "agent_llm_config.example.json",
)


def load_config(path: str | None = None) -> dict:
    explicit_path = path or os.getenv("OPENCLAW_CONFIG")
    selected_path = explicit_path or DEFAULT_CONFIG_PATH
    if not explicit_path and not Path(selected_path).is_file():
        selected_path = EXAMPLE_CONFIG_PATH
    with open(selected_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_llm_config(config: dict | None = None) -> dict:
    cfg = config or load_config()
    return cfg.get("llm", {})


def get_agent_config(config: dict | None = None) -> dict:
    cfg = config or load_config()
    return cfg.get("agent", {})


def get_server_config(config: dict | None = None) -> dict:
    cfg = config or load_config()
    return cfg.get("server", {"host": "0.0.0.0", "port": 5000})
