"""Ollama installation, service management, and health checks.

Supports Ubuntu (apt) and macOS (brew).  Falls back to the official
``curl -fsSL https://ollama.com/install.sh | sh`` script for other
Linux distros.
"""
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default Ollama endpoint
OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


# ===================================================================
# Installation
# ===================================================================


def is_ollama_installed() -> bool:
    """Check whether the ``ollama`` binary is on PATH."""
    return bool(shutil_which("ollama"))


def shutil_which(name: str) -> Optional[str]:
    """Thin wrapper around ``shutil.which``."""
    import shutil
    return shutil.which(name)


def install_ollama(dry_run: bool = False) -> dict[str, Any]:
    """Install Ollama using the platform-appropriate method.

    Returns:
        dict with keys: ok, method, detail, error
    """
    if is_ollama_installed():
        return {"ok": True, "method": "already_installed", "detail": "Ollama is already installed", "error": ""}

    system = sys.platform
    detail = ""
    error = ""

    try:
        if system == "linux":
            # Detect if apt is available (Ubuntu/Debian)
            if shutil_which("apt-get"):
                if dry_run:
                    detail = "Would install Ollama via official script"
                else:
                    # The official install script handles Ubuntu/Debian properly
                    _run(["curl", "-fsSL", "https://ollama.com/install.sh"])
                    detail = "Ollama installed via official script"
            else:
                if dry_run:
                    detail = "Would install Ollama via official script (non-apt Linux)"
                else:
                    _run(["curl", "-fsSL", "https://ollama.com/install.sh"])
                    detail = "Ollama installed via official script"
        elif system == "darwin":
            if shutil_which("brew"):
                if dry_run:
                    detail = "Would run: brew install ollama"
                else:
                    _run(["brew", "install", "ollama"])
                    detail = "Ollama installed via Homebrew"
            else:
                if dry_run:
                    detail = "Would install via official script"
                else:
                    _run(["curl", "-fsSL", "https://ollama.com/install.sh"])
                    detail = "Ollama installed via official script"
        else:
            return {
                "ok": False,
                "method": "unsupported",
                "detail": "",
                "error": f"Unsupported platform: {system}. Visit https://ollama.com/download",
            }

        return {"ok": True, "method": "install", "detail": detail, "error": ""}

    except Exception as e:
        error = str(e)
        return {"ok": False, "method": "failed", "detail": detail, "error": error}


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a command with real-time output and capture error."""
    # For curl-to-sh, we pipe to sh
    if cmd == ["curl", "-fsSL", "https://ollama.com/install.sh"]:
        logger.info("Downloading Ollama install script...")
        import requests
        resp = requests.get("https://ollama.com/install.sh", timeout=30)
        resp.raise_for_status()
        # Execute the script via sh
        proc = subprocess.run(
            ["sh"],
            input=resp.text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Install script failed: {proc.stderr[:500]}")
        return proc
    else:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ===================================================================
# Service management
# ===================================================================


def start_ollama(wait_seconds: int = 15) -> dict[str, Any]:
    """Start the Ollama service if not already running.

    Returns:
        dict with keys: ok, detail, error
    """
    if is_running():
        return {"ok": True, "detail": "Ollama is already running", "error": ""}

    import subprocess
    try:
        if sys.platform == "linux":
            # Try systemd first, then background process
            if shutil_which("systemctl"):
                subprocess.run(
                    ["sudo", "systemctl", "start", "ollama"],
                    capture_output=True, text=True, timeout=30,
                )
            else:
                # Fallback: background daemon
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        elif sys.platform == "darwin":
            subprocess.run(
                ["brew", "services", "start", "ollama"],
                capture_output=True, text=True, timeout=30,
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Wait for it to be ready
        for _ in range(wait_seconds):
            if is_running():
                return {"ok": True, "detail": "Ollama started successfully", "error": ""}
            time.sleep(1)

        return {"ok": False, "detail": "", "error": f"Ollama did not start within {wait_seconds}s"}

    except Exception as e:
        return {"ok": False, "detail": "", "error": str(e)}


def is_running() -> bool:
    """Check whether the Ollama server is responding."""
    try:
        import requests
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def stop_ollama() -> dict[str, Any]:
    """Stop the Ollama service."""
    try:
        if sys.platform == "linux" and shutil_which("systemctl"):
            subprocess.run(
                ["sudo", "systemctl", "stop", "ollama"],
                capture_output=True, text=True, timeout=30,
            )
        elif sys.platform == "darwin":
            subprocess.run(
                ["brew", "services", "stop", "ollama"],
                capture_output=True, text=True, timeout=30,
            )
        elif sys.platform.startswith("win"):
            subprocess.run(
                ["taskkill", "/F", "/IM", "ollama.exe"],
                capture_output=True, text=True, timeout=30,
            )
        else:
            # No service manager — terminate the background process directly.
            # (Ollama has no HTTP shutdown endpoint.)
            subprocess.run(
                ["pkill", "-f", "ollama serve"],
                capture_output=True, text=True, timeout=30,
            )
        return {"ok": True, "detail": "Ollama stopped", "error": ""}
    except Exception as e:
        return {"ok": False, "detail": "", "error": str(e)}


# ===================================================================
# Systemd service setup (Linux)
# ===================================================================


def ensure_systemd_service() -> dict[str, Any]:
    """Ensure Ollama has a systemd service file and is enabled.

    Returns:
        dict with keys: ok, detail, error
    """
    if sys.platform != "linux":
        return {"ok": True, "detail": "Not on Linux, skipping systemd setup", "error": ""}

    if not shutil_which("systemctl"):
        return {"ok": True, "detail": "systemctl not available, skipping", "error": ""}

    service_path = "/etc/systemd/system/ollama.service"
    service_content = """[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_KEEP_ALIVE=-1"

[Install]
WantedBy=multi-user.target
"""

    try:
        # Check if service already exists
        result = subprocess.run(
            ["systemctl", "is-active", "ollama"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"ok": True, "detail": "Ollama systemd service already active", "error": ""}

        # If a unit file already exists (e.g. installed by the official
        # script), don't overwrite it — just enable and start it.
        if os.path.exists(service_path):
            subprocess.run(["sudo", "systemctl", "enable", "ollama"],
                           capture_output=True, text=True, timeout=10)
            subprocess.run(["sudo", "systemctl", "start", "ollama"],
                           capture_output=True, text=True, timeout=30)
            return {"ok": True, "detail": "Existing Ollama systemd unit enabled and started", "error": ""}

        # Write service file
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".service", delete=False) as f:
            f.write(service_content)
            tmp_path = f.name

        subprocess.run(["sudo", "cp", tmp_path, service_path], check=True, timeout=10)
        os.unlink(tmp_path)

        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True, timeout=10)
        subprocess.run(["sudo", "systemctl", "enable", "ollama"], check=True, timeout=10)
        subprocess.run(["sudo", "systemctl", "start", "ollama"], check=True, timeout=30)

        return {"ok": True, "detail": "Ollama systemd service installed and started", "error": ""}

    except Exception as e:
        return {"ok": False, "detail": "", "error": str(e)}


# ===================================================================
# Utility
# ===================================================================


def get_ollama_version() -> str:
    """Return the installed Ollama version string."""
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception:
        return "Unknown"


def list_models() -> list[dict[str, Any]]:
    """List locally available Ollama models.

    Returns:
        List of dicts with keys: name, size, modified
    """
    try:
        import requests
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "name": m["name"],
                "size": _format_size(m.get("size", 0)),
                "modified": m.get("modified_at", ""),
            }
            for m in data.get("models", [])
        ]
    except Exception:
        return []


def _format_size(size_bytes: int) -> str:
    """Format byte size to human-readable."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
