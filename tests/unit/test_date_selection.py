import unittest
from datetime import datetime

import mobile_crawler


def view(text, left, top, right=1080, bottom=None):
    return {
        "text": text,
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom if bottom is not None else top + 60,
    }


class DateSelectionTests(unittest.TestCase):
    def test_current_month_fallback_accounts_for_calendar_scrolled_to_today(self):
        click_y = mobile_crawler.calendar_fallback_click_y(
            datetime(2026, 7, 25),
            header_top=583,
            today=datetime(2026, 7, 17),
        )
        # July 17 is in the first visible week; July 25 is the next row.
        self.assertEqual(click_y, 871)

    def test_future_month_fallback_starts_from_month_first_week(self):
        click_y = mobile_crawler.calendar_fallback_click_y(
            datetime(2026, 8, 1),
            header_top=1171,
            today=datetime(2026, 7, 17),
        )
        self.assertEqual(click_y, 1306)

    def test_swipes_down_when_target_month_is_earlier_than_visible_months(self):
        self.assertEqual(
            mobile_crawler.calendar_swipe_direction(
                datetime(2026, 7, 25),
                [(2026, 8), (2026, 9)],
            ),
            "down",
        )

    def test_swipes_up_when_target_month_is_later_than_visible_months(self):
        self.assertEqual(
            mobile_crawler.calendar_swipe_direction(
                datetime(2026, 10, 25),
                [(2026, 8), (2026, 9)],
            ),
            "up",
        )

    def test_does_not_swipe_when_target_month_is_visible(self):
        self.assertIsNone(
            mobile_crawler.calendar_swipe_direction(
                datetime(2026, 8, 25),
                [(2026, 8), (2026, 9)],
            )
        )

    def test_prefers_actual_date_node_bounds_over_fixed_row_coordinate(self):
        target = datetime(2026, 7, 25)
        # The actual date node is 70px above the old fixed-coordinate center;
        # another 25 is present farther away from the target month's expected row.
        actual = view("25", 965, 1150, 1010, 1210)
        adjacent_month = view("25", 965, 1500, 1010, 1560)

        selected = mobile_crawler.choose_calendar_date_view(
            [adjacent_month, actual],
            target,
            header_top=583,
        )

        self.assertIs(selected, actual)

    def test_returns_none_when_target_date_node_is_not_exposed(self):
        target = datetime(2026, 7, 25)
        selected = mobile_crawler.choose_calendar_date_view(
            [view("24", 815, 1150, 860, 1210)],
            target,
            header_top=583,
        )
        self.assertIsNone(selected)

    def test_selected_date_parser_matches_month_and_day(self):
        class Device:
            pass

        device = Device()
        original = mobile_crawler.collect_screen_views
        try:
            mobile_crawler.collect_screen_views = lambda _: [
                {"text": "07-25周六", "left": 0, "top": 0, "right": 100, "bottom": 40}
            ]
            self.assertTrue(
                mobile_crawler.selected_date_matches(device, datetime(2026, 7, 25))
            )
            self.assertFalse(
                mobile_crawler.selected_date_matches(device, datetime(2026, 8, 1))
            )
        finally:
            mobile_crawler.collect_screen_views = original


if __name__ == "__main__":
    unittest.main()
