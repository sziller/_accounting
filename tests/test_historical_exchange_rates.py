"""EUR/* contract with deterministic providers; no real USD datasource/network."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from decimal import Decimal
import html
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch, Mock

from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core import config
from app.db import database
from app.db.exchange_rate_repository import ExchangeRateRepository, ExchangeRateSourceConflict
from app.db.exchange_rate_upgrade import upgrade_exchange_rate_identity
from app.db.models import Base, ExchangeRateORM
from app.domain.historical_rates import HistoricalRateObservation, HistoryPolicy
from app.services.exchange_rate_service import ExchangeRateService
from app.services.historical_exchange_rate_service import HistoricalExchangeRateService, ExchangeRateProviderError
from app.services.mnb_exchange_rate_import_service import MnbExchangeRateImportService
from app.services.mnb_exchange_rate_provider import MnbHistoricalRateProvider
from app.services.mnb_exchange_rate_sync_service import MnbExchangeRateSyncService

START, FRIDAY, SUNDAY = date(2026, 9, 1), date(2026, 9, 4), date(2026, 9, 6)
EXACT_USD = Decimal("1.1750123456789012345678901234567890")


def observation(day=START, *, quote="USD", source="TEST-USD", rate=EXACT_USD):
    return HistoricalRateObservation(day, "EUR", quote, rate, "1", source)


class FixtureProvider:
    history_policy = HistoryPolicy()

    def __init__(self, items, *, source="TEST-USD", quote="USD"):
        self.items = items
        self.source = source
        self.quote_currencies = frozenset({quote})
        self.calls = []

    def fetch_rates(self, *, quote_currency, start_date, end_date):
        self.calls.append((quote_currency, start_date, end_date))
        return [item for item in self.items if start_date <= item.rate_date <= end_date]


class HistoricalExchangeRatesTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(directory.name) / 'fx.db'}",
                                    connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.history = HistoricalExchangeRateService(self.db)
        self.rates = ExchangeRateService(self.db)
        self.provider = FixtureProvider([observation(), observation(FRIDAY)])

    def imported(self, provider=None, quote="USD"):
        return self.history.import_rates(quote_currency=quote, provider=provider or self.provider,
                                         start_date=START, end_date=SUNDAY)

    def rows(self):
        return list(self.db.scalars(select(ExchangeRateORM).order_by(ExchangeRateORM.quote_currency, ExchangeRateORM.rate_date)))

    def test_usd_sync_orientation_precision_and_no_weekend_synthesis(self):
        result = self.history.synchronize(quote_currency=" usd ", provider=self.provider,
                                           start_date=START, end_date=SUNDAY)
        self.assertEqual(result.processed_count, 2)
        self.assertEqual(self.provider.calls, [("USD", START, SUNDAY)])
        self.assertEqual([row.rate_date for row in self.rows()], [START, FRIDAY])
        for row in self.rows():
            self.assertEqual((row.base_currency, row.quote_currency, row.unit, row.source), ("EUR", "USD", "1", "TEST-USD"))
            self.assertEqual(row.rate, str(EXACT_USD))
            self.assertEqual(Decimal(row.rate), EXACT_USD)
        self.assertIsNone(self.rates.get_exact_rate(rate_date=SUNDAY, base_currency="EUR", quote_currency="USD", source="TEST-USD"))
        latest = self.rates.get_latest_rate_on_or_before(rate_date=SUNDAY, base_currency="EUR", quote_currency="USD", source="TEST-USD")
        self.assertEqual(latest.rate_date, FRIDAY)
        self.assertEqual(self.history.synchronize(quote_currency="USD", provider=self.provider,
            start_date=START, end_date=SUNDAY).requested_ranges, ((FRIDAY, SUNDAY),))
        self.assertEqual(len(self.rows()), 2)

    def test_huf_usd_coexistence_both_import_directions_and_lookups(self):
        huf = FixtureProvider([observation(quote="HUF", source="TEST-HUF", rate=Decimal("392.10"))], source="TEST-HUF", quote="HUF")
        self.imported(huf, "HUF")
        huf_id = self.rows()[0].id
        self.imported()
        self.assertEqual(len(self.rows()), 3)
        huf.items = [observation(quote="HUF", source="TEST-HUF", rate=Decimal("393.20"))]
        self.imported(huf, "HUF")
        self.assertEqual(self.rates.get_exact_rate(rate_date=START, base_currency="EUR", quote_currency="USD", source="TEST-USD"), EXACT_USD)
        self.provider.items = [observation(rate=Decimal("1.1684")), observation(FRIDAY)]
        self.imported()
        repository = ExchangeRateRepository(self.db)
        self.assertEqual(repository.get_exact_rate(rate_date=START, base_currency="eur", quote_currency=" huf ", source="test-huf"), Decimal("393.20"))
        self.assertEqual(repository.get_latest_rate_on_or_before(rate_date=SUNDAY, base_currency="EUR", quote_currency="USD", source="TEST-USD"), EXACT_USD)
        self.assertEqual(repository.get_exact_rate_row(rate_date=START, base_currency="EUR", quote_currency="HUF", source="TEST-HUF").id, huf_id)
        self.assertIsNone(repository.get_latest_rate_on_or_before(rate_date=SUNDAY, base_currency="EUR", quote_currency="USD", source="TEST-HUF"))
        self.assertEqual(repository.get_rate_date_bounds(base_currency="EUR", quote_currency="HUF", source="TEST-HUF"), (START, START))

    def test_reimport_updates_same_row_preserving_id_and_created_at(self):
        self.imported()
        before = self.rows()[0]
        identity, created = before.id, before.created_at
        self.provider.items = [observation(rate=Decimal("1.168400"))]
        self.assertEqual(self.imported(), 1)
        updated = self.rows()[0].updated_at
        self.assertEqual(self.imported(), 1)
        after = self.rows()[0]
        self.assertEqual((after.id, after.created_at, after.rate), (identity, created, "1.168400"))
        self.assertEqual(after.updated_at, updated)
        self.assertEqual(len(self.rows()), 2)

    def test_existing_provider_cannot_be_silently_replaced(self):
        self.imported()
        replacement = FixtureProvider([observation(source="DIFFERENT")], source="DIFFERENT")
        with self.assertRaisesRegex(ExchangeRateSourceConflict, "already belongs to TEST-USD"):
            self.imported(replacement)
        self.assertEqual(len(self.rows()), 2)
        self.assertTrue(all(row.source == "TEST-USD" for row in self.rows()))
        # Pair/day uniqueness is enforced by SQLite as well as the service.
        self.db.add(ExchangeRateORM(rate_date=START, base_currency="EUR", quote_currency="USD",
                                   source="DIFFERENT", rate="9", unit="1"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_invalid_provider_currency_requests_never_fall_back(self):
        for quote in ("HUF", "EUR", "EURUSD", "US", "US1", "ZZZ"):
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                self.imported(quote=quote)
        self.assertEqual(self.provider.calls, [])
        with patch("app.services.mnb_exchange_rate_provider.Client") as client:
            with self.assertRaisesRegex(ValueError, "does not support EUR/USD"):
                self.imported(MnbHistoricalRateProvider(), "USD")
            with self.assertRaises(ValueError):
                MnbHistoricalRateProvider().fetch_rates(quote_currency="USD", start_date=START, end_date=SUNDAY)
            with self.assertRaises(ValueError):
                MnbExchangeRateImportService(self.db).import_rates(currency="USD", start_date=START, end_date=SUNDAY)
            client.assert_not_called()
        with self.assertRaises(TypeError):
            self.rates.get_latest_rate_on_or_before(rate_date=SUNDAY, base_currency="EUR", source="MNB")
        with self.assertRaises(TypeError):
            self.rates.upsert_rate(rate_date=START, base_currency="EUR", quote_currency="USD", rate=EXACT_USD)
        self.assertEqual(self.rows(), [])

    def test_invalid_observations_fail_before_any_chunk_writes(self):
        huf = FixtureProvider([observation(quote="HUF", source="TEST-HUF")], source="TEST-HUF", quote="HUF")
        self.imported(huf, "HUF")
        invalid = [replace(observation(), base_currency="USD", quote_currency="EUR"),
                   replace(observation(), quote_currency="HUF"), replace(observation(), source="MNB"),
                   replace(observation(), unit="100"), replace(observation(), rate_date=date(2026, 8, 31)),
                   replace(observation(), rate_date=date(2026, 9, 7))]
        invalid += [replace(observation(), rate=value) for value in
                    (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.175, "1.175")]
        for item in invalid:
            with self.subTest(item=item):
                provider = FixtureProvider([])
                provider.fetch_rates = Mock(return_value=[observation(), item])
                with self.assertRaises(ExchangeRateProviderError):
                    self.imported(provider)
                self.assertEqual([(row.quote_currency, row.source) for row in self.rows()], [("HUF", "TEST-HUF")])
        with self.assertRaises(ValueError):
            self.rates.upsert_rate(rate_date=START, base_currency="USD", quote_currency="HUF", rate=EXACT_USD, source="TEST")
        with self.assertRaises(ValueError):
            self.rates.upsert_rate(rate_date=START, base_currency="EUR", quote_currency="USD", rate=1.175, source="TEST")

    def test_provider_failure_keeps_other_currency_and_storage_errors_are_distinct(self):
        self.imported()
        provider = FixtureProvider([], quote="HUF", source="TEST-HUF")
        provider.fetch_rates = Mock(side_effect=ConnectionError("offline"))
        with self.assertRaises(ExchangeRateProviderError):
            self.imported(provider, "HUF")
        self.assertEqual(len(self.rows()), 2)
        with patch.object(self.history.exchange_rates, "upsert_rate", side_effect=OperationalError("db", {}, Exception())):
            with self.assertRaises(OperationalError):
                self.imported()

    def test_normalized_currency_and_source_identifiers(self):
        provider = FixtureProvider([observation(quote=" usd ", source=" fixture ")], source=" fixture ", quote=" usd ")
        self.imported(provider, " usd ")
        row = self.rows()[0]
        self.assertEqual((row.base_currency, row.quote_currency, row.source), ("EUR", "USD", "FIXTURE"))
        self.assertEqual(self.rates.get_exact_rate(rate_date=START, base_currency="eur", quote_currency="usd", source="fixture"), EXACT_USD)

    def test_mnb_soap_parsing_sync_and_cli_compatibility_use_generic_storage(self):
        def xml_response(**kwargs):
            dates = [day for day in (START, FRIDAY) if kwargs["startDate"] <= day.isoformat() <= kwargs["endDate"]]
            return '<MNBExchangeRates>' + ''.join(
                f'<Day date="{day}"><Rate unit="1" curr="EUR">392,10</Rate><Rate unit="1" curr="USD">333,00</Rate></Day>'
                for day in dates) + '</MNBExchangeRates>'
        self.imported()  # Real MNB adapter must leave fixture USD rows intact.
        with patch.object(config, "MNB_EXCHANGE_RATE_START_DATE", START), patch("app.services.mnb_exchange_rate_provider.Client") as client:
            client.return_value.service.GetExchangeRates.side_effect = xml_response
            result = MnbExchangeRateSyncService(self.db).synchronize(today=SUNDAY)
            self.assertEqual(result.processed_count, 2)
            client.return_value.service.GetExchangeRates.assert_called_with(
                startDate="2026-09-01", endDate="2026-09-06", currencyNames="EUR")
            result = MnbExchangeRateSyncService(self.db).synchronize(today=SUNDAY)
            self.assertEqual(result.requested_ranges, ((FRIDAY, SUNDAY),))
            self.assertEqual(result.processed_count, 1)
            result = MnbExchangeRateImportService(self.db).import_eur_huf_rates(start_date=START, end_date=SUNDAY)
            self.assertEqual((result.currency, result.imported_count, result.skipped_count), ("EUR", 2, 0))
        self.assertEqual(len(self.rows()), 4)
        self.assertEqual(self.rates.get_exact_rate(rate_date=START, base_currency="EUR", quote_currency="HUF", source="MNB"), Decimal("392.10"))
        self.assertEqual(self.rates.get_exact_rate(rate_date=START, base_currency="EUR", quote_currency="USD", source="TEST-USD"), EXACT_USD)
        self.assertEqual({row.rate_date for row in self.rows()}, {START, FRIDAY})

    def test_mnb_escaped_wrapper_and_blank_publication_days(self):
        xml = '<MNBExchangeRates><Day date="2026-09-01"><Rate curr="EUR" unit="1">390,2500</Rate></Day><Day date="2026-09-02"/></MNBExchangeRates>'
        provider = MnbHistoricalRateProvider()
        for content in (xml, html.escape(xml), '<GetExchangeRatesResult>' + html.escape(xml) + '</GetExchangeRatesResult>'):
            rows = provider._parse_exchange_rates(soap_response=content, currency="EUR")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].rate, Decimal("390.2500"))
            self.assertEqual(rows[0].rate_date, START)

    def test_legacy_huf_rows_survive_index_upgrade_without_recreation(self):
        self.rates.upsert_rate(rate_date=START, base_currency="EUR", quote_currency="HUF",
                               rate=Decimal("392.1000"), source="MNB")
        before = self.db.execute(text("SELECT * FROM eur_huf_exchange_rates")).all()
        self.db.rollback()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX uq_exchange_rate_date_pair")
        with patch.object(database, "engine", self.engine):
            database.init_db()
            database.init_db()
        after = self.db.execute(text("SELECT * FROM eur_huf_exchange_rates")).all()
        self.assertEqual(before, after)
        self.imported()
        self.assertEqual(len(self.rows()), 3)

    def test_conflicting_legacy_providers_block_upgrade_without_data_loss(self):
        self.db.rollback()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX uq_exchange_rate_date_pair")
        for source in ("FIRST", "SECOND"):
            self.db.add(ExchangeRateORM(rate_date=START, base_currency="EUR", quote_currency="HUF",
                                       source=source, rate="392.10", unit="1"))
        self.db.commit()
        with self.assertRaisesRegex(RuntimeError, "No rates were discarded"):
            upgrade_exchange_rate_identity(self.engine)
        self.assertEqual(len(self.rows()), 2)

    def test_concurrent_same_source_upserts_remain_single_observation(self):
        barrier = Barrier(2)
        def write(value):
            with Session(self.engine) as db:
                barrier.wait(timeout=5)
                ExchangeRateService(db).upsert_rate(rate_date=START, base_currency="EUR", quote_currency="USD",
                                                     rate=Decimal(value), source="TEST-USD")
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(write, ("1.16", "1.17")))
        self.assertEqual(len(self.rows()), 1)
        self.assertIn(self.rows()[0].rate, ("1.16", "1.17"))


if __name__ == "__main__":
    unittest.main()
