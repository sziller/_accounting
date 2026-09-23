"""Compatibility import entry points; MNB fetches, shared EUR history persists."""
from dataclasses import dataclass
from datetime import date
from sqlalchemy.orm import Session

from app.domain.historical_rates import currency_code
from app.services.historical_exchange_rate_service import HistoricalExchangeRateService
from app.services.mnb_exchange_rate_provider import (
    ImportedMnbRate, MNB_WSDL_URL, MnbHistoricalRateProvider,
)


@dataclass(frozen=True)
class MnbImportResult:
    requested_start_date: date
    requested_end_date: date
    currency: str
    imported_count: int
    skipped_count: int


class MnbExchangeRateImportService(MnbHistoricalRateProvider):
    """Keep the manual CLI API, delegating persistence to the generic service.

    `currency` in the old import_rates signature is the MNB-requested BASE,
    not the quote currency. Only EUR is accepted; USD would mean USD/HUF.
    """
    def __init__(self, db: Session):
        self.db = db
        self.history = HistoricalExchangeRateService(db)

    def import_eur_huf_rates(self, *, start_date: date, end_date: date) -> MnbImportResult:
        return self.import_rates(start_date=start_date, end_date=end_date, currency="EUR")

    def import_rates(self, *, start_date: date, end_date: date, currency: str) -> MnbImportResult:
        if currency_code(currency) != "EUR":
            raise ValueError("MNB import only supports EUR/HUF; currency is the base, not a EUR quote currency")
        count = self.history.import_rates(quote_currency="HUF", provider=self,
                                          start_date=start_date, end_date=end_date)
        return MnbImportResult(start_date, end_date, "EUR", count, 0)
