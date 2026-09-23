"""Dedicated USD storage using the established exact-decimal upsert semantics."""
from app.db.exchange_rate_repository import ExchangeRateRepository
from app.db.models import EurUsdExchangeRateORM


class EurUsdExchangeRateRepository(ExchangeRateRepository):
    model = EurUsdExchangeRateORM

    @staticmethod
    def _identity(base_currency, quote_currency, source):
        identity = ExchangeRateRepository._identity(base_currency, quote_currency, source)
        if identity[1] != "USD":
            raise ValueError("EUR/USD storage requires quote currency USD")
        return identity
