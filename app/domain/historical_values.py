"""Small, tax-independent change-point lookup for source-controlled parameters."""
from collections.abc import Mapping
from typing import TypeVar

T = TypeVar('T')


class HistoricalValueUnavailable(ValueError):
    """No value is declared effective for the requested year."""


def resolve_historical_value(history: Mapping[int, T], tax_year: int) -> T:
    """Return the latest effective value at/before tax_year without mutation."""
    effective_year = max((year for year in history if year <= tax_year), default=None)
    if effective_year is None:
        raise HistoricalValueUnavailable(f'No historical value is defined for tax year {tax_year}.')
    return history[effective_year]
