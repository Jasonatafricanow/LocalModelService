#!/bin/bash
# OpenClaw — 一键安装入口 (Shell wrapper)
#
# Delegates to the Python installer for full environment detection,
# GPU-based model recommendation, and interactive setup.
#
# Fallback: if Python 3 is not available, runs the legacy bash-based
# installation flow.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${1:-qwen2.5}"
PORT="${2:-5000}"

# ── Try the Python installer first ──
if command -v python3 &>/dev/null; then
    python3 --version 2>/dev/null | grep -qE '3\.(1[0-9]|[2-9][0-9])' && {
        echo "→ 使用 Python 交互式安装向导"
        # Forward all args as-is; install.py accepts optional positional
        # [model] [port] plus --port/--non-interactive/--skip-download.
        python3 "$SCRIPT_DIR/install.py" "$@"
        exit $?
    }
fi

# Validate before the legacy installer performs any side effects.
if [[ ! "$PORT" =~ ^[0-9]{1,5}$ ]] || (( 10#$PORT < 1 || 10#$PORT > 65535 )); then
    echo "Invalid port: expected an integer from 1 to 65535" >&2
    exit 2
fi

# ── Legacy bash fallback ──
echo "Python 3.10+ 未安装 — 使用 legacy bash 安装流程"
echo ""

function step { echo -e "\n[step $1/$2] $3"; }

step 1 4 "安装 Python 依赖"
pip3 install --user -r "$SCRIPT_DIR/requirements.txt" 2>&1 | grep -E "(Successfully|already|ERROR)" || true

step 2 4 "安装 / 启动 Ollama"
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    ollama serve &>/dev/null &
    sleep 3
fi

step 3 4 "下载模型 $MODEL"
if ! ollama list 2>/dev/null | grep -q "$MODEL"; then
    ollama pull "$MODEL"
fi

step 4 4 "写入配置"
cd "$SCRIPT_DIR"
python3 - "$MODEL" "$PORT" <<'PYCONFIG'
import json
import sys
from pathlib import Path
model, port = sys.argv[1:]
port = int(port)
if not 1 <= port <= 65535:
    raise ValueError('Invalid port')
path = Path('config/agent_llm_config.json')
cfg = json.loads(path.read_text(encoding='utf-8'))
cfg['llm']['model'] = model
cfg['server']['port'] = port
path.write_text(json.dumps(cfg, indent=4, ensure_ascii=False), encoding='utf-8')
PYCONFIG

echo ""
echo "========================================"
echo "  部署完成"
echo "========================================"
echo ""
echo "  启动服务器: cd \"$SCRIPT_DIR\" && python3 src/main.py"
echo "  服务地址:   http://localhost:$PORT"
echo ""
