#!/usr/bin/env bash
# ============================================================================
# OpenClaw 装机凭据初始化（autoinstall late-commands 里以 root 在目标系统内运行）
#
# 1) 把 user-data 里的公开默认密码换成每台机器独立的随机密码，并要求首次登录改密。
#    新密码只显示在本机控制台登录界面（/etc/issue.d），局域网里的人拿不到。
# 2) 生成 OPENCLAW_API_KEY 写入 /etc/openclaw/openclaw.env（仅 root 可读），
#    openclaw.service 通过 EnvironmentFile 读取——否则 0.0.0.0 绑定会被
#    validate_bind_security 拒绝，服务起不来。
#
# 幂等：已存在的 env 文件不会被覆盖。
# ============================================================================
set -euo pipefail

USER_NAME=openclaw
ENV_DIR=/etc/openclaw
ENV_FILE="$ENV_DIR/openclaw.env"
ISSUE_FILE=/etc/issue.d/90-openclaw.issue

rand() {
    python3 -c "import secrets, sys; print(secrets.token_urlsafe(int(sys.argv[1])))" "$1"
}

password="$(rand 12)"
echo "$USER_NAME:$password" | chpasswd
chage -d 0 "$USER_NAME"   # 首次登录（含 SSH）强制改密

install -d -m 755 /etc/issue.d
cat > "$ISSUE_FILE" <<EOF
OpenClaw initial login: $USER_NAME / $password
(You must change it at first login. API key: sudo cat $ENV_FILE)

EOF
chmod 644 "$ISSUE_FILE"

install -d -m 700 "$ENV_DIR"
if [ ! -s "$ENV_FILE" ]; then
    umask 077
    printf 'OPENCLAW_API_KEY=%s\nOPENCLAW_TOOLS_API_KEY=%s\n' "$(rand 32)" "$(rand 32)" > "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
