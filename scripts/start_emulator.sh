#!/bin/zsh
set -euo pipefail

SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}"
AVD_NAME="${ANDROID_AVD_NAME:-Ctrip_Pixel_1080x2400}"
ADB="$SDK_ROOT/platform-tools/adb"
EMULATOR="$SDK_ROOT/emulator/emulator"
LAUNCHD_LABEL="com.tiket.ctrip-emulator"
LOG_FILE="$HOME/Library/Logs/tiket-emulator.log"

if [[ ! -x "$ADB" || ! -x "$EMULATOR" ]]; then
  print -u2 "Android SDK 未安装。请先运行 ./scripts/setup_emulator.sh"
  exit 1
fi

running_serial="$($ADB devices | awk '$1 ~ /^emulator-/ && $2 == "device" {print $1; exit}')"
if [[ -n "$running_serial" ]]; then
  print "模拟器已运行：$running_serial"
  print "export ANDROID_DEVICE_SERIAL=$running_serial"
  exit 0
fi

if ! "$EMULATOR" -list-avds | grep -Fxq "$AVD_NAME"; then
  print -u2 "找不到 AVD：$AVD_NAME。请先运行 ./scripts/setup_emulator.sh"
  exit 1
fi

print "正在启动 $AVD_NAME ..."
mkdir -p "$HOME/Library/Logs"
# 交给当前 macOS 用户的 launchd 托管，避免调用脚本的终端退出后模拟器也被终止。
launchctl remove "$LAUNCHD_LABEL" 2>/dev/null || true
launchctl submit -l "$LAUNCHD_LABEL" -o "$LOG_FILE" -e "$LOG_FILE" -- \
  "$EMULATOR" -avd "$AVD_NAME" -no-boot-anim -netdelay none -netspeed full -no-metrics

serial=""
for _ in {1..60}; do
  serial="$($ADB devices | awk '$1 ~ /^emulator-/ {print $1; exit}')"
  [[ -n "$serial" ]] && break
  sleep 1
done
if [[ -z "$serial" ]]; then
  print -u2 "模拟器进程已启动，但 60 秒内没有出现在 adb devices。日志：$LOG_FILE"
  exit 1
fi

$ADB -s "$serial" wait-for-device
until [[ "$($ADB -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; do
  sleep 2
done

$ADB -s "$serial" shell wm size 1080x2400 >/dev/null
$ADB -s "$serial" shell wm density 420 >/dev/null
$ADB -s "$serial" shell settings put global window_animation_scale 0
$ADB -s "$serial" shell settings put global transition_animation_scale 0
$ADB -s "$serial" shell settings put global animator_duration_scale 0
$ADB -s "$serial" shell input keyevent 82 || true

print "模拟器已就绪：$serial"
print "export ANDROID_DEVICE_SERIAL=$serial"
