"""Provider-neutral EUR quote observations: always 1 EUR = rate quote units."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Iterable, Protocol


def currency_code(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value.strip().upper()):
        raise ValueError("Currency must be a three-letter ISO-style code")
    return value.strip().upper()


def eur_pair(base_currency: str, quote_currency: str) -> tuple[str, str]:
    base, quote = currency_code(base_currency), currency_code(quote_currency)
    if base != "EUR" or quote == "EUR":
        raise ValueError("Historical rate orientation must be 1 EUR = X non-EUR quote currency")
    return base, quote


def source_code(source: str) -> str:
    if not isinstance(source, str) or not source.strip() or len(source.strip()) > 32:
        raise ValueError("An explicit provider source (1–32 characters) is required")
    return source.strip().upper()


def validate_rate(rate: Decimal, unit: str) -> None:
    if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0 or len(str(rate)) > 64:
        raise ValueError("Rate must be a positive finite Decimal fitting the rate column")
    try:
        valid_unit = isinstance(unit, str) and Decimal(unit).is_finite() and Decimal(unit) == 1
    except InvalidOperation:
        valid_unit = False
    if not valid_unit:
        raise ValueError("Observations must quote exactly 1 EUR (unit=1); normalize provider units first")


@dataclass(frozen=True)
class HistoricalRateObservation:
    rate_date: date
    base_currency: str
    quote_currency: str
    rate: Decimal
    unit: str
    source: str


@dataclass(frozen=True)
class HistoryPolicy:
    """Provider publication/request policy, not synthesized observation dates."""
    lower_boundary_tolerance_days: int = 0
    chunk_by_year: bool = False


class HistoricalRateProvider(Protocol):
    source: str
    quote_currencies: frozenset[str]
    history_policy: HistoryPolicy

    def fetch_rates(self, *, quote_currency: str, start_date: date,
                    end_date: date) -> Iterable[HistoricalRateObservation]: ...
