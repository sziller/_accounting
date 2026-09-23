"""Shared exact-decimal persistence and lookup; provider identity is explicit."""
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

from app.db.exchange_rate_repository import ExchangeRateRepository
from app.db.models import ExchangeRateORM


class ExchangeRateService:
    repository_class = ExchangeRateRepository

    @property
    def table_name(self):
        return self.repository.model.__tablename__

    def __init__(self, db: Session):
        self.db = db
        self.repository = self.repository_class(db=db)

    def upsert_rate(self, *, rate_date: date, base_currency: str, quote_currency: str,
                    rate: Decimal, source: str, unit: str = "1") -> ExchangeRateORM:
        """Keep per-observation commits; rollback a failed write before reuse."""
        try:
            row = self.repository.upsert_rate(rate_date=rate_date, base_currency=base_currency,
                quote_currency=quote_currency, rate=rate, unit=unit, source=source)
            self.db.commit()
            self.db.refresh(row)
            return row
        except Exception:
            self.db.rollback()
            raise

    def get_exact_rate(self, *, rate_date: date, base_currency: str,
                       quote_currency: str, source: str) -> Decimal | None:
        return self.repository.get_exact_rate(rate_date=rate_date, base_currency=base_currency,
                                              quote_currency=quote_currency, source=source)

    def get_latest_rate_on_or_before(self, *, rate_date: date, base_currency: str,
                                     quote_currency: str, source: str) -> ExchangeRateORM | None:
        """Existing inclusive fallback: latest observed date <= request, no age cap."""
        return self.repository.get_latest_rate_row_on_or_before(rate_date=rate_date,
            base_currency=base_currency, quote_currency=quote_currency, source=source)

    def get_rate_date_bounds(self, *, base_currency: str, quote_currency: str,
                             source: str) -> tuple[date | None, date | None]:
        return self.repository.get_rate_date_bounds(base_currency=base_currency,
                                                    quote_currency=quote_currency, source=source)

    def list_rates(self, *, base_currency: str | None = None, quote_currency: str | None = None,
                    source: str | None = None, limit: int = 100) -> list[ExchangeRateORM]:
        return self.repository.list_rates(base_currency=base_currency, quote_currency=quote_currency,
                                          source=source, limit=limit)
