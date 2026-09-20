"""OpenClaw Interactive Installer CLI.

One-command setup::

    python install.py

Detects your hardware, recommends models, installs Ollama, downloads
the selected models, and configures the server.
"""
import argparse
import os
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so all imports work
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.install import detect as detect_mod
from src.install import ollama as ollama_mod
from src.install import models as models_mod

# Set by main() from --non-interactive; when True, confirm()/choose()
# return their defaults instead of prompting (true unattended install).
NON_INTERACTIVE = False


# ===================================================================
# Terminal helpers (no external deps)
# ===================================================================

def _color(code: int, text: str) -> str:
    """Wrap text in an ANSI color code."""
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def green(text: str) -> str:
    return _color(32, text)


def yellow(text: str) -> str:
    return _color(33, text)


def red(text: str) -> str:
    return _color(31, text)


def cyan(text: str) -> str:
    return _color(36, text)


def bold(text: str) -> str:
    return _color(1, text)


def banner() -> None:
    print()
    print(bold("=" * 56))
    print(bold("   OpenClaw — 一键安装向导"))
    print(bold("   基于 Ollama 的本地智能 Agent 服务"))
    print(bold("=" * 56))
    print()
    print("  本向导将自动完成：")
    print("  " + green("•") + " 系统环境检测")
    print("  " + green("•") + " GPU 检测与模型推荐")
    print("  " + green("•") + " Ollama 安装（如未安装）")
    print("  " + green("•") + " 模型下载")
    print("  " + green("•") + " 服务配置与启动")
    print()


def confirm(prompt: str, default: bool = True) -> bool:
    """Ask the user a yes/no question."""
    if NON_INTERACTIVE:
        return default
    hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"  {bold('?')} {prompt} [{hint}] ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print(f"  {yellow('请输入 y 或 n')}")


def choose(title: str, options: list[tuple[str, str]], default: int = 0) -> int:
    """Show a numbered menu and let the user pick one.

    Args:
        title: Section header shown before the options.
        options: List of (label, description) pairs.
        default: 0-based index of the default choice.

    Returns:
        0-based index of the chosen option.
    """
    if NON_INTERACTIVE:
        return default
    print(f"\n  {bold(title)}")
    print()
    for i, (label, desc) in enumerate(options):
        marker = green("▸") if i == default else " "
        print(f"  {marker} [{i + 1}] {label}")
        if desc:
            print(f"       {yellow(desc)}")
    print()

    while True:
        raw = input(f"  请输入编号 [1-{len(options)}] (默认 {default + 1}): ").strip()
        if not raw:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print(f"  {red(f'请输入 1-{len(options)} 之间的数字')}")


def step_header(num: int, total: int, label: str) -> None:
    """Print a step header."""
    print()
    print(bold(f"  [{num}/{total}] {label}"))
    print("-" * 40)


def step_ok(text: str) -> None:
    print(f"  {green('✓')} {text}")


def step_warn(text: str) -> None:
    print(f"  {yellow('⚠')} {text}")


def step_fail(text: str) -> None:
    print(f"  {red('✗')} {text}")


# ===================================================================
# Installation steps
# ===================================================================

TOTAL_STEPS = 8


def step_environment() -> bool:
    """Step 1: Check system environment."""
    step_header(1, TOTAL_STEPS, "系统环境检测")

    results = detect_mod.run_all_checks()
    checks = results["checks"]

    for key, check in checks.items():
        label = {
            "os": "操作系统",
            "python": "Python 版本",
            "gpu": "GPU 检测",
            "ram": "内存",
            "disk": "磁盘空间",
            "port": "端口 5000",
        }.get(key, key)

        if check["ok"]:
            step_ok(f"{label}: {check['detail']}")
        else:
            step_fail(f"{label}: {check['detail']}")
            if check.get("error"):
                print(f"         {red(check['error'])}")

    if not results["all_ok"]:
        os_check = checks.get("os", {})
        if not os_check.get("ok"):
            print()
            print(f"  {red('环境检测未通过 — 操作系统不支持')}")
            print(f"  {yellow('提示: 请使用 Ubuntu 20.04+ 或 Debian 11+ 系统')}")
            return False

        gpu = checks.get("gpu", {})
        if gpu.get("type") == "cpu":
            step_warn("未检测到 GPU，将使用 CPU 模式（推荐 qwen2.5:3b）")
            return True

        print()
        print(f"  {red('环境检测未通过，请修复上述问题后重试')}")
        return False

    return True


def step_python_deps() -> bool:
    """Step 2: Install Python dependencies from requirements.txt."""
    step_header(2, TOTAL_STEPS, "Python 依赖安装")

    req_path = _PROJECT_ROOT / "requirements.txt"
    if not req_path.exists():
        step_warn(f"未找到 {req_path}，跳过依赖安装")
        return True

    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "-r", str(req_path)],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode == 0:
            step_ok("Python 依赖安装完成")
        else:
            # Show only the last few lines of output
            lines = proc.stdout.strip().splitlines()[-5:]
            for line in lines:
                if line.strip():
                    print(f"    {line}")
            if "already satisfied" in proc.stdout:
                step_ok("Python 依赖已安装")
            else:
                step_warn(f"pip 返回代码 {proc.returncode}，部分依赖可能未安装")
        return True
    except Exception as e:
        step_fail(f"依赖安装失败: {e}")
        return False


def step_ollama_install() -> bool:
    """Step 3: Install / verify Ollama."""
    step_header(3, TOTAL_STEPS, "Ollama 安装")

    if ollama_mod.is_ollama_installed():
        version = ollama_mod.get_ollama_version()
        step_ok(f"Ollama 已安装: {version}")
        return True

    print(f"  {yellow('Ollama 未安装，正在下载安装...')}")
    result = ollama_mod.install_ollama()
    if result["ok"]:
        step_ok(result["detail"])
    else:
        step_fail(result.get("error", "安装失败"))
        return False

    return True


def step_ollama_start() -> bool:
    """Step 4: Start Ollama service."""
    step_header(4, TOTAL_STEPS, "Ollama 服务启动")

    if ollama_mod.is_running():
        step_ok("Ollama 服务运行中")
        return True

    print(f"  {yellow('正在启动 Ollama...')}")
    result = ollama_mod.start_ollama(wait_seconds=15)
    if result["ok"]:
        step_ok(result["detail"])
    else:
        step_fail(result.get("error", "启动失败"))
        # Try to set up systemd service on Linux
        if sys.platform == "linux":
            print("  " + yellow("尝试配置 systemd 服务..."))
            svc = ollama_mod.ensure_systemd_service()
            if svc["ok"]:
                step_ok(svc["detail"])
                return True
            step_fail(svc.get("error", "systemd 配置失败"))

        print(f"  {yellow('提示: 可手动运行 ollama serve 启动')}")
        return False

    return True


def step_gpu_detection() -> dict | None:
    """Step 5: GPU detection and model recommendation."""
    step_header(5, TOTAL_STEPS, "GPU 检测与模型推荐")

    gpu_info = detect_mod.check_gpu()
    if gpu_info["ok"]:
        step_ok(f"检测到 GPU: {gpu_info['detail']}")
    else:
        step_warn(f"GPU 状态: {gpu_info['detail']}")

    recommendation = models_mod.get_recommendation_from_gpu(gpu_info)
    print()
    print(f"  推荐方案: {bold(recommendation['label'])}")
    print(f"  聊天模型: {cyan(recommendation['chat'])}")
    if recommendation.get("vision"):
        print(f"  视觉模型: {cyan(recommendation['vision'])}")
    print(f"  嵌入模型: {cyan(recommendation['embed'])}")
    if recommendation.get("note"):
        print(f"  {yellow('提示:')} {recommendation['note']}")
    print()

    return recommendation


def step_model_selection(recommendation: dict) -> list[str]:
    """Step 6: Let user select which models to download."""
    step_header(6, TOTAL_STEPS, "模型选择")

    # Build the model list
    chat_model = recommendation["chat"]
    vision_model = recommendation.get("vision")
    embed_model = recommendation.get("embed", "nomic-embed-text")

    # Each menu option maps to a concrete list of models so the chosen
    # index always downloads exactly what the label promises.
    options: list[tuple[str, str]] = []
    option_models: list[list[str]] = []

    # 0: chat only
    options.append((
        f"{chat_model} (仅聊天)",
        models_mod.get_model_size_info(chat_model).get("params", "?"),
    ))
    option_models.append([chat_model])

    # 1: chat + vision (when a separate vision model is recommended)
    if vision_model:
        options.append((
            f"{chat_model} + {vision_model} (聊天 + 视觉)",
            "推荐用于 WhatsApp 图片识别",
        ))
        option_models.append([chat_model, vision_model])

    # 2+: alternative tiers, each with concrete model names
    for alt in recommendation.get("alternatives", []):
        alt_chat = alt.get("chat")
        if not alt_chat:
            continue
        alt_models = [alt_chat]
        if alt.get("vision"):
            alt_models.append(alt["vision"])
        options.append((
            f"{alt['label']}: " + " + ".join(alt_models),
            alt.get("note", ""),
        ))
        option_models.append(alt_models)

    choice = choose("请选择要下载的模型组合：", options, default=0)

    selected = list(option_models[choice])

    # Always include the embedding model
    if embed_model and embed_model not in selected:
        selected.append(embed_model)

    print()
    for m in selected:
        size_info = models_mod.get_model_size_info(m)
        print(f"  {green('▸')} {m} ({size_info.get('params', '?')}, ~{size_info.get('disk', '?')} GB)")
    print()

    if confirm("确认下载以上模型？", default=True):
        return selected
    else:
        print(f"  {yellow('已取消')}")
        return []


def step_download(models: list[str]) -> bool:
    """Step 7: Download selected models."""
    step_header(7, TOTAL_STEPS, "下载模型")

    if not models:
        step_warn("未选择模型，跳过下载")
        return True

    all_ok = True
    for model_name in models:
        print()
        print(f"  正在下载 {cyan(model_name)} ...")

        # Check if already available
        available = ollama_mod.list_models()
        if any(m["name"] == model_name for m in available):
            step_ok(f"{model_name} 已存在")
            continue

        # Custom progress callback
        def on_progress(name, line):
            # Only print non-spinner lines
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("\r"):
                print(f"    {cleaned[:100]}")

        result = models_mod.pull_model(model_name, on_progress=on_progress)

        if result["ok"]:
            step_ok(f"{model_name} 下载完成")
        else:
            step_fail(f"{model_name} 下载失败: {result['error']}")
            all_ok = False

    return all_ok


def step_configure(
    models: list[str],
    gpu_vram_gb: float = 0,
    server_port: int = 5000,
    non_interactive: bool = False,
) -> bool:
    """Step 8: Write configuration and start server."""
    step_header(8, TOTAL_STEPS, "配置与启动")

    if not models:
        step_warn("跳过配置")
        return True

    # Pick the chat model (first non-embedding, non-vision model) and the
    # vision model (first model tagged with "vl") from the selected set.
    embed_model = "nomic-embed-text"
    non_embed = [m for m in models if m != embed_model]
    vision_models = [m for m in non_embed if "vl" in m]
    chat_candidates = [m for m in non_embed if "vl" not in m]
    chat_model = chat_candidates[0] if chat_candidates else (
        non_embed[0] if non_embed else "qwen2.5:7b"
    )
    vision_model = vision_models[0] if vision_models else None

    result = models_mod.write_config(
        chat_model=chat_model,
        vision_model=vision_model,
        embed_model=embed_model,
        server_port=server_port,
        gpu_vram_gb=gpu_vram_gb,
    )
    if result["ok"]:
        step_ok(result["detail"])
    else:
        step_fail(result.get("error", "配置写入失败"))
        return False

    # Show completion
    print()
    print(bold(green("=" * 56)))
    print(bold(green("   安装完成！")))
    print(bold(green("=" * 56)))
    print()
    print(f"  {green('▸')} 启动服务器:")
    print(f"     python src/main.py")
    print()
    print(f"  {green('▸')} 测试:")
    print(f"     curl http://localhost:{server_port}/health")
    print(f"     curl -X POST http://localhost:{server_port}/chat \\")
    print(f"       -H 'Content-Type: application/json' \\")
    print(f"       -d '{{\"message\": \"你好\"}}'")
    print()
    print(f"  {green('▸')} 查看工具列表:")
    print(f"     curl http://localhost:{server_port}/tools")
    print()

    # In non-interactive mode, don't spawn a background server unattended —
    # just print the command.
    if non_interactive:
        print(f"  {yellow('非交互模式：请手动运行 python src/main.py 启动服务器')}")
    elif confirm("立即启动服务器？", default=True):
        import subprocess
        try:
            subprocess.Popen(
                [sys.executable, str(_PROJECT_ROOT / "src" / "main.py")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"  {green('✓')} 服务器已在后台启动 (http://localhost:{server_port})")
        except Exception as e:
            print(f"  {yellow(f'启动失败: {e}')}")
            print(f"  {yellow('请手动运行: python src/main.py')}")

    return True


# ===================================================================
# Main
# ===================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OpenClaw — 一键安装向导",
    )
    parser.add_argument(
        "--port", type=int, default=5000,
        help="服务端口 (默认: 5000)",
    )
    parser.add_argument(
        "--non-interactive", action="store_true",
        help="非交互模式，自动选择推荐配置",
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="跳过模型下载（仅检测环境）",
    )
    parser.add_argument(
        "model", nargs="?", default=None,
        help="要部署的聊天模型标签（可选位置参数，如 qwen2.5:7b）",
    )
    parser.add_argument(
        "port_pos", nargs="?", type=int, default=None,
        help="服务端口（可选位置参数，覆盖 --port）",
    )
    args = parser.parse_args()

    global NON_INTERACTIVE
    NON_INTERACTIVE = args.non_interactive

    server_port = args.port_pos if args.port_pos is not None else args.port

    banner()

    if not args.non_interactive and not confirm("开始安装？"):
        print(f"\n  {yellow('安装已取消')}")
        return 0

    # === Step 1: Environment ===
    if not step_environment():
        print(f"\n  {red('环境检测未通过，安装终止。')}")
        return 1

    # === Step 2: Python dependencies ===
    step_python_deps()

    # === Step 3: Ollama installation ===
    if not step_ollama_install():
        print(f"\n  {red('Ollama 安装失败，安装终止。')}")
        return 1

    # === Step 4: Ollama service ===
    if not step_ollama_start():
        print(f"\n  {red('Ollama 服务启动失败，安装终止。')}")
        return 1

    # === Step 5: GPU detection & recommendation ===
    recommendation = step_gpu_detection()

    # Optional positional [model] overrides the recommended chat model.
    if args.model:
        recommendation["chat"] = args.model

    gpu_vram_gb = recommendation.get("vram_gb", 0)

    # === Step 6: Model selection ===
    models = step_model_selection(recommendation)

    # === Step 7: Download models ===
    if args.skip_download:
        step_header(7, TOTAL_STEPS, "下载模型")
        step_warn("--skip-download 已指定，跳过下载")
    else:
        step_download(models)

    # === Step 8: Configure & launch ===
    step_configure(
        models,
        gpu_vram_gb=gpu_vram_gb,
        server_port=server_port,
        non_interactive=args.non_interactive,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
