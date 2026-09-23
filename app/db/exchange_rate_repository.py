"""Exact-decimal EUR history with explicit quote/source lookup and atomic upsert.

One authoritative observation exists per (date, EUR, quote). Source is preserved
metadata: reimporting the same source updates it; another source cannot overwrite
it without an explicit future replacement policy. This repository never commits.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.db.models import ExchangeRateORM, utc_now
from app.domain.historical_rates import eur_pair, currency_code, source_code, validate_rate


class ExchangeRateSourceConflict(ValueError):
    """A different provider already owns the observation for this date/pair."""


def decimal_to_db(value: Decimal) -> str:
    return str(value)


def decimal_from_db(value: str) -> Decimal:
    return Decimal(value)


class ExchangeRateRepository:
    model = ExchangeRateORM

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _identity(base_currency, quote_currency, source):
        base, quote = eur_pair(base_currency, quote_currency)
        return base, quote, source_code(source)

    def upsert_rate(self, *, rate_date: date, base_currency: str, quote_currency: str,
                    rate: Decimal, source: str, unit: str = "1") -> ExchangeRateORM:
        base, quote, source = self._identity(base_currency, quote_currency, source)
        validate_rate(rate, unit)
        if type(rate_date) is not date:
            raise ValueError("rate_date must be a calendar date")
        statement = insert(self.model).values(
            rate_date=rate_date, base_currency=base, quote_currency=quote,
            rate=decimal_to_db(rate), unit="1", source=source)
        statement = statement.on_conflict_do_update(
            index_elements=["rate_date", "base_currency", "quote_currency"],
            set_={"rate": decimal_to_db(rate), "unit": "1", "updated_at": utc_now()},
            where=(self.model.source == source) & (
                (self.model.rate != decimal_to_db(rate)) | (self.model.unit != "1")))
        self.db.execute(statement)
        row = self.db.scalar(select(self.model).where(
            self.model.rate_date == rate_date,
            self.model.base_currency == base, self.model.quote_currency == quote
        ).execution_options(populate_existing=True))
        if row.source != source:
            raise ExchangeRateSourceConflict(
                f"{rate_date} {base}/{quote} already belongs to {row.source}; cannot overwrite with {source}")
        return row

    def _series_query(self, *, base_currency, quote_currency, source):
        base, quote, source = self._identity(base_currency, quote_currency, source)
        return select(self.model).where(
            self.model.base_currency == base,
            self.model.quote_currency == quote,
            self.model.source == source)

    def get_exact_rate_row(self, *, rate_date: date, base_currency: str,
                           quote_currency: str, source: str) -> ExchangeRateORM | None:
        return self.db.scalar(self._series_query(base_currency=base_currency,
            quote_currency=quote_currency, source=source).where(self.model.rate_date == rate_date))

    def get_exact_rate(self, *, rate_date: date, base_currency: str,
                       quote_currency: str, source: str) -> Decimal | None:
        row = self.get_exact_rate_row(rate_date=rate_date, base_currency=base_currency,
                                      quote_currency=quote_currency, source=source)
        return None if row is None else decimal_from_db(row.rate)

    def get_rate_date_bounds(self, *, base_currency: str, quote_currency: str,
                             source: str) -> tuple[date | None, date | None]:
        base, quote, source = self._identity(base_currency, quote_currency, source)
        return tuple(self.db.execute(select(func.min(self.model.rate_date), func.max(self.model.rate_date)).where(
            self.model.base_currency == base, self.model.quote_currency == quote,
            self.model.source == source)).one())

    def get_latest_rate_row_on_or_before(self, *, rate_date: date, base_currency: str,
                                         quote_currency: str, source: str) -> ExchangeRateORM | None:
        """Return the latest observed date <= request; no age cap or synthetic rows."""
        return self.db.scalar(self._series_query(base_currency=base_currency,
            quote_currency=quote_currency, source=source).where(self.model.rate_date <= rate_date)
            .order_by(self.model.rate_date.desc()).limit(1))

    def get_latest_rate_on_or_before(self, *, rate_date: date, base_currency: str,
                                     quote_currency: str, source: str) -> Decimal | None:
        row = self.get_latest_rate_row_on_or_before(rate_date=rate_date, base_currency=base_currency,
                                                   quote_currency=quote_currency, source=source)
        return None if row is None else decimal_from_db(row.rate)

    def list_rates(self, *, base_currency: str | None = None, quote_currency: str | None = None,
                    source: str | None = None, limit: int = 100) -> list[ExchangeRateORM]:
        stmt = select(self.model)
        if base_currency is not None:
            stmt = stmt.where(self.model.base_currency == currency_code(base_currency))
        if quote_currency is not None:
            stmt = stmt.where(self.model.quote_currency == currency_code(quote_currency))
        if source is not None:
            stmt = stmt.where(self.model.source == source_code(source))
        return list(self.db.scalars(stmt.order_by(self.model.rate_date.desc(), self.model.quote_currency).limit(limit)))
