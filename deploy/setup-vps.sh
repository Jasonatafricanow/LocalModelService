#!/bin/bash
# OpenClaw 跨境部署 — VPS 初始化脚本（在海外 VPS 上运行）
# 用法: bash deploy/setup-vps.sh your-domain.com
#
set -e

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
    echo "用法: bash setup-vps.sh your-domain.com"
    exit 1
fi

echo "=== 1/4 安装 nginx + certbot ==="
apt update && apt install -y nginx certbot python3-certbot-nginx

echo "=== 2/4 配置 nginx ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sed "s/your-domain.com/$DOMAIN/g" "$SCRIPT_DIR/vps-nginx.conf" > /etc/nginx/sites-available/openclaw
ln -sf /etc/nginx/sites-available/openclaw /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx

echo "=== 3/4 申请 SSL 证书 ==="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@"$DOMAIN" || {
    echo "certbot 需要交互，手动运行: certbot --nginx -d $DOMAIN"
}

echo "=== 4/4 检查服务状态 ==="
systemctl status nginx --no-pager | head -5

echo ""
echo "✅ VPS 配置完成"
echo "   nginx 反代: https://$DOMAIN → localhost:5000"
echo ""
echo "   接下来在大陆服务器上执行:"
echo "   ssh -R 5000:localhost:5000 -N root@$(curl -s ifconfig.me)"
