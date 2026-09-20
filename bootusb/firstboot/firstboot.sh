#!/usr/bin/env bash
# ============================================================================
# OpenClaw 首次开机自动配置（由 openclaw-firstboot.service 触发，root 运行）
#
# 两阶段状态机（/var/lib/openclaw/phase）：
#   start   -> 联网、apt update、尽力探测并安装 GPU 驱动；装了独显驱动就重启
#   drivers -> 建 venv、装依赖、跑 install.py --non-interactive（装 Ollama+拉模型+写配置）
#              然后启用并启动 openclaw.service，标记 done 并自禁用本服务
#   done    -> 直接退出
#
# 全程日志： /var/log/openclaw-firstboot.log
# ============================================================================
set -uo pipefail

APP=/opt/openclaw
VENV="$APP/.venv"
STATE_DIR=/var/lib/openclaw
STATE="$STATE_DIR/phase"
LOG=/var/log/openclaw-firstboot.log

mkdir -p "$STATE_DIR"
# 同时输出到日志和控制台
exec > >(tee -a "$LOG") 2>&1

phase="$(cat "$STATE" 2>/dev/null || echo start)"
echo "=================================================================="
echo "[firstboot] $(date -Is)  phase=$phase"

[ "$phase" = "done" ] && { echo "[firstboot] already completed, nothing to do"; exit 0; }

wait_net() {
    echo "[firstboot] waiting for network (max ~5 min)..."
    for _ in $(seq 1 60); do
        if curl -fsS --max-time 5 https://ollama.com >/dev/null 2>&1; then
            echo "[firstboot] network is up"; return 0
        fi
        sleep 5
    done
    echo "[firstboot] WARN: network still not reachable, continuing anyway"
    return 1
}

# --------------------------------------------------------------------------
# Phase: start  — GPU driver best-effort (target GPU is mixed/unknown)
# --------------------------------------------------------------------------
if [ "$phase" = "start" ]; then
    export DEBIAN_FRONTEND=noninteractive
    wait_net || true
    apt-get update -y || true

    gpu_line="$(lspci 2>/dev/null | grep -iE 'vga|3d|display' || true)"
    echo "[firstboot] GPU probe: ${gpu_line:-none}"

    if echo "$gpu_line" | grep -qi 'nvidia'; then
        echo "[firstboot] NVIDIA detected -> installing driver (ubuntu-drivers autoinstall)"
        apt-get install -y ubuntu-drivers-common || true
        ubuntu-drivers autoinstall || apt-get install -y nvidia-driver-535-server || true
        echo drivers > "$STATE"
        echo "[firstboot] driver installed, rebooting to load it..."
        sleep 3; systemctl reboot; exit 0

    elif echo "$gpu_line" | grep -qiE 'amd|ati|radeon|advanced micro devices'; then
        echo "[firstboot] AMD detected -> best-effort ROCm tooling (may be skipped)"
        # 完整 ROCm 体积大且版本敏感；这里只装轻量的 rocm-smi，装不上就回退 CPU。
        apt-get install -y rocm-smi 2>/dev/null || echo "[firstboot] ROCm skipped -> CPU fallback"
        echo drivers > "$STATE"
        echo "[firstboot] rebooting to settle kernel modules..."
        sleep 3; systemctl reboot; exit 0

    else
        echo "[firstboot] no discrete GPU -> CPU mode, no reboot needed"
        echo drivers > "$STATE"
        # 不重启，直接进入下一阶段
    fi
fi

# --------------------------------------------------------------------------
# Phase: drivers  — build venv, install deps, run OpenClaw installer, start svc
# --------------------------------------------------------------------------
wait_net || true

echo "[firstboot] creating virtualenv at $VENV"
python3 -m venv "$VENV" || { echo "[firstboot] ERROR: venv creation failed"; }
"$VENV/bin/pip" install --upgrade pip || true
if [ -f "$APP/requirements.txt" ]; then
    echo "[firstboot] installing Python dependencies into venv"
    "$VENV/bin/pip" install -r "$APP/requirements.txt" || echo "[firstboot] WARN: some deps failed to install"
fi

echo "[firstboot] running OpenClaw installer (Ollama + models + config)"
cd "$APP"
# --non-interactive: 自动选推荐模型，装 Ollama、拉模型、写配置（不自动起服务，由 systemd 接管）
"$VENV/bin/python" "$APP/install.py" --non-interactive || echo "[firstboot] WARN: installer returned non-zero"

echo "[firstboot] enabling and starting openclaw.service"
cp "$APP/bootusb/firstboot/openclaw.service" /etc/systemd/system/ 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now openclaw.service || echo "[firstboot] WARN: could not start openclaw.service"

echo done > "$STATE"
touch "$STATE_DIR/.firstboot-done"
systemctl disable openclaw-firstboot.service || true
echo "[firstboot] COMPLETE $(date -Is) — server should be on http://<host>:5000"
