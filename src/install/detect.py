"""System environment detection for OpenClaw installer.

Detects OS, Python version, GPU, RAM, disk space, and running services.
All checks return structured dicts with a ``pass`` key for easy use in
the installer CLI.
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


# ===================================================================
# OS detection
# ===================================================================


def check_os() -> dict[str, Any]:
    """Detect operating system.

    Returns:
        dict with keys: ok, name, version, family, arch, detail
    """
    system = platform.system()
    arch = platform.machine()
    detail = f"{system} {platform.release()} ({arch})"

    result: dict[str, Any] = {
        "name": system,
        "version": platform.release(),
        "family": "",
        "arch": arch,
        "detail": detail,
        "ok": False,
        "error": "",
    }

    if system == "Linux":
        try:
            # Try to get distro info
            with open("/etc/os-release") as f:
                data = f.read()
            for line in data.splitlines():
                if line.startswith("ID="):
                    result["family"] = line.split("=", 1)[1].strip().strip('"')
                if line.startswith("VERSION_ID="):
                    result["version"] = line.split("=", 1)[1].strip().strip('"')
        except FileNotFoundError:
            pass  # keep fallback values

        # Ubuntu / Debian are supported
        if result["family"] in ("ubuntu", "debian"):
            result["ok"] = True
        else:
            result["ok"] = True  # still try, but warn
            result["error"] = f"Installation tested on Ubuntu; detected {result['family']}"

    elif system == "Darwin":
        result["ok"] = True
        result["family"] = "macos"

    elif system == "Windows":
        # Windows Subsystem for Linux detection
        if "microsoft" in platform.uname().release.lower():
            result["ok"] = True
            result["family"] = "wsl"
        else:
            result["ok"] = False
            result["error"] = "Windows is not supported directly. Use WSL2 or a Linux VM."

    return result


def check_python() -> dict[str, Any]:
    """Check Python version (need 3.10+)."""
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return {
        "ok": ok,
        "version": f"{v.major}.{v.minor}.{v.micro}",
        "path": sys.executable,
        "detail": f"Python {v.major}.{v.minor}.{v.micro} ({sys.executable})",
        "error": "" if ok else f"Python 3.10+ required (found {v.major}.{v.minor})",
    }


# ===================================================================
# GPU detection (wraps the existing gpu_detector module)
# ===================================================================


def check_gpu() -> dict[str, Any]:
    """Detect installed GPU.

    Wraps :func:`gpu_detector.detect_gpu` with extra detail.
    """
    # Import here to avoid circular / early-import issues
    import sys as _sys
    from pathlib import Path as _Path

    # Make sure project root is on sys.path so the module can be found
    _root = _Path(__file__).resolve().parent.parent.parent
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))

    from .gpu_detector import detect_gpu

    info = detect_gpu()

    result: dict[str, Any] = {
        "ok": info["type"] != "cpu",
        "type": info["type"],
        "name": info["name"],
        "vram_gb": info["vram_gb"],
        "recommended_model": info["recommended_model"],
        "recommended_vision_model": info["recommended_vision_model"],
        "detail": f"{info['name']} ({info['vram_gb']} GB VRAM)" if info["type"] != "cpu" else "CPU only (no GPU detected)",
    }
    return result


# ===================================================================
# RAM and disk
# ===================================================================


def check_ram() -> dict[str, Any]:
    """Check available RAM.

    Returns dict with total_gb, detail, ok (True if >= 8 GB).
    """
    try:
        if sys.platform == "linux":
            total_gb = 0
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        total_gb = round(kb / (1024 * 1024), 1)
                        break
        elif sys.platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            total_gb = round(int(result.stdout.strip()) / (1024**3), 1)
        else:
            total_gb = 8  # assume minimum for unknown
    except Exception:
        total_gb = 0

    # Minimum RAM for 7B models: ~8 GB, for 14B: ~16 GB
    ok = total_gb >= 8
    return {
        "ok": ok,
        "total_gb": total_gb,
        "detail": f"{total_gb} GB" if total_gb > 0 else "Unknown",
        "error": "" if ok else f"At least 8 GB RAM recommended (found {total_gb} GB)",
    }


def check_disk(path: str | None = None) -> dict[str, Any]:
    """Check available disk space at *path* (default: project root).

    Ollama models can be ~4-16 GB each. Recommend at least 20 GB free.
    """
    target = path or os.getcwd()
    try:
        usage = shutil.disk_usage(target)
        free_gb = round(usage.free / (1024**3), 1)
        ok = free_gb >= 20
        return {
            "ok": ok,
            "free_gb": free_gb,
            "total_gb": round(usage.total / (1024**3), 1),
            "detail": f"{free_gb} GB free",
            "error": "" if ok else f"At least 20 GB free recommended (found {free_gb} GB)",
        }
    except Exception as e:
        return {
            "ok": False,
            "free_gb": 0,
            "total_gb": 0,
            "detail": "Unknown",
            "error": str(e),
        }


# ===================================================================
# Port availability
# ===================================================================


def check_port(port: int = 5000) -> dict[str, Any]:
    """Check if *port* is available."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return {"ok": True, "port": port, "detail": f"Port {port} is available"}
        except OSError:
            return {"ok": False, "port": port, "detail": f"Port {port} is already in use"}


# ===================================================================
# Aggregate check
# ===================================================================


def run_all_checks() -> dict[str, Any]:
    """Run all environment checks and return a summary dict."""
    # Use the project root (where install.py lives) for disk check
    _project_root = str(Path(__file__).resolve().parent.parent.parent)
    results = {
        "os": check_os(),
        "python": check_python(),
        "gpu": check_gpu(),
        "ram": check_ram(),
        "disk": check_disk(_project_root),
        "port": check_port(),
    }
    all_ok = all(r["ok"] for r in results.values())
    return {
        "all_ok": all_ok,
        "checks": results,
    }
