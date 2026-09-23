from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core import config
from scripts.import_mnb_rates import build_parser

from app.db.models import Base, ExchangeRateORM
from app.services.exchange_rate_service import ExchangeRateService
from app.services.mnb_exchange_rate_provider import MnbHistoricalRateProvider, ImportedMnbRate
from app.services.mnb_exchange_rate_sync_service import (
    ExchangeRateSchemaError,
    MnbExchangeRateProviderError,
    MnbExchangeRateSyncService,
)


TODAY = date(2026, 8, 23)


class RecordingProvider(MnbHistoricalRateProvider):
    calls: list[tuple[date, date]] = []
    fail = False

    def fetch_rates(self, *, quote_currency: str, start_date: date, end_date: date):
        assert quote_currency == "HUF"
        type(self).calls.append((start_date, end_date))
        if type(self).fail:
            raise ConnectionError("MNB unavailable")
        return [ImportedMnbRate(day, "EUR", "HUF", Decimal("400.00"), "1")
                for day in (start_date, end_date)]


class MnbExchangeRateSyncServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        setting = patch.object(config, "MNB_EXCHANGE_RATE_START_DATE", date(2021, 1, 1))
        setting.start()
        self.addCleanup(setting.stop)
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        RecordingProvider.calls = []
        RecordingProvider.fail = False

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def add_rate(self, rate_date: date, *, source: str = "MNB") -> None:
        ExchangeRateService(self.db).upsert_rate(
            rate_date=rate_date,
            base_currency="EUR",
            quote_currency="HUF",
            rate=Decimal("399.00"),
            source=source,
        )

    def sync(self):
        return MnbExchangeRateSyncService(
            self.db, provider_factory=RecordingProvider
        ).synchronize(today=TODAY)

    def test_empty_dataset_bootstraps_full_window_in_year_chunks(self) -> None:
        result = self.sync()
        self.assertEqual(result.requested_ranges, ((date(2021, 1, 1), TODAY),))
        self.assertEqual(RecordingProvider.calls[0], (date(2021, 1, 1), date(2021, 12, 31)))
        self.assertEqual(RecordingProvider.calls[-1], (date(2026, 1, 1), TODAY))

    def test_custom_config_start_is_used_by_sync_and_cli(self) -> None:
        configured_start = date(2023, 6, 15)
        with patch.object(config, "MNB_EXCHANGE_RATE_START_DATE", configured_start):
            result = self.sync()
            self.assertEqual(result.required_start_date, configured_start)
            self.assertEqual(RecordingProvider.calls[0][0], configured_start)
            self.assertEqual(build_parser().parse_args([]).start, configured_start)
            self.assertEqual(build_parser().parse_args(["--start", "2020-02-01"]).start, date(2020, 2, 1))

    def test_refresh_does_not_start_before_configured_limit(self) -> None:
        self.add_rate(date(2020, 1, 1))
        self.assertEqual(self.sync().requested_ranges, ((date(2021, 1, 1), TODAY),))

    def test_future_start_is_rejected_before_import(self) -> None:
        with patch.object(config, "MNB_EXCHANGE_RATE_START_DATE", date(2099, 1, 1)):
            with self.assertRaisesRegex(ValueError, "must not be after today"):
                self.sync()
        self.assertEqual(RecordingProvider.calls, [])

    def test_recent_only_data_backfills_and_refreshes_without_overlap(self) -> None:
        self.add_rate(date(2025, 1, 2))
        self.add_rate(date(2026, 8, 20))
        result = self.sync()
        self.assertEqual(
            result.requested_ranges,
            (
                (date(2021, 1, 1), date(2025, 1, 2)),
                (date(2026, 8, 20), TODAY),
            ),
        )

    def test_existing_historical_coverage_only_refreshes_latest(self) -> None:
        self.add_rate(date(2021, 1, 4))
        self.add_rate(date(2026, 8, 20))
        result = self.sync()
        self.assertEqual(result.requested_ranges, ((date(2026, 8, 20), TODAY),))

    def test_lower_boundary_tolerance_includes_tenth_day_after_start(self) -> None:
        self.add_rate(date(2021, 1, 11))
        self.add_rate(date(2026, 8, 20))
        result = self.sync()
        self.assertEqual(result.requested_ranges, ((date(2026, 8, 20), TODAY),))

    def test_later_january_start_requires_backfill(self) -> None:
        self.add_rate(date(2021, 1, 20))
        self.add_rate(date(2026, 8, 20))
        result = self.sync()
        self.assertEqual(
            result.requested_ranges,
            (
                (date(2021, 1, 1), date(2021, 1, 20)),
                (date(2026, 8, 20), TODAY),
            ),
        )

    def test_february_start_requires_backfill(self) -> None:
        self.add_rate(date(2021, 2, 1))
        self.add_rate(date(2026, 8, 20))
        result = self.sync()
        self.assertEqual(
            result.requested_ranges,
            (
                (date(2021, 1, 1), date(2021, 2, 1)),
                (date(2026, 8, 20), TODAY),
            ),
        )

    def test_late_same_year_start_requires_backfill(self) -> None:
        self.add_rate(date(2021, 11, 15))
        self.add_rate(date(2026, 8, 20))
        result = self.sync()
        self.assertEqual(
            result.requested_ranges,
            (
                (date(2021, 1, 1), date(2021, 11, 15)),
                (date(2026, 8, 20), TODAY),
            ),
        )

    def test_repeated_weekend_sync_is_idempotent(self) -> None:
        self.add_rate(date(2021, 1, 4))
        self.add_rate(date(2026, 8, 21))
        self.sync()
        self.sync()
        duplicate_count = self.db.scalar(
            select(func.count()).select_from(ExchangeRateORM).where(
                ExchangeRateORM.rate_date == date(2026, 8, 21),
                ExchangeRateORM.base_currency == "EUR",
                ExchangeRateORM.quote_currency == "HUF",
                ExchangeRateORM.source == "MNB",
            )
        )
        self.assertEqual(duplicate_count, 1)

    def test_provider_failure_is_distinct_and_preserves_existing_rows(self) -> None:
        self.add_rate(date(2026, 8, 21))
        RecordingProvider.fail = True
        with self.assertRaises(MnbExchangeRateProviderError):
            self.sync()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ExchangeRateORM)), 1)

    def test_missing_table_is_fatal_schema_error(self) -> None:
        Base.metadata.drop_all(self.engine)
        with self.assertRaises(ExchangeRateSchemaError):
            self.sync()

    def test_unrelated_rates_do_not_satisfy_mnb_eur_huf_coverage(self) -> None:
        self.add_rate(date(2020, 1, 2), source="OTHER")
        result = self.sync()
        self.assertEqual(result.requested_ranges, ((date(2021, 1, 1), TODAY),))


if __name__ == "__main__":
    unittest.main()
