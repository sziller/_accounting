"""Both production sync wrappers share planning but own independent lower limits."""
from datetime import date, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core import config
from app.db.models import Base
from app.services.exchange_rate_service import ExchangeRateService
from app.services.eur_usd_exchange_rate_service import EurUsdExchangeRateService
from app.services.mnb_exchange_rate_provider import MnbHistoricalRateProvider
from app.services.ecb_exchange_rate_provider import EcbHistoricalRateProvider
from app.services.mnb_exchange_rate_sync_service import MnbExchangeRateSyncService
from app.services.ecb_exchange_rate_sync_service import EcbExchangeRateSyncService

START = date(2021, 1, 1)
TODAY = date(2026, 9, 22)


class RangeCases:
    def setUp(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)
        for name in ('MNB_EXCHANGE_RATE_START_DATE', 'ECB_EXCHANGE_RATE_START_DATE'):
            setting = patch.object(config, name, START)
            setting.start()
            self.addCleanup(setting.stop)
        setting = patch.object(config, 'ECB_EXCHANGE_RATE_LOWER_BOUNDARY_TOLERANCE_DAYS', 7)
        setting.start()
        self.addCleanup(setting.stop)

    def seed(self, *days):
        for day in days:
            self.storage(self.db).upsert_rate(rate_date=day, base_currency='EUR',
                quote_currency=self.quote, source=self.source, rate=Decimal('1.2500'))

    def run_sync(self):
        # Mock only retrieval: real wrapper, planner, policy and repository bounds.
        with patch.object(self.provider, 'fetch_rates', return_value=[]) as fetch:
            result = self.sync_service(self.db).synchronize(today=TODAY)
        calls = [(call.kwargs['start_date'], call.kwargs['end_date']) for call in fetch.call_args_list]
        self.assertTrue(all(call.kwargs['quote_currency'] == self.quote for call in fetch.call_args_list))
        return result, calls

    def expected_calls(self, first, last):
        if self.quote == 'USD':
            return [(first, last)]
        # MNB's unchanged yearly SOAP request boundary.
        return [(max(first, date(year, 1, 1)), min(last, date(year, 12, 31)))
                for year in range(first.year, last.year + 1)]

    def test_empty_requests_full_configured_range(self):
        result, calls = self.run_sync()
        self.assertEqual(result.requested_ranges, ((START, TODAY),))
        self.assertEqual(calls, self.expected_calls(START, TODAY))

    def test_old_history_is_not_redownloaded_and_new_dates_are_requested(self):
        self.seed(date(2021, 1, 4), date(2026, 9, 18))
        result, calls = self.run_sync()
        expected = [(date(2026, 9, 18), TODAY)]
        self.assertEqual(list(result.requested_ranges), expected)
        self.assertEqual(calls, expected)

    def test_history_through_yesterday_refreshes_only_yesterday_and_today(self):
        self.seed(date(2021, 1, 4), date(2026, 9, 21))
        _, calls = self.run_sync()
        self.assertEqual(calls, [(date(2026, 9, 21), TODAY)])

    def test_missing_lower_history_only_backfills_to_first_observation(self):
        first = date(2023, 6, 15)
        self.seed(first, TODAY)
        result, calls = self.run_sync()
        self.assertEqual(result.requested_ranges, ((START, first), (TODAY, TODAY)))
        self.assertEqual(calls, self.expected_calls(START, first) + [(TODAY, TODAY)])

    def test_complete_history_still_refreshes_today_inclusively(self):
        self.seed(date(2021, 1, 4), TODAY)
        _, calls = self.run_sync()
        self.assertEqual(calls, [(TODAY, TODAY)])

    def test_tolerance_edge_and_first_day_beyond_it(self):
        edge = START + timedelta(days=self.tolerance)
        self.seed(edge, TODAY)
        _, calls = self.run_sync()
        self.assertEqual(calls, [(TODAY, TODAY)])
        # Move requested start one day earlier: same stored bounds now need backfill.
        earlier = START - timedelta(days=1)
        with patch.object(config, self.setting, earlier):
            result, calls = self.run_sync()
        self.assertEqual(result.requested_ranges, ((earlier, edge), (TODAY, TODAY)))
        self.assertEqual(calls, self.expected_calls(earlier, edge) + [(TODAY, TODAY)])

    def test_start_settings_are_independent_in_both_directions(self):
        own_start = date(2022, 3, 1)
        other_start = date(2020, 5, 1)
        with patch.object(config, self.setting, own_start):
            before, before_calls = self.run_sync()
            with patch.object(config, self.other_setting, other_start):
                after, after_calls = self.run_sync()
        self.assertEqual(before.required_start_date, own_start)
        self.assertEqual(before.requested_ranges, ((own_start, TODAY),))
        self.assertEqual(before_calls, self.expected_calls(own_start, TODAY))
        self.assertEqual(after, before)
        self.assertEqual(after_calls, before_calls)


class MnbStartupRangeTests(RangeCases, unittest.TestCase):
    quote, source, tolerance = 'HUF', 'MNB', 10
    storage = ExchangeRateService
    provider = MnbHistoricalRateProvider
    sync_service = MnbExchangeRateSyncService
    setting = 'MNB_EXCHANGE_RATE_START_DATE'
    other_setting = 'ECB_EXCHANGE_RATE_START_DATE'


class EcbStartupRangeTests(RangeCases, unittest.TestCase):
    quote, source, tolerance = 'USD', 'ECB', 7
    storage = EurUsdExchangeRateService
    provider = EcbHistoricalRateProvider
    sync_service = EcbExchangeRateSyncService
    setting = 'ECB_EXCHANGE_RATE_START_DATE'
    other_setting = 'MNB_EXCHANGE_RATE_START_DATE'
