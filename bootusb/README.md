# OpenClaw 一键启动盘 (bootusb)

把一台普通 x86_64 机器变成「插 U 盘 → 开机 → 自动装好 Ubuntu 和 OpenClaw」的 AI 服务机。

## 它到底做了什么

制作出来的 U 盘是一张**定制过的 Ubuntu 24.04 Server 安装盘**。目标机从它启动后会：

1. **无人值守安装 Ubuntu**（自动分区、建用户、联网）——⚠️ 会**清空目标机最大的那块硬盘**。
2. 安装完自动重启，进入系统后由 `openclaw-firstboot.service` 接管：
3. **尽力探测并安装 GPU 驱动**（NVIDIA→驱动+CUDA，AMD→ROCm 尽力，识别不到→CPU），装了独显驱动会再重启一次。
4. 建 Python venv、装依赖、跑 `install.py --non-interactive`：**装 Ollama、按显存拉推荐模型、写配置**。
5. 启用 `openclaw.service`，服务常驻在 `http://<机器IP>:5000`。

全程无需人工干预。**首次开机需要联网**（下载 Ollama 和模型）。

## 前置条件

- 一台 **Linux 构建机**（用来做 ISO），装好：`xorriso`、`rsync`
  ```bash
  sudo apt install xorriso rsync
  ```
- 官方 **Ubuntu Server 24.04 LTS** ISO（`ubuntu-24.04.x-live-server-amd64.iso`），从 ubuntu.com/download/server 下载。
- 一个 **≥8GB U 盘**（做安装盘用；模型不打包进盘，走首次开机联网下载）。
- 目标机：**可以被整盘清空**，能联网，UEFI 或 Legacy BIOS 均可。

## 三步走

### 1) 构建定制 ISO（在 Linux 构建机上）

```bash
cd /path/to/LocalModelService
bash bootusb/build-iso.sh ~/Downloads/ubuntu-24.04.2-live-server-amd64.iso openclaw-autoinstall.iso
```

### 2) 先在虚拟机里试跑（强烈建议）

真烧 U 盘前，先用 QEMU 验证会不会正常无人值守安装：

```bash
qemu-system-x86_64 -m 4096 -smp 2 -cdrom openclaw-autoinstall.iso -boot d \
  -drive file=test.qcow2,if=virtio,size=30G -nographic
# (先 qemu-img create -f qcow2 test.qcow2 30G)
```

### 3) 烧录到 U 盘

```bash
lsblk -dpno NAME,SIZE,MODEL,TRAN          # 找到 U 盘，认准 TRAN=usb，用整盘 /dev/sdX
bash bootusb/flash-usb.sh openclaw-autoinstall.iso /dev/sdX
```

然后把 U 盘插到目标机，设 BIOS 从 U 盘启动，开机即自动开跑。

## 装完之后怎么用

- 服务地址：`http://<机器IP>:5000`，接口用法见项目根 `README` / `DEV_LOG`（`/health`、`/chat`、`/v1/chat/completions` 等）。
- **默认账号 `openclaw` / 默认密码 `openclaw` —— 请立刻改：** `passwd`。
- 首次开机进度日志：`/var/log/openclaw-firstboot.log`（`journalctl -u openclaw-firstboot -f` 也行）。
- 服务管理：`systemctl status openclaw`、`systemctl restart openclaw`。
- 配置文件：`/opt/openclaw/config/agent_llm_config.json`（改模型/端口后 `systemctl restart openclaw`）。

## 定制

- **改默认密码**：`openssl passwd -6` 生成新哈希，替换 `bootusb/autoinstall/user-data` 里 `identity.password`，重新构建 ISO。
- **固定端口/模型**：改 `user-data` 让首次开机传参，或装完后改 `config/agent_llm_config.json`。
- **离线部署（不联网拉模型）**：本盘默认走联网下载。若要完全离线，需要把模型预置进镜像（体积会涨到几十 G），可另行扩展 `firstboot.sh` 从盘内拷贝 blob——需要时告诉我。

## 注意事项 / 已知限制

- **破坏性**：安装会清空目标机最大的硬盘。上生产前务必在 VM 里验证一遍。
- **GPU 驱动是尽力而为**：驱动依机器而定，装不上会自动回退 CPU（用 `qwen2.5:3b`）。
- **ISO 引导结构随版本变化**：`build-iso.sh` 用 `xorriso ... boot_image any replay` 复用官方引导，对 24.04 系列稳；换大版本（如未来 26.04）可能需微调 `grub.cfg` 里 `casper` 路径。
- **首次开机必须联网**：Ollama 和模型是那时候下载的。
