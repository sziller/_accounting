"""Shared local-only EUR conversion dispatch; no collection or persistence."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
from app.services.exchange_rate_service import ExchangeRateService
from app.services.eur_usd_exchange_rate_service import EurUsdExchangeRateService


class LocalCurrencyConversion:
    sources = {"HUF": "MNB", "USD": "ECB"}

    def __init__(self, db):
        self.huf = ExchangeRateService(db)
        self.usd = EurUsdExchangeRateService(db)

    def supports(self, original, common):
        return common == "EUR" and original in self.sources

    def lookup(self, original, common, day):
        if not self.supports(original, common):
            raise ValueError(f"Unsupported conversion: {original} → {common}.")
        service = self.huf if original == "HUF" else self.usd
        return service.get_latest_rate_on_or_before(
            rate_date=day, base_currency="EUR", quote_currency=original,
            source=self.sources[original])

    @staticmethod
    def calculate(amount, rate, *, precision=None):
        # Keep caller's established Decimal precision; AR uses 64 digits.
        with localcontext() as context:
            if precision is not None:
                context.prec = precision
            return (Decimal(amount) / Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
