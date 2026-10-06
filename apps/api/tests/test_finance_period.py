"""Tests for finance_period's pure period-resolution logic — IST edge
cases, week-start convention, custom-range validation, and the UTC
conversion used to filter payment.created_at."""

from datetime import date, datetime, timedelta, timezone

import pytest

from finance_period import (
    IST,
    InvalidPeriod,
    format_range_label,
    ist_day_bounds_to_utc,
    resolve_period,
)


class TestToday:
    def test_today_is_a_single_day_range(self):
        d = date(2026, 10, 6)
        assert resolve_period("today", d) == (d, d)


class TestThisWeek:
    def test_monday_is_the_start_of_its_own_week(self):
        monday = date(2026, 10, 5)  # a real Monday
        assert monday.weekday() == 0
        start, end = resolve_period("this_week", monday)
        assert start == monday
        assert end == monday + timedelta(days=6)

    def test_sunday_belongs_to_the_week_that_started_the_prior_monday(self):
        sunday = date(2026, 10, 11)
        assert sunday.weekday() == 6
        start, end = resolve_period("this_week", sunday)
        assert start == date(2026, 10, 5)
        assert end == date(2026, 10, 11)

    def test_midweek_resolves_to_the_same_monday_through_sunday(self):
        wednesday = date(2026, 10, 7)
        assert resolve_period("this_week", wednesday) == (date(2026, 10, 5), date(2026, 10, 11))


class TestLastWeek:
    def test_last_week_is_the_seven_days_before_this_week(self):
        today = date(2026, 10, 7)  # Wednesday, this week = Oct 5-11
        start, end = resolve_period("last_week", today)
        assert (start, end) == (date(2026, 9, 28), date(2026, 10, 4))


class TestThisMonth:
    def test_resolves_to_the_full_calendar_month_not_clamped_to_today(self):
        """Checking on the 6th still returns the 1st through the 31st —
        matches GymOps' own reference ("Oct 01, 2026 - Oct 31, 2026")."""
        today = date(2026, 10, 6)
        assert resolve_period("this_month", today) == (date(2026, 10, 1), date(2026, 10, 31))

    def test_february_in_a_leap_year(self):
        today = date(2028, 2, 15)  # 2028 is a leap year
        assert resolve_period("this_month", today) == (date(2028, 2, 1), date(2028, 2, 29))

    def test_february_in_a_non_leap_year(self):
        today = date(2026, 2, 15)
        assert resolve_period("this_month", today) == (date(2026, 2, 1), date(2026, 2, 28))

    def test_thirty_day_month(self):
        today = date(2026, 4, 10)
        assert resolve_period("this_month", today) == (date(2026, 4, 1), date(2026, 4, 30))


class TestLastMonth:
    def test_resolves_to_the_prior_full_calendar_month(self):
        today = date(2026, 10, 6)
        assert resolve_period("last_month", today) == (date(2026, 9, 1), date(2026, 9, 30))

    def test_crosses_a_year_boundary_in_january(self):
        today = date(2027, 1, 15)
        assert resolve_period("last_month", today) == (date(2026, 12, 1), date(2026, 12, 31))


class TestThisYearAndLastYear:
    def test_this_year_is_jan_1_to_dec_31(self):
        assert resolve_period("this_year", date(2026, 6, 1)) == (date(2026, 1, 1), date(2026, 12, 31))

    def test_last_year_crosses_the_year_boundary_correctly(self):
        assert resolve_period("last_year", date(2027, 1, 1)) == (date(2026, 1, 1), date(2026, 12, 31))

    def test_last_year_from_a_leap_year_today(self):
        # 2028 is a leap year; last_year (2027) is not — the function
        # shouldn't accidentally carry a Feb 29 into a non-leap year.
        assert resolve_period("last_year", date(2028, 3, 1)) == (date(2027, 1, 1), date(2027, 12, 31))


class TestCustom:
    def test_valid_range_is_returned_as_given(self):
        f, t = date(2026, 1, 1), date(2026, 3, 31)
        assert resolve_period("custom", date(2026, 10, 6), f, t) == (f, t)

    def test_missing_from_or_to_is_rejected(self):
        with pytest.raises(InvalidPeriod):
            resolve_period("custom", date(2026, 10, 6), None, date(2026, 10, 6))
        with pytest.raises(InvalidPeriod):
            resolve_period("custom", date(2026, 10, 6), date(2026, 10, 6), None)

    def test_from_after_to_is_rejected(self):
        with pytest.raises(InvalidPeriod):
            resolve_period("custom", date(2026, 10, 6), date(2026, 5, 1), date(2026, 1, 1))

    def test_from_equal_to_to_is_a_single_valid_day(self):
        d = date(2026, 5, 1)
        assert resolve_period("custom", date(2026, 10, 6), d, d) == (d, d)

    def test_span_over_the_cap_is_rejected(self):
        with pytest.raises(InvalidPeriod):
            resolve_period("custom", date(2026, 10, 6), date(2020, 1, 1), date(2026, 10, 6))

    def test_span_at_exactly_the_cap_is_accepted(self):
        f = date(2026, 1, 1)
        t = f + timedelta(days=730)
        resolve_period("custom", date(2026, 10, 6), f, t)  # must not raise


class TestUnknownPeriod:
    def test_unknown_period_name_is_rejected(self):
        with pytest.raises(InvalidPeriod):
            resolve_period("bogus", date(2026, 10, 6))


class TestIstDayBoundsToUtc:
    def test_midnight_ist_is_18_30_utc_the_previous_day(self):
        """The headline edge case: a payment made right after IST midnight
        on the 1st must still land inside "this month" in UTC terms —
        IST is UTC+5:30, so IST midnight is 18:30 UTC the day before."""
        start_utc, end_utc = ist_day_bounds_to_utc(date(2026, 10, 1), date(2026, 10, 1))
        assert start_utc == datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)

    def test_11_59pm_ist_on_the_last_day_of_the_month_stays_in_that_month(self):
        """A payment at 23:30 IST on the 31st is 18:00 UTC the same day —
        well inside the UTC end-of-day boundary computed here (18:29:59.999
        UTC on the 31st, i.e. 23:59:59.999999 IST)."""
        start_utc, end_utc = ist_day_bounds_to_utc(date(2026, 10, 31), date(2026, 10, 31))
        payment_instant = datetime(2026, 10, 31, 23, 30, tzinfo=IST).astimezone(timezone.utc)
        assert start_utc <= payment_instant <= end_utc

    def test_the_first_second_of_the_next_month_ist_falls_outside_this_months_range(self):
        _, end_utc = ist_day_bounds_to_utc(date(2026, 10, 1), date(2026, 10, 31))
        first_second_of_november_ist = datetime(2026, 11, 1, 0, 0, 1, tzinfo=IST).astimezone(timezone.utc)
        assert first_second_of_november_ist > end_utc

    def test_end_of_range_is_inclusive_of_the_whole_last_day(self):
        _, end_utc = ist_day_bounds_to_utc(date(2026, 10, 1), date(2026, 10, 31))
        last_moment_ist = datetime(2026, 10, 31, 23, 59, 59, tzinfo=IST).astimezone(timezone.utc)
        assert last_moment_ist <= end_utc


class TestFormatRangeLabel:
    def test_matches_gymops_reference_format(self):
        assert format_range_label(date(2026, 10, 1), date(2026, 10, 31)) == "Oct 01, 2026 - Oct 31, 2026"

    def test_single_day_range(self):
        assert format_range_label(date(2026, 10, 6), date(2026, 10, 6)) == "Oct 06, 2026 - Oct 06, 2026"
