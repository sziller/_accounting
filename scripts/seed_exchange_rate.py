# scripts/seed_exchange_rate.py

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.db.database import create_db_session, init_db
from app.services.exchange_rate_service import ExchangeRateService


def main() -> None:
    """=== script function ====
    Insert one manual EUR/HUF exchange-rate row for local conversion testing.
    === by Sziller & ChatGPT ==="""
    init_db()

    db = create_db_session()

    try:
        service = ExchangeRateService(db=db)

        row = service.upsert_rate(
            rate_date=date(2026, 5, 9),
            base_currency="EUR",
            quote_currency="HUF",
            rate=Decimal("390.00"),
            unit="1",
            source="MNB",
        )

        print(
            f"Saved exchange rate: "
            f"{row.rate_date} {row.base_currency}/{row.quote_currency} = {row.rate}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
