"""Tests for src/install — environment detection, GPU detection, VRAM calc.

Run with::

    python -m pytest tests/test_install.py -v
"""
from pathlib import Path

# Ensure project root is importable
_root = Path(__file__).resolve().parent.parent
import sys
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.install import detect
from src.install import gpu_detector
from src.install import models as models_mod


# ===================================================================
# System detection
# ===================================================================


class TestDetectOS:
    def test_check_os_returns_dict(self):
        result = detect.check_os()
        assert isinstance(result, dict)
        assert "name" in result
        assert "ok" in result

    def test_check_os_linux_or_windows(self):
        """Any platform should return a valid result (even if not ok)."""
        result = detect.check_os()
        assert result["name"] in ("Linux", "Darwin", "Windows", "Java")
        assert result["detail"]


class TestDetectPython:
    def test_check_python_ok(self):
        result = detect.check_python()
        assert result["ok"] is True
        assert result["version"].startswith("3.")
        assert result["path"]


class TestDetectPort:
    def test_check_port_available_or_not(self):
        """Port 19999 is unlikely to be in use on CI/dev machines."""
        result = detect.check_port(19999)
        # It might be in use, but should always have a valid structure
        assert "ok" in result
        assert "port" in result
        assert "detail" in result


class TestDetectDisk:
    def test_check_disk_returns_dict(self):
        result = detect.check_disk()
        assert isinstance(result, dict)
        assert "ok" in result
        assert "free_gb" in result
        assert result["free_gb"] > 0  # must have some free space


class TestDetectRam:
    def test_check_ram_returns_dict(self):
        result = detect.check_ram()
        assert "ok" in result
        assert "total_gb" in result
        if result["total_gb"] > 0:
            assert result["total_gb"] >= 0.5  # at least 512 MB


class TestRunAllChecks:
    def test_run_all_checks_structure(self):
        result = detect.run_all_checks()
        assert "all_ok" in result
        assert "checks" in result
        keys = {"os", "python", "gpu", "ram", "disk", "port"}
        assert keys.issubset(result["checks"].keys())

    def test_run_all_checks_non_critical_fields(self):
        """Even if GPU is CPU, other checks must have their detail fields."""
        result = detect.run_all_checks()
        for key, check in result["checks"].items():
            assert "detail" in check, f"{key} missing detail"
            assert "ok" in check, f"{key} missing ok"


# ===================================================================
# GPU detector
# ===================================================================


class TestGpuDetector:
    def test_detect_gpu_returns_dict(self):
        info = gpu_detector.detect_gpu()
        assert isinstance(info, dict)
        assert "type" in info
        assert "name" in info
        assert "vram_gb" in info
        assert "recommended_model" in info
        assert info["type"] in ("nvidia", "amd", "cpu")

    def test_detect_gpu_cpu_fallback(self):
        """On a machine without a supported GPU, it should return CPU mode."""
        info = gpu_detector.detect_gpu()
        if info["type"] == "cpu":
            assert info["vram_gb"] == 0
            assert info["recommended_model"] == "qwen2.5:3b"

    def test_gpu_profiles_defined(self):
        assert len(gpu_detector.GPU_PROFILES) >= 2
        assert "rtx 4060" in gpu_detector.GPU_PROFILES
        assert "rx 9070 xt" in gpu_detector.GPU_PROFILES


# ===================================================================
# Model recommendations
# ===================================================================


class TestModelRecommendations:
    def test_get_recommendation_returns_keys(self):
        gpu_info = gpu_detector.detect_gpu()
        rec = models_mod.get_recommendation_from_gpu(gpu_info)
        expected = {"tier", "label", "chat", "vision", "embed", "note", "alternatives"}
        assert expected.issubset(rec.keys())

    def test_recommendation_model_matches_gpu_info(self):
        gpu_info = gpu_detector.detect_gpu()
        rec = models_mod.get_recommendation_from_gpu(gpu_info)
        assert rec["chat"] == gpu_info["recommended_model"]

    def test_recommendation_cpu_tier(self):
        """On CPU, tier should be 'cpu'."""
        info = {"type": "cpu", "name": "CPU", "vram_gb": 0,
                "recommended_model": "qwen2.5:3b", "recommended_vision_model": None}
        rec = models_mod.get_recommendation_from_gpu(info)
        assert rec["tier"] == "cpu"
        assert rec["chat"] == "qwen2.5:3b"

    def test_recommendation_8gb_nvidia(self):
        info = {"type": "nvidia", "name": "RTX 4060", "vram_gb": 8,
                "recommended_model": "qwen2.5:7b", "recommended_vision_model": "qwen2.5vl:7b"}
        rec = models_mod.get_recommendation_from_gpu(info)
        assert rec["tier"] == "nvidia_8gb"
        assert rec["chat"] == "qwen2.5:7b"
        assert rec["vision"] == "qwen2.5vl:7b"

    def test_recommendation_16gb_nvidia(self):
        info = {"type": "nvidia", "name": "RTX 4070", "vram_gb": 16,
                "recommended_model": "qwen2.5:14b", "recommended_vision_model": "qwen2.5vl:7b"}
        rec = models_mod.get_recommendation_from_gpu(info)
        assert rec["tier"] == "nvidia_16gb"
        assert rec["chat"] == "qwen2.5:14b"
        assert rec["vision"] == "qwen2.5vl:7b"

    def test_recommendation_24gb_high(self):
        info = {"type": "nvidia", "name": "RTX 4090", "vram_gb": 24,
                "recommended_model": "qwen2.5:32b", "recommended_vision_model": "qwen2.5vl:7b"}
        rec = models_mod.get_recommendation_from_gpu(info)
        assert rec["tier"] == "high"
        assert rec["chat"] == "qwen2.5:32b"

    def test_recommendation_amd(self):
        info = {"type": "amd", "name": "RX 9070 XT", "vram_gb": 16,
                "recommended_model": "qwen2.5:14b", "recommended_vision_model": "qwen2.5vl:7b"}
        rec = models_mod.get_recommendation_from_gpu(info)
        assert rec["tier"] == "amd_16gb"


# ===================================================================
# VRAM calculation
# ===================================================================


class TestModelSizeInfo:
    def test_known_model(self):
        info = models_mod.get_model_size_info("qwen2.5vl:3b")
        assert info["params"] == "3B (VL)"
        assert info["ram_min"] > 0

    def test_unknown_model_returns_fallback(self):
        info = models_mod.get_model_size_info("some:unknown")
        assert isinstance(info, dict)
        assert "params" in info


class TestFindModelVram:
    def test_known_vram(self):
        vram = models_mod._find_model_vram("qwen2.5vl:3b")
        assert vram > 0
        assert vram < 20  # sanity check

    def test_vl_3b_on_8gb(self):
        vram = models_mod._find_model_vram("qwen2.5vl:3b")
        assert 3.0 <= vram <= 5.0  # should be ~4.0 GB


class TestCalcRemainingVRAM:
    def test_8gb_plus_vl3b(self):
        v = models_mod.calc_remaining_vram(8.0, "qwen2.5vl:3b")
        assert v["total_gb"] == 8.0
        assert v["model_gb"] > 0
        assert v["remaining_gb"] > 2.0  # should be ~3.4 GB

    def test_16gb_plus_vl14b(self):
        v = models_mod.calc_remaining_vram(16.0, "qwen2.5vl:14b")
        assert v["total_gb"] == 16.0
        assert v["remaining_gb"] > 2.0

    def test_8gb_plus_vl7b_is_full(self):
        """qwen2.5vl:7b on 8 GB should leave almost no room."""
        v = models_mod.calc_remaining_vram(8.0, "qwen2.5vl:7b")
        assert v["remaining_gb"] < 1.0  # nearly full

    def test_negative_vram_clamped(self):
        """If model exceeds VRAM, remaining should be 0, not negative."""
        v = models_mod.calc_remaining_vram(2.0, "qwen2.5vl:14b")
        assert v["remaining_gb"] == 0.0


class TestRecommendNumCtx:
    def test_8gb_plus_vl3b_8192(self):
        ctx = models_mod.recommend_num_ctx(8.0, "qwen2.5vl:3b")
        assert ctx >= 8192

    def test_16gb_plus_vl14b_8192_or_more(self):
        ctx = models_mod.recommend_num_ctx(16.0, "qwen2.5vl:14b")
        assert ctx >= 8192

    def test_2gb_plus_vl14b_minimum(self):
        """Insufficient VRAM should return 512."""
        ctx = models_mod.recommend_num_ctx(2.0, "qwen2.5vl:14b")
        assert ctx == 512


# ===================================================================
# Config writing
# ===================================================================


class TestWriteConfig:
    def test_write_config_with_vram(self, tmp_path):
        """write_config should accept gpu_vram_gb and produce num_ctx."""
        import tempfile, os, json
        from src.install.models import _PROJECT_ROOT, CONFIG_FILE

        # Temporarily swap config path to temp dir
        orig_root = models_mod._PROJECT_ROOT
        orig_cfg = models_mod.CONFIG_FILE
        tmp_root = tmp_path / "project"
        tmp_root.mkdir()
        models_mod._PROJECT_ROOT = tmp_root
        models_mod.CONFIG_FILE = tmp_root / "config" / "agent_llm_config.json"

        try:
            result = models_mod.write_config(
                chat_model="qwen2.5vl:3b",
                gpu_vram_gb=8.0,
            )
            assert result["ok"] is True
            assert "num_ctx" in result["detail"] or "model" in result["detail"]

            # Verify written file
            assert models_mod.CONFIG_FILE.exists()
            with open(models_mod.CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            assert cfg["llm"]["model"] == "qwen2.5vl:3b"
            assert cfg["llm"]["num_ctx"] >= 8192
            assert cfg["llm"]["max_tokens"] == 2048
        finally:
            models_mod._PROJECT_ROOT = orig_root
            models_mod.CONFIG_FILE = orig_cfg

    def test_write_config_default_no_vram(self, tmp_path):
        """Without VRAM info, num_ctx should be default 4096."""
        import json
        orig_root = models_mod._PROJECT_ROOT
        orig_cfg = models_mod.CONFIG_FILE
        tmp_root = tmp_path / "project2"
        tmp_root.mkdir()
        models_mod._PROJECT_ROOT = tmp_root
        models_mod.CONFIG_FILE = tmp_root / "config" / "agent_llm_config.json"

        try:
            result = models_mod.write_config(chat_model="qwen2.5:3b")
            assert result["ok"] is True
            with open(models_mod.CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            assert cfg["llm"]["num_ctx"] == 4096
            assert cfg["llm"]["max_tokens"] == 2048
        finally:
            models_mod._PROJECT_ROOT = orig_root
            models_mod.CONFIG_FILE = orig_cfg
