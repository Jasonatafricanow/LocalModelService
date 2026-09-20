#!/usr/bin/env python3
"""OpenClaw — 一键安装入口

一行命令完成：环境检测 → Ollama 安装 → GPU 识别 → 推荐模型 → 下载 → 配置 → 启动

用法:
    python install.py              # 交互式安装（推荐）
    python install.py --non-interactive   # 全自动安装
    python install.py --skip-download     # 仅检测环境，不下载模型
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.install.cli import main

if __name__ == "__main__":
    sys.exit(main())
