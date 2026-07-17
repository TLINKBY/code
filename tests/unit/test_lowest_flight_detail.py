import os
import tempfile
import unittest
from unittest.mock import patch

import mobile_crawler


def make_flight(number, price, departure="2026-07-25 20:55", top=400):
    return {
        "flight_number": number,
        "airline": "春秋航空",
        "departure_time": departure,
        "arrival_time": "2026-07-25 23:30",
        "price": float(price),
        "bounds": {"left": 20, "top": top, "right": 1060, "bottom": top + 200},
    }


class FakeImage:
    def save(self, path):
        with open(path, "wb") as output:
            output.write(b"fake png")


class FakeDevice:
    def __init__(self):
        self.clicks = []
        self.swipes = []
        self.presses = []

    def click(self, x, y):
        self.clicks.append((x, y))

    def swipe_ext(self, direction, scale):
        self.swipes.append((direction, scale))

    def press(self, key):
        self.presses.append(key)

    def screenshot(self):
        return FakeImage()


class LowestFlightDetailTests(unittest.TestCase):
    def setUp(self):
        self.device = FakeDevice()
        self.lowest = make_flight("9C8931", 310)
        self.other = make_flight("MU1234", 430, departure="2026-07-25 18:10")

    @patch.object(mobile_crawler, "time")
    @patch.object(mobile_crawler, "ensure_screen_on")
    @patch.object(mobile_crawler, "parse_screen_flights")
    def test_relocates_lowest_flight_upward_and_clicks_its_card(
        self,
        parse_screen_flights,
        ensure_screen_on,
        fake_time,
    ):
        parse_screen_flights.side_effect = [[self.other], [self.lowest]]

        clicked = mobile_crawler.find_and_click_flight(
            self.device,
            self.lowest,
            "2026-07-25",
            max_upward_swipes=2,
        )

        self.assertTrue(clicked)
        self.assertEqual(self.device.swipes, [("down", 0.7)])
        self.assertEqual(self.device.clicks, [(540, 500)])

    @patch.object(mobile_crawler, "wait_for_flight_detail_page", return_value=True)
    @patch.object(mobile_crawler, "find_and_click_flight", return_value=True)
    @patch.object(mobile_crawler, "ensure_screen_on")
    def test_only_lowest_qualifying_flight_gets_full_screen_path(
        self,
        ensure_screen_on,
        find_and_click_flight,
        wait_for_flight_detail_page,
    ):
        flights = [self.other, self.lowest]
        with tempfile.TemporaryDirectory() as screenshot_dir:
            captured = mobile_crawler.capture_lowest_flight_detail(
                self.device,
                flights,
                "2026-07-25",
                target_price=350,
                max_upward_swipes=4,
                screenshot_dir=screenshot_dir,
            )

            self.assertTrue(captured)
            self.assertNotIn("screenshot_path", self.other)
            self.assertRegex(self.lowest["screenshot_path"], r"^/static/generated/target_9C8931_\d+\.png$")
            filename = self.lowest["screenshot_path"].removeprefix("/static/generated/")
            self.assertTrue(os.path.exists(os.path.join(screenshot_dir, filename)))

    @patch.object(mobile_crawler, "find_and_click_flight")
    def test_does_not_open_detail_when_lowest_price_misses_target(self, find_and_click_flight):
        captured = mobile_crawler.capture_lowest_flight_detail(
            self.device,
            [self.lowest],
            "2026-07-25",
            target_price=300,
            max_upward_swipes=4,
        )

        self.assertFalse(captured)
        find_and_click_flight.assert_not_called()

    @patch.object(mobile_crawler, "time")
    @patch.object(mobile_crawler, "wait_for_flight_detail_page", return_value=False)
    @patch.object(mobile_crawler, "find_and_click_flight", return_value=True)
    def test_timeout_returns_to_list_and_keeps_scraped_flight(
        self,
        find_and_click_flight,
        wait_for_flight_detail_page,
        fake_time,
    ):
        captured = mobile_crawler.capture_lowest_flight_detail(
            self.device,
            [self.lowest],
            "2026-07-25",
            target_price=350,
            max_upward_swipes=4,
        )

        self.assertFalse(captured)
        self.assertEqual(self.device.presses, ["back"])
        self.assertNotIn("screenshot_path", self.lowest)


if __name__ == "__main__":
    unittest.main()
