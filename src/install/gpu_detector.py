"""GPU auto-detection module.

Detects the installed GPU (NVIDIA or AMD) and recommends appropriate
Ollama model configurations.
"""
import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Known GPU profiles and their recommended models (see CLAUDE_TASK.md).
# Each profile carries a chat model plus a *separate* vision model.
GPU_PROFILES = {
    "rtx 4060": {
        "vram_gb": 8,
        "recommended_model": "qwen2.5:7b",
        "recommended_vision_model": "qwen2.5vl:7b",
    },
    "rx 9070 xt": {
        "vram_gb": 16,
        "recommended_model": "qwen2.5:14b",
        "recommended_vision_model": "qwen2.5vl:7b",
    },
}

# VRAM assumed for an unknown card of each vendor when the actual amount
# cannot be queried.
_DEFAULT_NVIDIA_VRAM_GB = 8
_DEFAULT_AMD_VRAM_GB = 16


def _recommend_by_vram(vram_gb: float) -> tuple[str, Optional[str]]:
    """Map available VRAM to a ``(chat_model, vision_model)`` recommendation."""
    if vram_gb >= 24:
        return "qwen2.5:32b", "qwen2.5vl:7b"
    if vram_gb >= 14:
        return "qwen2.5:14b", "qwen2.5vl:7b"
    if vram_gb >= 8:
        return "qwen2.5:7b", "qwen2.5vl:7b"
    if vram_gb >= 6:
        return "qwen2.5:3b", "qwen2.5vl:3b"
    return "qwen2.5:3b", None


def _parse_vram_mib(value: str) -> float:
    """Convert an ``nvidia-smi`` memory.total value (MiB, no units) to GB."""
    try:
        return round(int(float(value)) / 1024)
    except (ValueError, TypeError):
        return 0.0


def detect_gpu() -> dict:
    """Detect the installed GPU and return recommended configuration.

    Tries ``nvidia-smi`` first, then AMD detection (``rocminfo`` /
    ``lspci``), and falls back to CPU-only mode.

    Returns:
        dict with keys ``type`` (``"nvidia"`` | ``"amd"`` | ``"cpu"``),
        ``name``, ``vram_gb``, ``recommended_model``,
        ``recommended_vision_model`` (| None for CPU).
    """
    nvidia = _detect_nvidia()
    if nvidia is not None:
        return nvidia

    amd = _detect_amd()
    if amd is not None:
        return amd

    logger.info("No supported GPU detected, falling back to CPU mode")
    return {
        "type": "cpu",
        "name": "CPU",
        "vram_gb": 0,
        "recommended_model": "qwen2.5:3b",
        "recommended_vision_model": None,
    }


# ---------------------------------------------------------------------------
# NVIDIA detection
# ---------------------------------------------------------------------------

def _detect_nvidia() -> Optional[dict]:
    """Detect NVIDIA GPU via ``nvidia-smi`` (queries name and total VRAM)."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
        if not lines:
            return None
        parts = [p.strip() for p in lines[0].split(",")]
        gpu_name = parts[0]
        vram_gb = _parse_vram_mib(parts[1]) if len(parts) > 1 else 0.0
        gpu_name_lower = gpu_name.lower()
        logger.info("NVIDIA GPU detected: %s (%.0f GB VRAM)", gpu_name, vram_gb)

        for key, profile in GPU_PROFILES.items():
            if key in gpu_name_lower:
                return {"type": "nvidia", "name": gpu_name, **profile}

        # Unknown NVIDIA card — recommend based on the detected VRAM.
        if vram_gb <= 0:
            vram_gb = _DEFAULT_NVIDIA_VRAM_GB
        chat, vision = _recommend_by_vram(vram_gb)
        logger.info("Unknown NVIDIA GPU '%s' — recommending %s", gpu_name, chat)
        return {
            "type": "nvidia",
            "name": gpu_name,
            "vram_gb": round(vram_gb),
            "recommended_model": chat,
            "recommended_vision_model": vision,
        }

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, IndexError) as e:
        logger.debug("nvidia-smi check failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# AMD detection
# ---------------------------------------------------------------------------

def _detect_amd() -> Optional[dict]:
    """Detect AMD GPU via ``rocminfo`` or ``lspci``."""
    gpu_name = _detect_amd_rocminfo()
    if not gpu_name:
        gpu_name = _detect_amd_lspci()

    if not gpu_name:
        return None

    gpu_name_lower = gpu_name.lower()
    logger.info("AMD GPU detected: %s", gpu_name)

    for key, profile in GPU_PROFILES.items():
        if key in gpu_name_lower:
            return {
                "type": "amd",
                "name": gpu_name,
                **profile,
            }

    # Unknown AMD card — recommend based on VRAM (queried or assumed).
    vram_gb = _detect_amd_vram_gb() or _DEFAULT_AMD_VRAM_GB
    chat, vision = _recommend_by_vram(vram_gb)
    logger.info("Unknown AMD GPU '%s' — recommending %s", gpu_name, chat)
    return {
        "type": "amd",
        "name": gpu_name,
        "vram_gb": round(vram_gb),
        "recommended_model": chat,
        "recommended_vision_model": vision,
    }


def _detect_amd_vram_gb() -> float:
    """Best-effort AMD VRAM detection via ``rocm-smi`` (0.0 if unavailable)."""
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return 0.0
        # Look for a byte/MiB total in the output and convert to GB.
        for line in result.stdout.splitlines():
            lower = line.lower()
            if "total" in lower and ("vram" in lower or "memory" in lower):
                match = re.search(r"(\d+)", line)
                if not match:
                    continue
                value = float(match.group(1))
                # rocm-smi usually reports bytes; fall back to MiB/KiB for
                # smaller magnitudes so the result is always in GB.
                if value >= 1 << 30:
                    return value / (1024 ** 3)
                if value >= 1 << 20:
                    return value / (1024 ** 2)
                return value / 1024
        return 0.0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.debug("rocm-smi vram check failed: %s", e)
        return 0.0


def _detect_amd_rocminfo() -> Optional[str]:
    """Check for AMD GPU using ``rocminfo`` (ROCm stack)."""
    try:
        result = subprocess.run(
            ["rocminfo"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():
            lower = line.lower()
            if "rx 9070" in lower:
                return "RX 9070 XT"
            if "radeon" in lower and "xt" in lower:
                return line.strip()
            # Match "gfxXXXX" agent names
            if "gfx" in lower and "name" in lower:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    return parts[1].strip()
        return None

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.debug("rocminfo check failed: %s", e)
        return None


def _detect_amd_lspci() -> Optional[str]:
    """Check for AMD GPU using ``lspci``."""
    try:
        result = subprocess.run(
            ["lspci"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():
            lower = line.lower()
            if ("amd" in lower or "radeon" in lower) and (
                "vga" in lower or "display" in lower or "gfx" in lower
            ):
                # Extract the device name after the PCI slot
                parts = line.split(":", 2)
                return parts[-1].strip() if len(parts) > 1 else line.strip()
        return None

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.debug("lspci check failed: %s", e)
        return None
