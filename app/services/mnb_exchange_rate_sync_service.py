"""Startup compatibility wrapper selecting MNB/HUF and its configured window."""
from datetime import date
from typing import Callable
from sqlalchemy.orm import Session

from app.core import config
from app.services.historical_exchange_rate_service import (
    ExchangeRateSchemaError,
    ExchangeRateProviderError as MnbExchangeRateProviderError,
    HistoricalSyncResult as MnbSyncResult,
    HistoricalExchangeRateService,
)
from app.services.mnb_exchange_rate_provider import MnbHistoricalRateProvider, LOWER_BOUNDARY_TOLERANCE_DAYS


class MnbExchangeRateSyncService:
    def __init__(self, db: Session, *, provider_factory: Callable[[], MnbHistoricalRateProvider] = MnbHistoricalRateProvider):
        self.history = HistoricalExchangeRateService(db)
        self.provider_factory = provider_factory

    def synchronize(self, *, today: date | None = None) -> MnbSyncResult:
        end = today or date.today()
        start = config.MNB_EXCHANGE_RATE_START_DATE
        if start > end:
            raise ValueError("MNB_EXCHANGE_RATE_START_DATE must not be after today")
        return self.history.synchronize(quote_currency="HUF", provider=self.provider_factory(),
                                        start_date=start, end_date=end)

    @staticmethod
    def _required_ranges(**kwargs):
        return HistoricalExchangeRateService.required_ranges(
            **kwargs, lower_boundary_tolerance_days=LOWER_BOUNDARY_TOLERANCE_DAYS)
