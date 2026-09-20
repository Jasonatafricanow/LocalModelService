#!/usr/bin/env bash
# ============================================================================
# 把官方 Ubuntu Server ISO 定制成 OpenClaw 无人值守安装盘。
#
# 用法:
#   bash bootusb/build-iso.sh  <ubuntu-24.04-live-server-amd64.iso>  [输出.iso]
#
# 依赖:  xorriso, rsync, python3     (Ubuntu: sudo apt install xorriso rsync)
#
# 原理: 用 xorriso 的 "boot_image any replay" 原样复制官方盘的 BIOS+UEFI 引导
#       结构（最稳妥、不易因版本变化翻车），只覆盖/新增三样东西：
#         /nocloud/{user-data,meta-data}   <- autoinstall 应答
#         /openclaw/...                     <- 本项目（供安装期拷进系统）
#         /boot/grub/grub.cfg               <- 改成默认无人值守启动
# ============================================================================
set -euo pipefail

SRC_ISO="${1:?用法: build-iso.sh <ubuntu-server.iso> [输出.iso]}"
OUT_ISO="${2:-openclaw-autoinstall.iso}"

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

[ -f "$SRC_ISO" ] || { echo "找不到源 ISO: $SRC_ISO"; exit 1; }
for t in xorriso rsync python3; do
    command -v "$t" >/dev/null || { echo "缺少依赖: $t (sudo apt install xorriso rsync)"; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> [1/4] 准备 autoinstall 应答文件"
mkdir -p "$WORK/nocloud"
cp "$HERE/autoinstall/user-data" "$WORK/nocloud/user-data"
cp "$HERE/autoinstall/meta-data" "$WORK/nocloud/meta-data"

echo "==> [2/4] 暂存 OpenClaw 项目（剔除 .git/缓存/已构建 ISO）"
mkdir -p "$WORK/openclaw"
rsync -a \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache' \
    --exclude 'bootusb/*.iso' \
    --exclude '*.iso' \
    "$REPO_ROOT/" "$WORK/openclaw/"

echo "==> [3/4] 提取并改写 grub.cfg（默认走无人值守安装）"
xorriso -osirrox on -indev "$SRC_ISO" \
    -extract /boot/grub/grub.cfg "$WORK/grub.cfg" 2>/dev/null
python3 - "$WORK/grub.cfg" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p, encoding="utf-8", errors="replace").read()
# 去掉原有的 default/timeout 设定，避免覆盖我们的
s = re.sub(r'^\s*set\s+(default|timeout(_style)?)=.*$', '', s, flags=re.M)
header = (
    'set default=0\n'
    'set timeout=5\n'
    'menuentry "Install OpenClaw (Automated, ERASES DISK)" {\n'
    '    set gfxpayload=keep\n'
    '    linux  /casper/vmlinuz autoinstall ds=nocloud\\;s=/cdrom/nocloud/ ---\n'
    '    initrd /casper/initrd\n'
    '}\n'
)
open(p, "w", encoding="utf-8").write(header + s)
print("grub.cfg patched")
PY

echo "==> [4/4] 重新打包 ISO（复用官方引导结构）"
xorriso -indev "$SRC_ISO" -outdev "$OUT_ISO" \
    -boot_image any replay \
    -volid OPENCLAW_AUTO \
    -map "$WORK/nocloud" /nocloud \
    -map "$WORK/openclaw" /openclaw \
    -map "$WORK/grub.cfg" /boot/grub/grub.cfg \
    -commit

echo ""
echo "✅ 完成: $OUT_ISO"
echo "   下一步: bash bootusb/flash-usb.sh \"$OUT_ISO\" /dev/sdX"
echo "   建议先用 QEMU 试跑:  qemu-system-x86_64 -m 4096 -cdrom \"$OUT_ISO\" -boot d"
