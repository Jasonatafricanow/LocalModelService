import json
import subprocess
import sys
from pathlib import Path


def test_legacy_config_treats_model_as_data(tmp_path):
    installer = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")
    code = installer.split("<<'PYCONFIG'\n", 1)[1].split("\nPYCONFIG", 1)[0]
    (tmp_path / "config").mkdir()
    config = tmp_path / "config/agent_llm_config.json"
    config.write_text('{"llm": {}, "server": {}}', encoding="utf-8")
    model = "model'\n__import__('os').system('unexpected')"
    result = subprocess.run([sys.executable, "-", model, "5000"], input=code, text=True, cwd=tmp_path, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(config.read_text(encoding="utf-8"))["llm"]["model"] == model
    before = config.read_bytes()
    for port in ["0", "65536", "1;print('injected')"]:
        result = subprocess.run([sys.executable, "-", model, port], input=code, text=True, cwd=tmp_path, capture_output=True)
        assert result.returncode != 0
        assert config.read_bytes() == before
