"""Model recommendation, selection, and download manager.

Built on top of the GPU detector and Ollama API to provide:
1. Model recommendation based on GPU profile
2. Interactive model selection
3. Model download with progress
4. Auto-configuration of agent_llm_config.json
"""
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests

from . import ollama as ollama_mod

logger = logging.getLogger(__name__)

# Relative to project root (resolved from this file's location)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = _PROJECT_ROOT / "config" / "agent_llm_config.json"

# Well-known model sizes for comparison
MODEL_SIZES = {
    "qwen2.5:0.5b": {"params": "0.5B", "ram_min": 2, "disk": 0.5},
    "qwen2.5:1.5b": {"params": "1.5B", "ram_min": 4, "disk": 1.0},
    "qwen2.5:3b": {"params": "3B", "ram_min": 4, "disk": 2.0},
    "qwen2.5:7b": {"params": "7B", "ram_min": 8, "disk": 4.5},
    "qwen2.5:14b": {"params": "14B", "ram_min": 16, "disk": 9.0},
    "qwen2.5:32b": {"params": "32B", "ram_min": 24, "disk": 20.0},
    "qwen2.5:72b": {"params": "72B", "ram_min": 48, "disk": 45.0},
    "qwen2.5vl:3b": {"params": "3B (VL)", "ram_min": 4, "disk": 2.0},
    "qwen2.5vl:7b": {"params": "7B (VL)", "ram_min": 8, "disk": 4.5},
    "qwen2.5vl:14b": {"params": "14B (VL)", "ram_min": 12, "disk": 9.0},
    "qwen2.5vl:32b": {"params": "32B (VL)", "ram_min": 20, "disk": 19.0},
    "qwen2.5vl:72b": {"params": "72B (VL)", "ram_min": 40, "disk": 43.0},
    "nomic-embed-text": {"params": "embed", "ram_min": 2, "disk": 0.3},
    "llama3.2:3b": {"params": "3B", "ram_min": 4, "disk": 2.0},
    "llama3.2:1b": {"params": "1B", "ram_min": 4, "disk": 1.0},
}

# Tier metadata for installer UI (model names come from gpu_detector results)
TIER_META = {
    "cpu": {
        "label": "CPU (no GPU)",
        "note": "Qwen2.5 3B for daily use; can also pull qwen2.5vl:3b for vision testing (slow but works)",
    },
    "nvidia_8gb": {
        "label": "NVIDIA ~8 GB (e.g. RTX 4060)",
        "note": "Multimodal (VL) — 3B fits comfortably with room for context",
    },
    "nvidia_16gb": {
        "label": "NVIDIA ~16 GB (e.g. RTX 4070+)",
        "note": "Multimodal (VL) — 14B Q4 (~9 GB) with GPU headroom",
    },
    "amd_16gb": {
        "label": "AMD ~16 GB (e.g. RX 9070 XT)",
        "note": "Multimodal (VL) — ROCm verified, 14B Q4 fits",
    },
    "high": {
        "label": "High-end (24GB+)",
        "note": "Multimodal (VL) — 32B Q4 for production quality",
    },
}

# Concrete chat + vision model per tier (matches CLAUDE_TASK.md).
# ``vision`` is a *separate* multimodal model; ``None`` skips vision.
# Note: on 8 GB cards the chat + vision pair does not fit in VRAM at the
# same time, so vision runs by swapping models (see ``write_config`` which
# uses a finite keep_alive for tight cards).
TIER_MODELS = {
    "cpu":         {"chat": "qwen2.5:3b",  "vision": None},
    "nvidia_8gb":  {"chat": "qwen2.5:7b",  "vision": "qwen2.5vl:7b"},
    "nvidia_16gb": {"chat": "qwen2.5:14b", "vision": "qwen2.5vl:7b"},
    "amd_16gb":    {"chat": "qwen2.5:14b", "vision": "qwen2.5vl:7b"},
    "high":        {"chat": "qwen2.5:32b", "vision": "qwen2.5vl:7b"},
}


# ===================================================================
# Recommendation
# ===================================================================


def get_recommendation_from_gpu(gpu_info: dict[str, Any]) -> dict[str, Any]:
    """Map GPU detection result to a model recommendation set.

    Model names are read directly from *gpu_info* (which comes from
    :func:`gpu_detector.detect_gpu`), keeping model selection centralised.

    Args:
        gpu_info: Output from :func:`detect.check_gpu`

    Returns:
        dict with keys: tier, label, chat, vision, embed, note,
        alternatives (list of other suitable configs)
    """
    gpu_type = gpu_info.get("type", "cpu")
    vram = gpu_info.get("vram_gb", 0)

    if gpu_type == "cpu":
        tier = "cpu"
    elif gpu_type == "nvidia":
        if vram >= 24:
            tier = "high"
        elif vram >= 14:
            tier = "nvidia_16gb"
        else:
            tier = "nvidia_8gb"
    elif gpu_type == "amd":
        if vram >= 24:
            tier = "high"
        else:
            tier = "amd_16gb"
    else:
        tier = "cpu"

    meta = TIER_META.get(tier, TIER_META["cpu"])

    result = {
        "tier": tier,
        "vram_gb": vram,
        "label": meta["label"],
        "chat": gpu_info.get("recommended_model", "qwen2.5:3b"),
        "vision": gpu_info.get("recommended_vision_model"),
        "embed": "nomic-embed-text",
        "note": meta["note"],
        "alternatives": [],
    }

    # Build alternatives list (different VRAM tiers the user might consider).
    # Each alternative carries concrete model names so the installer can
    # actually download the selected combo.
    alt_tiers = ["cpu"]
    if tier in ("nvidia_8gb", "cpu"):
        alt_tiers.append("nvidia_16gb")
    if tier != "high":
        alt_tiers.append("high")

    result["alternatives"] = [
        {
            "label": TIER_META[t]["label"],
            "note": TIER_META[t]["note"],
            "chat": TIER_MODELS[t]["chat"],
            "vision": TIER_MODELS[t]["vision"],
        }
        for t in alt_tiers if t != tier
    ]

    return result


def get_model_size_info(model_name: str) -> dict[str, Any]:
    """Return size info for a known model, or a best-guess."""
    known = MODEL_SIZES.get(model_name)
    if known:
        return known
    # Try partial match (strip quant suffix if any)
    base = model_name.split(":")[0] if ":" in model_name else model_name
    for key, val in MODEL_SIZES.items():
        if key.startswith(base):
            return val
    return {"params": "?", "ram_min": 8, "disk": 5.0}


# ===================================================================
# VRAM estimation and context-length recommendation
# ===================================================================

# Approximate VRAM consumed by each model in GB (Q4 quantised)
MODEL_VRAM_GB = {
    # Pure text models (Q4) — stable, no image spike
    "qwen2.5:0.5b":    0.5,
    "qwen2.5:1.5b":    1.0,
    "qwen2.5:3b":      2.0,
    "qwen2.5:7b":      4.5,
    "qwen2.5:14b":     9.0,
    "qwen2.5:32b":    19.0,
    "qwen2.5:72b":    43.0,
    # VL models (Q4) — PEAK VRAM (includes vision encoder compute buffers
    # during image processing, which is the worst case for VRAM planning)
    "qwen2.5vl:3b":   4.0,   # idles 3.5 GB, peaks 4.0 GB when processing image
    "qwen2.5vl:7b":   7.5,   # peaks near 8 GB limit — risky on 8GB cards
    "qwen2.5vl:14b": 11.0,   # estimated peak on 16 GB GPUs
    "qwen2.5vl:32b": 21.0,   # estimated peak
    "qwen2.5vl:72b": 45.0,   # estimated peak
    # Embeddings / other
    "nomic-embed-text": 0.3,
    "llama3.2:3b":     2.0,
    "llama3.2:1b":     1.0,
}

# Overhead — peak model VRAM already includes vision compute buffers,
# so we just need minimal CUDA/Ollama overhead + small safety margin.
OLLAMA_OVERHEAD_GB    = 0.3   # Minimal Ollama + CUDA context overhead
SAFETY_MARGIN_GB      = 0.3   # Small headroom

# KV cache footprint per 1 024 tokens, in GB.
# Qwen models use GQA (Grouped Query Attention) reducing KV pressure.
# Numbers are conservative (FP16 KV cache).
KV_CACHE_PER_1K_TOKENS_GB = {
    # Model family          → GB per 1 024 tokens
    "qwen2.5vl:3b":     0.08,
    "qwen2.5vl:7b":     0.14,
    "qwen2.5vl:14b":    0.22,
    "qwen2.5vl:32b":    0.25,
    "qwen2.5vl:72b":    0.30,
    "qwen2.5:7b":        0.12,
    "qwen2.5:14b":       0.20,
    "qwen2.5:32b":       0.22,
    "qwen2.5:3b":        0.06,
}


def _find_model_vram(model_name: str) -> float:
    """Estimate VRAM footprint for *model_name* in GB."""
    if model_name in MODEL_VRAM_GB:
        return MODEL_VRAM_GB[model_name]
    # Partial match (strip variant suffix)
    for key, val in MODEL_VRAM_GB.items():
        if model_name.startswith(key.rstrip("0123456789:b")):
            return val
    # Unknown model — use disk estimate if available
    size_info = get_model_size_info(model_name)
    return size_info.get("disk", 8.0)


def _find_kv_cache_gb_per_1k(model_name: str) -> float:
    """Estimate KV cache footprint per 1 024 tokens in GB."""
    if model_name in KV_CACHE_PER_1K_TOKENS_GB:
        return KV_CACHE_PER_1K_TOKENS_GB[model_name]
    for key, val in KV_CACHE_PER_1K_TOKENS_GB.items():
        if model_name.startswith(key[:12]):
            return val
    # Unknown — use a safe default
    return 0.20


def calc_remaining_vram(gpu_vram_gb: float, chat_model: str) -> dict[str, Any]:
    """Calculate how much VRAM is left after loading *chat_model*.

    Args:
        gpu_vram_gb: Total GPU VRAM in GB.
        chat_model: Model tag (e.g. ``qwen2.5vl:14b``).

    Returns:
        dict with keys: total_gb, model_gb, overhead_gb, remaining_gb, detail
    """
    model_gb = _find_model_vram(chat_model)

    overhead_gb = OLLAMA_OVERHEAD_GB + SAFETY_MARGIN_GB
    # Note: VL model peak already includes vision compute buffers in MODEL_VRAM_GB,
    # so no additional VL_ENCODER_MARGIN is needed here.

    remaining_gb = gpu_vram_gb - model_gb - overhead_gb

    return {
        "total_gb": gpu_vram_gb,
        "model_gb": round(model_gb, 1),
        "overhead_gb": round(overhead_gb, 1),
        "remaining_gb": round(max(remaining_gb, 0), 1),
        "detail": (
            f"{gpu_vram_gb} GB VRAM | model ~{model_gb:.1f} GB"
            f" | overhead ~{overhead_gb:.1f} GB"
            f" | free ~{max(remaining_gb, 0):.1f} GB"
        ),
    }


def recommend_num_ctx(gpu_vram_gb: float, chat_model: str) -> int:
    """Recommend a safe ``num_ctx`` (context window) for *chat_model*.

    Ollama pre-allocates KV cache for the full context window, so this
    value directly determines VRAM usage.  Clamped to common tiers.

    Returns:
        Recommended ``num_ctx`` (0 = Ollama default 2048).
    """
    vram = calc_remaining_vram(gpu_vram_gb, chat_model)
    remaining_gb = vram["remaining_gb"]
    kv_per_1k = _find_kv_cache_gb_per_1k(chat_model)

    if kv_per_1k <= 0 or remaining_gb <= 0:
        return 512

    max_1k_blocks = int(remaining_gb / kv_per_1k)
    max_tokens = max_1k_blocks * 1024

    # Clamp to reasonable tiers (large values for high-end cards)
    for tier in (32768, 16384, 8192, 4096, 2048, 1024, 512, 256):
        if max_tokens >= tier:
            return tier
    return 256


# ===================================================================
# Download
# ===================================================================


def pull_model(
    model_name: str,
    on_progress: Optional[callable] = None,
    timeout: int = 1800,
) -> dict[str, Any]:
    """Pull an Ollama model, optionally showing progress.

    Args:
        model_name: Full model tag (e.g. ``qwen2.5:7b``).
        on_progress: Optional callback ``(model, status_line)`` called
            on each status line from the pull.
        timeout: Max seconds to wait for the pull to complete.

    Returns:
        dict with keys: ok, name, detail, error
    """
    logger.info("Pulling model: %s", model_name)

    try:
        # Run `ollama pull` which shows a progress spinner in the terminal
        process = subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        last_line = ""
        start = time.time()
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            line = line.strip()
            if line:
                last_line = line
                if on_progress:
                    on_progress(model_name, line)

            if time.time() - start > timeout:
                process.kill()
                return {
                    "ok": False,
                    "name": model_name,
                    "detail": "",
                    "error": f"Download timed out after {timeout}s",
                }

        process.wait()

        if process.returncode == 0:
            # Verify it was pulled
            available = ollama_mod.list_models()
            pulled = any(m["name"] == model_name for m in available)
            return {
                "ok": pulled,
                "name": model_name,
                "detail": f"Downloaded {model_name}" if pulled else "Model not found after pull",
                "error": "" if pulled else "Ollama reports model missing after pull",
            }
        else:
            return {
                "ok": False,
                "name": model_name,
                "detail": "",
                "error": f"ollama pull returned exit code {process.returncode}",
            }

    except FileNotFoundError:
        return {
            "ok": False,
            "name": model_name,
            "detail": "",
            "error": "Ollama binary not found. Install Ollama first.",
        }
    except Exception as e:
        return {
            "ok": False,
            "name": model_name,
            "detail": "",
            "error": str(e),
        }


# ===================================================================
# Configuration
# ===================================================================


def write_config(
    chat_model: str,
    vision_model: Optional[str] = None,
    embed_model: str = "nomic-embed-text",
    server_port: int = 5000,
    gpu_vram_gb: float = 0,
) -> dict[str, Any]:
    """Write the selected models into ``config/agent_llm_config.json``.

    Creates the config directory if it doesn't exist.

    When *gpu_vram_gb* is > 0, the ``num_ctx`` (context window) is
    auto-tuned to the largest safe value for the available VRAM.
    """
    num_ctx = 4096   # default context window
    max_tokens = 2048  # max output tokens (doesn't affect KV cache pre-allocation)
    vram_report = ""
    if gpu_vram_gb > 0:
        vram = calc_remaining_vram(gpu_vram_gb, chat_model)
        num_ctx = recommend_num_ctx(gpu_vram_gb, chat_model)
        vram_report = f" | {vram['detail']} → num_ctx={num_ctx}"

    # keep_alive: pin the chat model in VRAM (-1) only when there is no
    # separate vision model or the card is large enough to hold both.
    # On tight cards (<16 GB) with a separate vision model, use a finite
    # keep_alive so Ollama can swap the chat model out to load the vision
    # model when VRAM is tight; otherwise pin it resident (-1).
    if vision_model and 0 < gpu_vram_gb < 16:
        keep_alive = 300
    else:
        keep_alive = -1

    config = {
        "llm": {
            "provider": "ollama",
            "model": chat_model,
            "vision_model": vision_model,
            "base_url": "http://localhost:11434",
            "temperature": 0.7,
            "top_p": 0.9,
            "num_ctx": num_ctx,
            "max_tokens": max_tokens,
            "timeout": 600,
            "keep_alive": keep_alive,
        },
        "agent": {
            "system_prompt": "你是一个智能助手，基于本地大模型运行。你可以帮助用户解答问题、提供信息和完成各种任务。请用中文回答用户的问题，保持友好和专业的态度。",
            "max_history": 40,
            "enable_tools": True,
        },
        "server": {
            "host": "0.0.0.0",
            "port": server_port,
        },
        "business": {
            "enabled": False,
            "base_url": "",
            "timeout": 8,
            "auth": {"scheme": "bearer", "token_env": "STORE_API_TOKEN"},
            "endpoints": {
                "stock": "/stock/{code}",
                "order": "/orders/{order_id}",
                "products": "/products",
            },
        },
    }

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    detail = f"model={chat_model}"
    if vision_model:
        detail += f", vision={vision_model}"
    detail += f", num_ctx={num_ctx}, keep_alive={keep_alive}{vram_report}"
    return {"ok": True, "detail": detail, "path": str(CONFIG_FILE)}
