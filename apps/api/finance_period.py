"""Finance period resolution — pure, IST-based, unit-tested directly (no
DB). dashboard.py turns the resulting IST calendar-date range into UTC
instants for querying payment.created_at (a timestamptz).

Weeks start on Monday — not a documented GymOps requirement (their
reference screenshot didn't show a week boundary), just the least
surprising default (ISO 8601, and date.weekday()'s own Monday=0) absent one.
"Today" and "Last Year" are additions beyond GymOps' observed list, at the
user's request.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

PERIODS = (
    "today",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_year",
    "last_year",
    "custom",
)

# ~2 years — generous for a legitimate "compare year over year" custom
# range, tight enough to stop an accidental all-time query from the finance
# summary's RPC scanning a tenant's entire payment history every request.
MAX_CUSTOM_RANGE_DAYS = 730


class InvalidPeriod(ValueError):
    """Raised by resolve_period for a bad period name or an invalid custom
    range — the route turns this into a 400 with the message as-is."""


def today_ist() -> date:
    return datetime.now(IST).date()


def _month_end(first_of_month: date) -> date:
    next_month = (
        date(first_of_month.year + 1, 1, 1)
        if first_of_month.month == 12
        else date(first_of_month.year, first_of_month.month + 1, 1)
    )
    return next_month - timedelta(days=1)


def resolve_period(
    period: str,
    today: date,
    custom_from: date | None = None,
    custom_to: date | None = None,
) -> tuple[date, date]:
    """(from, to) as an inclusive IST calendar-date range, both ends
    included. Full calendar periods, not clamped to `today` — "This Month"
    on the 6th still resolves to the 1st through the 30th/31st, same as
    GymOps' own reference screenshot ("Oct 01, 2026 - Oct 31, 2026"); dates
    after today simply have no payments yet, which is correct, not a bug."""
    if period == "today":
        return today, today

    if period == "this_week":
        start = today - timedelta(days=today.weekday())  # Monday
        return start, start + timedelta(days=6)

    if period == "last_week":
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        return start, start + timedelta(days=6)

    if period == "this_month":
        start = today.replace(day=1)
        return start, _month_end(start)

    if period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end

    if period == "this_year":
        return date(today.year, 1, 1), date(today.year, 12, 31)

    if period == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)

    if period == "custom":
        if custom_from is None or custom_to is None:
            raise InvalidPeriod("custom period requires both from and to")
        if custom_from > custom_to:
            raise InvalidPeriod("from must be on or before to")
        if (custom_to - custom_from).days > MAX_CUSTOM_RANGE_DAYS:
            raise InvalidPeriod(f"custom range cannot exceed {MAX_CUSTOM_RANGE_DAYS} days")
        return custom_from, custom_to

    raise InvalidPeriod(f"unknown period {period!r} — expected one of {PERIODS}")


def ist_day_bounds_to_utc(start: date, end: date) -> tuple[datetime, datetime]:
    """The full IST calendar-day range [start 00:00:00, end 23:59:59.999999]
    converted to UTC instants, for filtering a timestamptz column. Kept
    separate from the plain `date` boundaries (used as-is for expense_date,
    which has no time/zone component to convert) — collapsing these into
    one pair and casting would silently shift by IST's +5:30 offset."""
    start_utc = datetime.combine(start, time.min, tzinfo=IST).astimezone(timezone.utc)
    end_utc = datetime.combine(end, time.max, tzinfo=IST).astimezone(timezone.utc)
    return start_utc, end_utc


def format_range_label(start: date, end: date) -> str:
    """"Oct 01, 2026 - Oct 31, 2026" — matching GymOps' reference display."""
    fmt = "%b %d, %Y"
    return f"{start.strftime(fmt)} - {end.strftime(fmt)}"
