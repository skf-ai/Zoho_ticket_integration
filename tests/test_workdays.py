"""Working-day arithmetic.

This is the highest-risk logic in the system: an off-by-one here means tickets
auto-close a day early and students lose their support case silently. The cases
below pin the rules the client actually agreed to -- Monday-Saturday working,
Sunday off, holidays off, Asia/Kolkata.
"""

import unittest
from datetime import date, datetime, timezone

from src import workdays

IST = workdays.IST


def ist(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


class TestIsWorkingDay(unittest.TestCase):
    def test_saturday_is_a_working_day(self):
        # 2026-07-25 is a Saturday. The client works Mon-Sat.
        self.assertTrue(workdays.is_working_day(date(2026, 7, 25)))

    def test_sunday_is_not(self):
        self.assertFalse(workdays.is_working_day(date(2026, 7, 26)))

    def test_listed_holiday_is_not(self):
        # 2026-08-15 (Independence Day) is in HOLIDAYS.
        self.assertFalse(workdays.is_working_day(date(2026, 8, 15)))

    def test_ordinary_weekday_is(self):
        self.assertTrue(workdays.is_working_day(date(2026, 7, 27)))


class TestAddWorkingDays(unittest.TestCase):
    def test_friday_evening_plus_three_skips_sunday(self):
        # Raised Fri 24 Jul 18:30 IST -> Sat, (skip Sun), Mon, Tue = Tue 28 Jul.
        due = workdays.add_working_days(ist(2026, 7, 24, 18, 30), 3)
        due_ist = workdays.to_ist(due)
        self.assertEqual(due_ist.date(), date(2026, 7, 28))

    def test_saturday_evening_plus_three_lands_wednesday(self):
        # The client's own worked example: a ticket raised Saturday evening is
        # due Wednesday, not Tuesday, because Sunday does not count.
        due = workdays.add_working_days(ist(2026, 7, 25, 18, 0), 3)
        due_ist = workdays.to_ist(due)
        self.assertEqual(due_ist.date(), date(2026, 7, 29))
        self.assertEqual(due_ist.weekday(), 2)  # Wednesday

    def test_deadline_lands_at_end_of_business(self):
        due_ist = workdays.to_ist(workdays.add_working_days(ist(2026, 7, 27, 9), 1))
        self.assertEqual(due_ist.hour, 18)
        self.assertEqual(due_ist.minute, 0)

    def test_holiday_is_skipped_as_well_as_sunday(self):
        # From Thu 13 Aug: +1 = Fri 14. Sat 15 is a holiday, Sun 16 is off,
        # so +2 = Mon 17.
        due_ist = workdays.to_ist(workdays.add_working_days(ist(2026, 8, 13, 10), 2))
        self.assertEqual(due_ist.date(), date(2026, 8, 17))

    def test_result_is_utc_aware(self):
        due = workdays.add_working_days(ist(2026, 7, 27, 9), 1)
        self.assertIsNotNone(due.tzinfo)
        self.assertEqual(due.utcoffset().total_seconds(), 0)

    def test_naive_input_is_treated_as_utc(self):
        naive = datetime(2026, 7, 27, 3, 30)  # 09:00 IST
        aware = datetime(2026, 7, 27, 3, 30, tzinfo=timezone.utc)
        self.assertEqual(
            workdays.add_working_days(naive, 2),
            workdays.add_working_days(aware, 2),
        )


class TestWorkingDaysBetween(unittest.TestCase):
    def test_same_day_is_zero(self):
        self.assertEqual(
            workdays.working_days_between(ist(2026, 7, 27, 9), ist(2026, 7, 27, 17)),
            0,
        )

    def test_counts_saturday_but_not_sunday(self):
        # Fri 24 -> Mon 27 crosses Saturday (counts) and Sunday (does not).
        self.assertEqual(
            workdays.working_days_between(ist(2026, 7, 24), ist(2026, 7, 27)),
            2,
        )

    def test_end_before_start_is_zero(self):
        self.assertEqual(
            workdays.working_days_between(ist(2026, 7, 27), ist(2026, 7, 24)),
            0,
        )


class TestNextWorkingDayStart(unittest.TestCase):
    def test_saturday_evening_defers_to_monday_morning(self):
        nxt = workdays.to_ist(workdays.next_working_day_start(ist(2026, 7, 25, 20)))
        self.assertEqual(nxt.date(), date(2026, 7, 27))
        self.assertEqual(nxt.hour, 9)

    def test_never_lands_on_a_non_working_day(self):
        for day in range(20, 32):
            nxt = workdays.next_working_day_start(ist(2026, 7, day, 12))
            self.assertTrue(workdays.is_working_day(workdays.to_ist(nxt).date()))


class TestSerialization(unittest.TestCase):
    def test_iso_round_trip(self):
        original = datetime(2026, 7, 27, 12, 30, tzinfo=timezone.utc)
        self.assertEqual(workdays.parse(workdays.iso(original)), original)

    def test_iso_strings_sort_chronologically(self):
        # The sweeper relies on lexicographic sorting of these strings on the
        # due-index sort key.
        earlier = workdays.iso(datetime(2026, 7, 27, 9, tzinfo=timezone.utc))
        later = workdays.iso(datetime(2026, 7, 27, 18, tzinfo=timezone.utc))
        self.assertLess(earlier, later)


if __name__ == "__main__":
    unittest.main()
