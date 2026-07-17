import os
import shutil
import subprocess


def find_adb():
    """返回 adb 路径，兼容终端和由 macOS App 启动的服务进程。"""
    candidates = [
        os.environ.get("ANDROID_ADB_PATH"),
        shutil.which("adb"),
    ]
    for sdk_root in filter(None, [
        os.environ.get("ANDROID_SDK_ROOT"),
        os.environ.get("ANDROID_HOME"),
        os.path.expanduser("~/Library/Android/sdk"),
    ]):
        candidates.append(os.path.join(sdk_root, "platform-tools", "adb"))

    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def list_adb_devices(adb_path=None):
    """返回已授权并在线的 ``[(serial, description), ...]``。"""
    adb_path = adb_path or find_adb()
    if not adb_path:
        return []

    result = subprocess.run(
        [adb_path, "devices", "-l"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append((parts[0], " ".join(parts[2:])))
    return devices


def choose_device_serial(devices, requested_serial=None):
    """选择目标设备：显式序列号优先，否则优先使用 Android 模拟器。"""
    serials = [serial for serial, _ in devices]
    if requested_serial:
        if requested_serial not in serials:
            raise RuntimeError(
                f"Configured Android device '{requested_serial}' is not online. "
                f"Available devices: {', '.join(serials) or 'none'}"
            )
        return requested_serial

    emulators = [serial for serial in serials if serial.startswith("emulator-")]
    if emulators:
        return sorted(emulators)[0]
    if len(serials) == 1:
        return serials[0]
    if not serials:
        raise RuntimeError(
            "No Android device is online. Start the emulator with "
            "./scripts/start_emulator.sh first."
        )
    raise RuntimeError(
        "Multiple physical Android devices are online. Set ANDROID_DEVICE_SERIAL "
        "to the device shown by 'adb devices'."
    )


def resolve_launcher_activity(device, package_name):
    """解析应用 Launcher Activity，避免 Android 15 模拟器的 Monkey 启动限制。"""
    response = device.shell([
        "cmd", "package", "resolve-activity", "--brief",
        "-c", "android.intent.category.LAUNCHER", package_name,
    ])
    output = getattr(response, "output", str(response))
    for line in reversed(output.splitlines()):
        component = line.strip()
        if component.startswith(f"{package_name}/"):
            return component.split("/", 1)[1]
    raise RuntimeError(f"Cannot resolve launcher activity for {package_name}")
