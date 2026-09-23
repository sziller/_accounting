"""EUR/USD persistence and exact/latest-on-or-before lookup."""
from app.db.eur_usd_exchange_rate_repository import EurUsdExchangeRateRepository
from app.services.exchange_rate_service import ExchangeRateService


class EurUsdExchangeRateService(ExchangeRateService):
    repository_class = EurUsdExchangeRateRepository
