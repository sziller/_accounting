"""Reusable inclusive date-range helpers for exchange-rate imports."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta


def iter_year_chunks(start_date: date, end_date: date) -> Iterator[tuple[date, date]]:
    """Split an inclusive interval into stable calendar-year request chunks.

    Each yielded pair is inclusive and stays within one calendar year.  A
    range such as 2025-10-15 through 2026-02-10 therefore yields
    2025-10-15..2025-12-31 and 2026-01-01..2026-02-10.  An inverted interval
    yields no chunks.  MNB bootstrap and backfill operations use this helper to
    avoid one unnecessarily large SOAP request, and the manual CLI shares it
    to keep chunking behavior consistent.
    """
    current_start = start_date
    while current_start <= end_date:
        current_end = min(date(current_start.year, 12, 31), end_date)
        yield current_start, current_end
        current_start = current_end + timedelta(days=1)
