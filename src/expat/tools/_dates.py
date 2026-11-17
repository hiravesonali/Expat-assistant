"""Small calendar helpers. The standard library has no "add months" (unlike date-fns `addMonths`).

We deliberately avoid python-dateutil: it is not a declared dependency, and these three functions are easy
to read and test.
"""

import calendar
from datetime import date


def shift_month(year: int, month: int, months: int) -> tuple[int, int]:
    """(year, month) moved by `months` (may be negative). Month arithmetic in base 12."""
    index = year * 12 + (month - 1) + months
    return index // 12, index % 12 + 1


def last_day_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def add_months(day: date, months: int) -> date:
    """Same day-of-month `months` later, clamped to the month end (Jan 31 + 1 month = Feb 28/29).

    Clamping matches § 188 Abs. 3 BGB: if the target month lacks that day, the period ends on its last day.
    """
    year, month = shift_month(day.year, day.month, months)
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def full_years_between(start: date, end: date) -> int:
    """Completed years from `start` to `end` (age-style: the anniversary day counts as completed)."""
    return end.year - start.year - ((end.month, end.day) < (start.month, start.day))
