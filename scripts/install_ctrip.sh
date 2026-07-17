#!/bin/zsh
set -euo pipefail

SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}"
ADB="$SDK_ROOT/platform-tools/adb"
SERIAL="${ANDROID_DEVICE_SERIAL:-$($ADB devices | awk '$1 ~ /^emulator-/ && $2 == "device" {print $1; exit}')}"

if [[ -z "$SERIAL" ]]; then
  print -u2 "没有运行中的 Android 模拟器。请先运行 ./scripts/start_emulator.sh"
  exit 1
fi

APK_URL="$(curl -fsSIL -A 'Mozilla/5.0 (Linux; Android 13; Pixel 6)' https://m.ctrip.com/m/c1051 | awk 'BEGIN{IGNORECASE=1} /^location: .*\.apk/ {sub(/^[^:]+:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit}')"
if [[ -z "$APK_URL" ]]; then
  print -u2 "无法从携程官方下载页取得 APK 地址。"
  exit 1
fi

APK_FILE="$(mktemp -t ctrip).apk"
trap 'rm -f "$APK_FILE"' EXIT
print "正在从携程官网下载 APK ..."
curl -fL --progress-bar "$APK_URL" -o "$APK_FILE"
print "正在安装到 $SERIAL ..."
"$ADB" -s "$SERIAL" install -r "$APK_FILE"
"$ADB" -s "$SERIAL" shell pm grant ctrip.android.view android.permission.POST_NOTIFICATIONS 2>/dev/null || true
print "携程已安装，包名：ctrip.android.view"
