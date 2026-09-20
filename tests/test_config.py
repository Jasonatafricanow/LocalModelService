import json

import pytest

from src.core import config


def test_default_config_falls_back_to_tracked_example(tmp_path, monkeypatch):
    missing = tmp_path / "agent_llm_config.json"
    example = tmp_path / "agent_llm_config.example.json"
    example.write_text(json.dumps({"llm": {"model": "example-model"}}), encoding="utf-8")
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", str(missing))
    monkeypatch.setattr(config, "EXAMPLE_CONFIG_PATH", str(example))

    assert config.load_config()["llm"]["model"] == "example-model"


def test_explicit_missing_config_still_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        config.load_config(str(tmp_path / "missing.json"))
