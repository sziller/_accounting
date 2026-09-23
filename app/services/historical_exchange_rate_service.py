"""Provider-neutral history planning, observation validation, and persistence."""
from dataclasses import dataclass
from datetime import date, timedelta
import logging

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.historical_rates import (
    HistoricalRateObservation, HistoricalRateProvider, eur_pair, source_code, validate_rate,
)
from app.services.date_ranges import iter_year_chunks
from app.services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger(__name__)


class ExchangeRateSchemaError(RuntimeError):
    """Required local exchange-rate storage is unavailable."""


class ExchangeRateProviderError(RuntimeError):
    """Fetching/parsing/validating a provider response failed, not the database."""


@dataclass(frozen=True)
class HistoricalSyncResult:
    required_start_date: date
    required_end_date: date
    earliest_before: date | None
    latest_before: date | None
    requested_ranges: tuple[tuple[date, date], ...]
    processed_count: int


class HistoricalExchangeRateService:
    def __init__(self, db: Session, *, exchange_rates=None):
        self.db = db
        self.exchange_rates = exchange_rates if exchange_rates is not None else ExchangeRateService(db=db)

    @staticmethod
    def _series(quote_currency, provider):
        _, quote = eur_pair("EUR", quote_currency)
        source = source_code(provider.source)
        supported = {eur_pair("EUR", code)[1] for code in provider.quote_currencies}
        if quote not in supported:
            raise ValueError(f"Provider {source} does not support EUR/{quote}")
        return quote, source

    def import_rates(self, *, quote_currency: str, provider: HistoricalRateProvider,
                     start_date: date, end_date: date) -> int:
        """Import exactly one requested interval; keep existing per-row commits.

        Validate the complete response before persisting any of it. Database errors
        stay database errors; later request failures do not erase earlier commits.
        """
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        quote, source = self._series(quote_currency, provider)
        observations = []
        try:
            for item in provider.fetch_rates(quote_currency=quote, start_date=start_date, end_date=end_date):
                base, item_quote = eur_pair(item.base_currency, item.quote_currency)
                if item_quote != quote or source_code(item.source) != source:
                    raise ValueError("Provider observation does not match the requested currency/source")
                if type(item.rate_date) is not date or not start_date <= item.rate_date <= end_date:
                    raise ValueError("Provider observation date is outside the requested interval")
                validate_rate(item.rate, item.unit)
                observations.append(HistoricalRateObservation(item.rate_date, base, quote, item.rate, "1", source))
        except SQLAlchemyError:
            raise
        except Exception as exc:
            raise ExchangeRateProviderError(f"{source} EUR/{quote} response failed: {exc}") from exc
        for item in observations:
            self.exchange_rates.upsert_rate(
                rate_date=item.rate_date, base_currency="EUR", quote_currency=quote,
                rate=item.rate, unit="1", source=source)
        return len(observations)

    def synchronize(self, *, quote_currency: str, provider: HistoricalRateProvider,
                    start_date: date, end_date: date | None = None, history_policy=None) -> HistoricalSyncResult:
        end = end_date or date.today()
        if start_date > end:
            raise ValueError("start_date must not be after end_date")
        quote, source = self._series(quote_currency, provider)
        policy = history_policy if history_policy is not None else provider.history_policy
        if policy.lower_boundary_tolerance_days < 0:
            raise ValueError("Lower boundary tolerance must be nonnegative")
        if not inspect(self.db.get_bind()).has_table(self.exchange_rates.table_name):
            raise ExchangeRateSchemaError(f"Required SQLite table {self.exchange_rates.table_name!r} does not exist after init_db()")
        earliest, latest = self.exchange_rates.get_rate_date_bounds(
            base_currency="EUR", quote_currency=quote, source=source)
        ranges = self.required_ranges(
            required_start=start_date, required_end=end, earliest=earliest, latest=latest,
            lower_boundary_tolerance_days=policy.lower_boundary_tolerance_days)
        processed = 0
        for first, last in ranges:
            chunks = iter_year_chunks(first, last) if policy.chunk_by_year else [(first, last)]
            for chunk_start, chunk_end in chunks:
                logger.info("%s EUR/%s history request: %s -> %s", source, quote, chunk_start, chunk_end)
                processed += self.import_rates(quote_currency=quote, provider=provider,
                                               start_date=chunk_start, end_date=chunk_end)
        return HistoricalSyncResult(start_date, end, earliest, latest, tuple(ranges), processed)

    @staticmethod
    def required_ranges(*, required_start, required_end, earliest, latest,
                        lower_boundary_tolerance_days=0):
        if earliest is None or latest is None:
            return [(required_start, required_end)]
        ranges = []
        if earliest > required_start + timedelta(days=lower_boundary_tolerance_days):
            ranges.append((required_start, min(earliest, required_end)))
        ranges.append((max(required_start, min(latest, required_end)), required_end))
        merged = []
        for start, end in sorted(ranges):
            if start > end:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged
