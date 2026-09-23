"""ECB startup synchronization: shared planning, dedicated USD storage."""
from datetime import date

from app.core import config
from app.domain.historical_rates import HistoryPolicy
from app.services.ecb_exchange_rate_provider import EcbHistoricalRateProvider
from app.services.eur_usd_exchange_rate_service import EurUsdExchangeRateService
from app.services.historical_exchange_rate_service import HistoricalExchangeRateService, HistoricalSyncResult


class EcbExchangeRateSyncService:
    def __init__(self, db, *, provider_factory=EcbHistoricalRateProvider):
        self.history = HistoricalExchangeRateService(db, exchange_rates=EurUsdExchangeRateService(db))
        self.provider_factory = provider_factory

    def synchronize(self, *, today: date | None = None) -> HistoricalSyncResult:
        end = today or date.today()
        start = config.ECB_EXCHANGE_RATE_START_DATE
        if start > end:
            raise ValueError("ECB_EXCHANGE_RATE_START_DATE must not be after today")
        return self.history.synchronize(
            quote_currency="USD", provider=self.provider_factory(), start_date=start, end_date=end,
            history_policy=HistoryPolicy(
                lower_boundary_tolerance_days=config.ECB_EXCHANGE_RATE_LOWER_BOUNDARY_TOLERANCE_DAYS))
