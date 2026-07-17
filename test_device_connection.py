import unittest

from android_device import choose_device_serial, resolve_launcher_activity


class FakeShellResponse:
    output = (
        "priority=0 preferredOrder=0 match=0x108000 isDefault=false\n"
        "ctrip.android.view/ctrip.business.splash.CtripSplashActivity\n"
    )


class FakeDevice:
    def shell(self, _args):
        return FakeShellResponse()


class ChooseDeviceSerialTests(unittest.TestCase):
    def test_prefers_emulator_over_physical_device(self):
        devices = [("R58M123", "model:Phone"), ("emulator-5554", "model:sdk_gphone")]
        self.assertEqual(choose_device_serial(devices), "emulator-5554")

    def test_honors_requested_serial(self):
        devices = [("emulator-5554", ""), ("emulator-5556", "")]
        self.assertEqual(
            choose_device_serial(devices, "emulator-5556"),
            "emulator-5556",
        )

    def test_rejects_offline_requested_serial(self):
        with self.assertRaisesRegex(RuntimeError, "is not online"):
            choose_device_serial([], "emulator-5554")

    def test_requires_selection_for_multiple_physical_devices(self):
        with self.assertRaisesRegex(RuntimeError, "Multiple physical"):
            choose_device_serial([("phone-1", ""), ("phone-2", "")])

    def test_resolves_launcher_activity_from_package_manager_output(self):
        self.assertEqual(
            resolve_launcher_activity(FakeDevice(), "ctrip.android.view"),
            "ctrip.business.splash.CtripSplashActivity",
        )


if __name__ == "__main__":
    unittest.main()
