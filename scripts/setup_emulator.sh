#!/bin/zsh
set -euo pipefail

SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}"
JAVA_HOME_LOCAL="${JAVA_HOME:-$HOME/.local/share/tiket-jdk/Contents/Home}"
AVD_NAME="${ANDROID_AVD_NAME:-Ctrip_Pixel_1080x2400}"
SYSTEM_IMAGE="${ANDROID_SYSTEM_IMAGE:-system-images;android-35;google_apis;arm64-v8a}"
COMMAND_LINE_TOOLS_VERSION="${ANDROID_COMMAND_LINE_TOOLS_VERSION:-14742923}"
SDKMANAGER="$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
AVDMANAGER="$SDK_ROOT/cmdline-tools/latest/bin/avdmanager"

if [[ ! -x "$JAVA_HOME_LOCAL/bin/java" ]]; then
  print "正在安装本地 JDK 21 ..."
  jdk_install_root="${JAVA_HOME_LOCAL:h:h}"
  mkdir -p "$jdk_install_root"
  jdk_archive="$(mktemp -t tiket-jdk).tar.gz"
  curl -fL --progress-bar \
    'https://api.adoptium.net/v3/binary/latest/21/ga/mac/aarch64/jdk/hotspot/normal/eclipse' \
    -o "$jdk_archive"
  tar -xzf "$jdk_archive" -C "$jdk_install_root" --strip-components=1
  rm -f "$jdk_archive"
fi
if [[ ! -x "$SDKMANAGER" ]]; then
  print "正在安装 Android Command-line Tools ..."
  tools_archive="$(mktemp -t android-command-line-tools).zip"
  tools_dir="$(mktemp -d -t android-command-line-tools)"
  curl -fL --progress-bar \
    "https://dl.google.com/android/repository/commandlinetools-mac-${COMMAND_LINE_TOOLS_VERSION}_latest.zip" \
    -o "$tools_archive"
  unzip -q "$tools_archive" -d "$tools_dir"
  mkdir -p "$SDK_ROOT/cmdline-tools/latest"
  mv "$tools_dir/cmdline-tools/"* "$SDK_ROOT/cmdline-tools/latest/"
  rm -f "$tools_archive"
fi

export JAVA_HOME="$JAVA_HOME_LOCAL"
export ANDROID_SDK_ROOT="$SDK_ROOT"
export PATH="$JAVA_HOME/bin:$SDK_ROOT/cmdline-tools/latest/bin:$SDK_ROOT/platform-tools:$SDK_ROOT/emulator:$PATH"

yes | "$SDKMANAGER" --licenses >/dev/null || true
"$SDKMANAGER" "platform-tools" "emulator" "platforms;android-35" "$SYSTEM_IMAGE"

if ! "$SDK_ROOT/emulator/emulator" -list-avds | grep -Fxq "$AVD_NAME"; then
  print "no" | "$AVDMANAGER" create avd --force --name "$AVD_NAME" --package "$SYSTEM_IMAGE" --device "pixel_6"
fi

CONFIG="$HOME/.android/avd/$AVD_NAME.avd/config.ini"
if [[ -f "$CONFIG" ]]; then
  sed -i '' -E 's/^hw\.lcd\.width=.*/hw.lcd.width=1080/; s/^hw\.lcd\.height=.*/hw.lcd.height=2400/; s/^hw\.lcd\.density=.*/hw.lcd.density=420/' "$CONFIG"
fi

print "AVD 已准备完成：$AVD_NAME"
print "下一步：./scripts/start_emulator.sh"
