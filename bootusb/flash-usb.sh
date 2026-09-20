#!/usr/bin/env bash
# ============================================================================
# 把定制好的 ISO 烧进 U 盘（会清空目标 U 盘！）
#
# 用法:  bash bootusb/flash-usb.sh  <iso 文件>  </dev/sdX 整盘设备>
#
# 找设备:  lsblk -dpno NAME,SIZE,MODEL,TRAN   (选 TRAN=usb 的那块，用整盘 /dev/sdX，
#                                              不要写分区 /dev/sdX1)
# ============================================================================
set -euo pipefail

ISO="${1:?用法: flash-usb.sh <iso> </dev/sdX>}"
DEV="${2:?出于安全考虑，必须显式指定目标设备，如 /dev/sdb}"

[ -f "$ISO" ]  || { echo "找不到 ISO: $ISO"; exit 1; }
[ -b "$DEV" ]  || { echo "$DEV 不是块设备"; exit 1; }

# 拒绝写到分区（应写整盘），并粗略拦一下系统盘
case "$DEV" in
    *[0-9]) echo "看起来像分区（$DEV）。请指定整盘，如 /dev/sdb"; exit 1;;
esac
if lsblk -no MOUNTPOINT "$DEV" 2>/dev/null | grep -qE '(^| )/($| )|/boot'; then
    echo "拒绝：$DEV 上似乎挂着系统根/boot分区。换一块 U 盘。"; exit 1
fi

echo "即将【彻底擦除】以下设备并写入 $ISO ："
lsblk -dpno NAME,SIZE,MODEL,TRAN "$DEV" || lsblk "$DEV"
echo ""
read -rp '确认无误？输入大写 ERASE 继续: ' confirm
[ "$confirm" = "ERASE" ] || { echo "已取消"; exit 1; }

# 尽量先卸载该设备的所有分区
for part in $(lsblk -lnpo NAME "$DEV" | tail -n +2); do
    sudo umount "$part" 2>/dev/null || true
done

echo "写入中（sudo dd）..."
sudo dd if="$ISO" of="$DEV" bs=4M status=progress conv=fsync
sync
echo "✅ 完成。拔盘前请等待写缓存刷新完毕。"
