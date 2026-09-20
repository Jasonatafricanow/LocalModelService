from langchain_ollama import ChatOllama

from src.core.config import get_llm_config


_llm_instance: ChatOllama | None = None


def get_llm(cfg: dict | None = None) -> ChatOllama:
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance

    llm_cfg = get_llm_config(cfg)
    _llm_instance = ChatOllama(
        model=llm_cfg.get("model", "qwen2.5"),
        base_url=llm_cfg.get("base_url", "http://localhost:11434"),
        temperature=llm_cfg.get("temperature", 0.7),
        top_p=llm_cfg.get("top_p", 0.9),
        num_ctx=llm_cfg.get("num_ctx", 4096),
        num_predict=llm_cfg.get("max_tokens", 4096),
        timeout=llm_cfg.get("timeout", 600),
        keep_alive=llm_cfg.get("keep_alive", -1),
    )
    return _llm_instance
