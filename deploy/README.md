# OpenClaw 跨境部署方案

```
                   大陆服务器 (GPU)                         海外 VPS (2核2G, $5/月)
               ┌──────────────────────┐               ┌──────────────────────┐
               │                      │               │                      │
               │  OpenClaw            │               │  nginx (反代 HTTPS)  │
               │   ├─ Ollama (GPU)    │◄──SSH 隧道──►│  或 frps             │
               │   └─ WhatsAppBridge  │    -R 5000    │                      │
               │       └─ 走代理出海  │               │  WhatsApp Webhook    │
               │                      │               │  ←─ https://vps:443  │
               └──────┬───────────────┘               └──────────────────────┘
                      │ HTTPS_PROXY=socks5://...
                      │
                      ▼
               WhatsApp Cloud API
               graph.facebook.com
```

## 架构原则

| 链路 | 位置 | 原因 |
|------|------|------|
| LLM 推理 (Ollama) | **大陆 GPU 机** | 模型大、延迟敏感，必须本地跑 |
| WhatsApp API 收发 | **出海 → 海外 VPS** | graph.facebook.com 被墙，需代理 |
| Webhook 回调 | **海外 VPS 反代 → 隧道 → 本地** | WhatsApp 必须能回调到公网 HTTPS |

---

## 一、海外 VPS 搭建（一次性的）

### 1. 安装 nginx

```bash
# Ubuntu 22.04
apt update && apt install -y nginx certbot python3-certbot-nginx

# 配置 SSL（需要域名指向 VPS）
certbot --nginx -d your-domain.com
```

### 2. 配置反代

将 `vps-nginx.conf` 复制到 `/etc/nginx/sites-available/openclaw`，修改域名后启用：

```bash
cp deploy/vps-nginx.conf /etc/nginx/sites-available/openclaw
# 编辑文件，将 your-domain.com 替换为你的域名
ln -s /etc/nginx/sites-available/openclaw /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## 二、大陆服务器部署

### 1. 标准安装

```bash
cd /home/user/openclaw

# 一键安装（含 Ollama + 模型下载）
python3 install.py --non-interactive

# 或手动
pip install -r requirements.txt
python3 src/main.py
```

### 2. 配置 WhatsApp 代理

```bash
# 方式 A：环境变量（推荐，全局生效）
export HTTPS_PROXY="socks5://127.0.0.1:1080"
export ALL_PROXY="socks5://127.0.0.1:1080"
python3 src/main.py

# 方式 B：HTTP 代理（如 V2Ray 本地端口）
export HTTPS_PROXY="http://127.0.0.1:8118"
python3 src/main.py
```

### 3. 建立 Webhook 隧道

```bash
# 方式 A：SSH 反向隧道（最简单，无需额外软件）
# 大陆服务器上执行：
ssh -R 5000:localhost:5000 -N -o ServerAliveInterval=60 user@your-vps.com

# 方式 B：frp 隧道（更稳定，推荐生产使用）
# 大陆服务器上：
./deploy/setup-frpc.sh
```

---

## 三、WhatsApp Cloud API 配置

在 [Meta Developer Console](https://developers.facebook.com) 中：

| 配置项 | 值 |
|--------|-----|
| Webhook URL | `https://your-domain.com/webhook` |
| Verify Token | 任意字符串，需与 `verify_webhook()` 调用时一致 |
| 回调地址 | `https://your-domain.com/whatsapp-webhook` |

---

## 四、启动命令（完整）

```bash
# 大陆 GPU 机
export HTTPS_PROXY="socks5://127.0.0.1:1080"
export OLLAMA_HOST="http://localhost:11434"

ssh -R 5000:localhost:5000 -N -o ServerAliveInterval=60 user@vps &
python3 src/main.py
```
